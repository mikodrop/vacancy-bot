"""
Модуль для работы с базой данных SQLite.

Предоставляет асинхронный класс Database для хранения
опубликованных вакансий и конфигурации источников.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import aiosqlite
from loguru import logger

from config import DB_PATH


class Database:
    """Асинхронный менеджер базы данных для хранения вакансий."""

    def __init__(self, db_path: str | None = None) -> None:
        """
        Инициализация менеджера БД.

        Args:
            db_path: путь к файлу базы данных. По умолчанию берётся из config.
        """
        self.db_path = db_path or str(DB_PATH)
        self._conn: aiosqlite.Connection | None = None

    # ── Подключение / отключение ──────────────────────────────

    async def _get_connection(self) -> aiosqlite.Connection:
        """
        Получить активное соединение, создав его при необходимости.

        Returns:
            Активное соединение aiosqlite.
        """
        if self._conn is None:
            # Создаём директорию data/, если её нет
            import pathlib
            pathlib.Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            logger.info("Подключение к БД установлено: {}", self.db_path)
        return self._conn

    async def close(self) -> None:
        """Закрыть соединение с базой данных."""
        try:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
                logger.info("Соединение с БД закрыто")
        except Exception as e:
            logger.error("Ошибка при закрытии соединения с БД: {}", e)

    # ── Инициализация таблиц ──────────────────────────────────

    async def init_db(self) -> None:
        """Создать таблицы published_vacancies и sources_config, если они не существуют."""
        try:
            conn = await self._get_connection()

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS published_vacancies (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    source       TEXT NOT NULL,
                    vacancy_id   TEXT NOT NULL,
                    title        TEXT,
                    company      TEXT,
                    salary_from  INTEGER,
                    salary_to    INTEGER,
                    url          TEXT,
                    published_at DATETIME,
                    posted_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                    title_hash   TEXT,
                    UNIQUE(source, vacancy_id)
                );
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sources_config (
                    source     TEXT PRIMARY KEY,
                    enabled    INTEGER DEFAULT 1,
                    last_check DATETIME
                );
                """
            )

            await conn.commit()
            logger.info("Таблицы БД инициализированы")
        except Exception as e:
            logger.error("Ошибка при инициализации БД: {}", e)
            raise

    # ── Проверки дубликатов ───────────────────────────────────

    async def exists(self, source: str, vacancy_id: str) -> bool:
        """
        Проверить, существует ли вакансия по source + vacancy_id.

        Args:
            source: название источника (hh, trudvsem, и т.д.).
            vacancy_id: идентификатор вакансии в источнике.

        Returns:
            True, если запись уже существует.
        """
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT 1 FROM published_vacancies WHERE source = ? AND vacancy_id = ? LIMIT 1",
                (source, vacancy_id),
            )
            row = await cursor.fetchone()
            return row is not None
        except Exception as e:
            logger.error("Ошибка при проверке exists({}, {}): {}", source, vacancy_id, e)
            return False

    async def exists_by_url(self, url: str) -> bool:
        """
        Проверить, существует ли вакансия по URL.

        Args:
            url: прямая ссылка на вакансию.

        Returns:
            True, если запись с таким URL уже есть.
        """
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT 1 FROM published_vacancies WHERE url = ? LIMIT 1",
                (url,),
            )
            row = await cursor.fetchone()
            return row is not None
        except Exception as e:
            logger.error("Ошибка при проверке exists_by_url({}): {}", url, e)
            return False

    async def exists_by_hash(self, title: str, company: str) -> bool:
        """
        Проверить, существует ли вакансия по MD5-хешу title+company.

        Используется как фолбэк-дедупликация, когда у вакансии
        нет уникального vacancy_id или URL.

        Args:
            title: название вакансии.
            company: название компании.

        Returns:
            True, если запись с таким хешем уже есть.
        """
        try:
            hash_value = self._make_hash(title, company)
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT 1 FROM published_vacancies WHERE title_hash = ? LIMIT 1",
                (hash_value,),
            )
            row = await cursor.fetchone()
            return row is not None
        except Exception as e:
            logger.error("Ошибка при проверке exists_by_hash({}, {}): {}", title, company, e)
            return False

    # ── Вставка записи ────────────────────────────────────────

    async def insert(self, vacancy: dict[str, Any]) -> bool:
        """
        Вставить запись о вакансии в таблицу published_vacancies.

        Args:
            vacancy: словарь с полями вакансии. Обязательные ключи:
                     source, vacancy_id. Остальные — опциональны.

        Returns:
            True, если запись успешно вставлена; False при дубликате или ошибке.
        """
        try:
            conn = await self._get_connection()

            title = vacancy.get("title", "")
            company = vacancy.get("company", "")
            title_hash = self._make_hash(title, company)

            await conn.execute(
                """
                INSERT INTO published_vacancies
                    (source, vacancy_id, title, company,
                     salary_from, salary_to, url,
                     published_at, title_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vacancy.get("source", "unknown"),
                    vacancy.get("vacancy_id", ""),
                    title,
                    company,
                    vacancy.get("salary_from"),
                    vacancy.get("salary_to"),
                    vacancy.get("url"),
                    vacancy.get("published_at"),
                    title_hash,
                ),
            )
            await conn.commit()

            logger.debug(
                "Вакансия сохранена: [{}] {} — {}",
                vacancy.get("source"),
                title,
                company,
            )
            return True
        except aiosqlite.IntegrityError:
            logger.warning(
                "Дубликат вакансии: [{}] {}",
                vacancy.get("source"),
                vacancy.get("vacancy_id"),
            )
            return False
        except Exception as e:
            logger.error("Ошибка при вставке вакансии: {}", e)
            return False

    # ── Статистика ────────────────────────────────────────────

    async def get_stats(self) -> dict[str, int]:
        """
        Получить количество опубликованных вакансий по каждому источнику.

        Returns:
            Словарь {source: count}.
        """
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT source, COUNT(*) as cnt FROM published_vacancies GROUP BY source"
            )
            rows = await cursor.fetchall()
            stats: dict[str, int] = {row["source"]: row["cnt"] for row in rows}
            logger.debug("Статистика вакансий: {}", stats)
            return stats
        except Exception as e:
            logger.error("Ошибка при получении статистики: {}", e)
            return {}

    # ── Последние вакансии ────────────────────────────────────

    async def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Получить последние опубликованные вакансии.

        Args:
            limit: максимальное количество записей (по умолчанию 10).

        Returns:
            Список словарей с данными вакансий.
        """
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM published_vacancies ORDER BY posted_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            result = [dict(row) for row in rows]
            logger.debug("Получено {} последних вакансий", len(result))
            return result
        except Exception as e:
            logger.error("Ошибка при получении последних вакансий: {}", e)
            return []

    # ── Утилиты ───────────────────────────────────────────────

    @staticmethod
    def _make_hash(title: str, company: str) -> str:
        """
        Создать MD5-хеш из title + company для фолбэк-дедупликации.

        Args:
            title: название вакансии.
            company: название компании.

        Returns:
            Шестнадцатеричная строка MD5-хеша.
        """
        raw = f"{title.strip().lower()}|{company.strip().lower()}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()
