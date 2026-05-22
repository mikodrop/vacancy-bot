# -*- coding: utf-8 -*-
"""
Модуль планировщика задач — сбор, фильтрация и публикация вакансий.

Содержит основную задачу daily_job(), которая:
1. Собирает вакансии из всех включённых источников
2. Фильтрует по заданным критериям
3. Проверяет дубликаты через базу данных
4. Публикует новые вакансии в Telegram-канал
"""

import sys
import os
import hashlib
import asyncio
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import SOURCES, MAX_PER_SESSION, DELAY_BETWEEN_POSTS
from db.database import Database
from filters.vacancy_filter import filter_vacancies
from templates.post_template import format_post, format_post_short
from bot.publisher import Publisher
from loguru import logger


async def _fetch_from_source(source_name: str) -> List[Dict[str, Any]]:
    """
    Получает вакансии из указанного источника.

    Args:
        source_name: имя источника (hh, trudvsem, superjob, tg, vk, habr, avito)

    Returns:
        Список словарей с данными вакансий.
    """
    vacancies: List[Dict[str, Any]] = []

    try:
        if source_name == "hh":
            from sources.hh_api import fetch_hh_vacancies
            vacancies = await fetch_hh_vacancies()

        elif source_name == "trudvsem":
            from sources.trudvsem_api import fetch_trudvsem_vacancies
            vacancies = await fetch_trudvsem_vacancies()

        elif source_name == "superjob":
            from sources.superjob_api import fetch_superjob_vacancies
            vacancies = await fetch_superjob_vacancies()

        elif source_name == "tg":
            from sources.tg_parser import fetch_tg_vacancies
            vacancies = await fetch_tg_vacancies()

        elif source_name == "vk":
            from sources.vk_parser import fetch_vk_vacancies
            vacancies = await fetch_vk_vacancies()

        elif source_name == "habr":
            from sources.habr_parser import fetch_habr_vacancies
            vacancies = await fetch_habr_vacancies()

        elif source_name == "avito":
            from sources.avito_parser import fetch_avito_vacancies
            vacancies = await fetch_avito_vacancies()

        else:
            logger.warning(f"Неизвестный источник: {source_name}")
            return []

        logger.info(f"Источник '{source_name}': получено {len(vacancies)} вакансий")

    except ImportError as e:
        logger.error(f"Не удалось импортировать модуль для источника '{source_name}': {e}")
    except Exception as e:
        logger.error(f"Ошибка при сборе вакансий из '{source_name}': {e}")

    return vacancies


def _title_hash(title: str) -> str:
    """
    Вычисляет SHA-256 хеш от заголовка вакансии (в нижнем регистре, без пробелов по краям).

    Args:
        title: заголовок вакансии

    Returns:
        Hex-строка SHA-256 хеша.
    """
    normalized = title.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def daily_job() -> None:
    """
    Основная задача планировщика — полный цикл сбора и публикации вакансий.

    Последовательность:
    1. Сбор вакансий из всех включённых источников (SOURCES)
    2. Фильтрация по ключевым словам / стоп-словам / зарплате
    3. Проверка на дубликаты через БД (по source+id, url, title_hash)
    4. Форматирование и публикация в Telegram-канал (до MAX_PER_SESSION штук)
    5. Сохранение опубликованных записей в БД
    """
    logger.info("=" * 60)
    logger.info("Запуск задачи сбора и публикации вакансий")
    logger.info("=" * 60)

    db = Database()
    publisher = Publisher()

    try:
        await db.init_db()

        # ── 1. Сбор вакансий из всех включённых источников ──────────
        all_vacancies: List[Dict[str, Any]] = []

        for source_name, enabled in SOURCES.items():
            if not enabled:
                logger.debug(f"Источник '{source_name}' отключён, пропускаем")
                continue

            fetched = await _fetch_from_source(source_name)
            all_vacancies.extend(fetched)

        logger.info(f"Всего собрано вакансий (до фильтрации): {len(all_vacancies)}")

        if not all_vacancies:
            logger.warning("Не удалось собрать ни одной вакансии, завершаем")
            return

        # ── 2. Фильтрация ──────────────────────────────────────────
        filtered = filter_vacancies(all_vacancies)
        logger.info(f"После фильтрации: {len(filtered)} вакансий")

        if not filtered:
            logger.info("После фильтрации не осталось вакансий")
            return

        # ── 3. Проверка дубликатов ──────────────────────────────────
        new_vacancies: List[Dict[str, Any]] = []

        for vacancy in filtered:
            source = vacancy.get("source", "unknown")
            vacancy_id = vacancy.get("vacancy_id", "")
            url = vacancy.get("url", "")
            title = vacancy.get("title", "")
            company = vacancy.get("company", "")

            # Проверяем по source + vacancy_id
            if vacancy_id and await db.exists(source, str(vacancy_id)):
                logger.debug(f"Дубликат (source+id): {title[:50]}")
                continue

            # Проверяем по URL
            if url and await db.exists_by_url(url):
                logger.debug(f"Дубликат (url): {title[:50]}")
                continue

            # Проверяем по хешу заголовка
            if title and company and await db.exists_by_hash(title, company):
                logger.debug(f"Дубликат (title_hash): {title[:50]}")
                continue

            new_vacancies.append(vacancy)

        logger.info(f"Новых уникальных вакансий: {len(new_vacancies)}")

        if not new_vacancies:
            logger.info("Нет новых вакансий для публикации")
            return

        # ── 4. Публикация ───────────────────────────────────────────
        published_count = 0

        for vacancy in new_vacancies[:MAX_PER_SESSION]:
            try:
                title = vacancy.get("title", "")
                description = vacancy.get("description", "")

                # Выбираем шаблон в зависимости от наличия описания
                if description and description.strip():
                    text = format_post(vacancy)
                else:
                    text = format_post_short(vacancy)

                success = await publisher.send_to_channel(text)

                if success:
                    # Сохраняем в БД
                    await db.insert(vacancy)
                    published_count += 1
                    logger.info(
                        f"[{published_count}/{MAX_PER_SESSION}] "
                        f"Опубликовано: {title[:60]}"
                    )
                else:
                    logger.warning(f"Не удалось опубликовать: {title[:60]}")

            except Exception as e:
                logger.error(
                    f"Ошибка при публикации вакансии "
                    f"'{vacancy.get('title', '?')[:40]}': {e}"
                )

            # Задержка между постами, чтобы не нарваться на лимиты Telegram
            if published_count < MAX_PER_SESSION:
                await asyncio.sleep(DELAY_BETWEEN_POSTS)

        logger.info(f"Итого опубликовано: {published_count} вакансий")

    except Exception as e:
        logger.exception(f"Критическая ошибка в daily_job: {e}")

    finally:
        await publisher.close()
        await db.close()
        logger.info("Задача завершена, ресурсы освобождены")


async def test_source(source_name: str) -> None:
    """
    Тестовый запуск одного источника — загружает вакансии и выводит в лог
    без публикации в канал. Используется для отладки.

    Args:
        source_name: имя источника (hh, trudvsem, superjob, tg, vk, habr, avito)
    """
    logger.info(f"Тестовый запуск источника: {source_name}")

    vacancies = await _fetch_from_source(source_name)

    if not vacancies:
        logger.warning(f"Источник '{source_name}' не вернул вакансий")
        return

    logger.info(f"Получено {len(vacancies)} вакансий из '{source_name}':")
    logger.info("-" * 60)

    for i, v in enumerate(vacancies, start=1):
        title = v.get("title", "—")
        company = v.get("company", "—")
        sal_from = v.get("salary_from")
        sal_to = v.get("salary_to")
        salary = f"{sal_from or ''} - {sal_to or ''}".strip(" -") or "не указана"
        area = v.get("area", "—")
        url = v.get("url", "—")

        logger.info(
            f"  [{i}] {title}\n"
            f"       Компания: {company}\n"
            f"       Зарплата: {salary}\n"
            f"       Регион:   {area}\n"
            f"       URL:      {url}"
        )

    logger.info("-" * 60)
    logger.info(f"Всего: {len(vacancies)}")

    # Показываем результат фильтрации (но не публикуем)
    filtered = filter_vacancies(vacancies)
    logger.info(f"После фильтрации осталось: {len(filtered)} вакансий")
