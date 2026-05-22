"""
Парсер Telegram-каналов через Telethon (MTProto API).

Читает посты из заданных публичных каналов, извлекает текст вакансий,
ищет зарплаты и ссылки, нормализует в унифицированный формат.

Требует api_id и api_hash с https://my.telegram.org
Сессия сохраняется в файл data/tg_session для переиспользования авторизации.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

# ── Гарантируем доступ к config из корня проекта ──────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (  # noqa: E402
    BASE_DIR,
    HOURS_LOOKBACK,
    TG_API_HASH,
    TG_API_ID,
    TG_CHANNELS_TO_MONITOR,
    TG_PHONE,
)

try:
    from telethon import TelegramClient  # type: ignore[import-untyped]
    from telethon.errors import ChannelPrivateError, FloodWaitError  # type: ignore[import-untyped]

    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    logger.warning("telethon не установлен — парсинг TG-каналов недоступен")

# ── Регулярные выражения ─────────────────────────────────────
# Паттерн для поиска зарплаты: «50000», «50 000», «50к», «50k», «50 тыс»
_SALARY_PATTERN = re.compile(
    r"(\d[\d\s]*\d|\d+)"           # число (возможно с пробелами внутри)
    r"\s*"                          # опциональный пробел
    r"(000|к|k|тыс\.?|руб\.?|₽)?", # суффикс
    re.IGNORECASE,
)
# Паттерн для извлечения URL из текста
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"')\]]+",
    re.IGNORECASE,
)

# Путь к файлу сессии Telethon
_SESSION_PATH = str(BASE_DIR / "data" / "tg_session")


class TelegramParser:
    """Клиент для чтения постов из Telegram-каналов через Telethon."""

    def __init__(self) -> None:
        """Инициализация клиента Telethon."""
        if not TELETHON_AVAILABLE:
            raise RuntimeError("telethon не установлен")

        # Убедимся, что директория для сессии существует
        os.makedirs(os.path.dirname(_SESSION_PATH), exist_ok=True)

        self.client = TelegramClient(
            _SESSION_PATH,
            TG_API_ID,
            TG_API_HASH,
        )
        logger.debug("TelegramParser инициализирован (сессия: {})", _SESSION_PATH)

    async def start(self) -> None:
        """Запуск клиента и авторизация (при необходимости — по телефону)."""
        try:
            if TG_PHONE:
                await self.client.start(phone=TG_PHONE)
            else:
                await self.client.start()
            logger.info("Telethon-клиент успешно подключён")
        except Exception as exc:
            logger.error("Ошибка при запуске Telethon-клиента: {}", exc)
            raise

    async def get_channel_posts(
        self,
        channel_username: str,
        hours_back: int = HOURS_LOOKBACK,
    ) -> list[dict[str, Any]]:
        """
        Получить посты из канала за последние hours_back часов.

        Args:
            channel_username: юзернейм канала (например, '@TGwork')
            hours_back: сколько часов назад искать

        Returns:
            Список вакансий в унифицированном формате.
        """
        vacancies: list[dict[str, Any]] = []
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours_back)

        try:
            entity = await self.client.get_entity(channel_username)
            messages = await self.client.get_messages(entity, limit=50)
        except ChannelPrivateError:
            logger.warning("Канал {} приватный — пропускаем", channel_username)
            return []
        except FloodWaitError as exc:
            logger.warning(
                "FloodWait для {} — ждём {} сек (пропускаем)",
                channel_username,
                exc.seconds,
            )
            return []
        except Exception as exc:
            logger.error(
                "Ошибка при получении постов из {}: {}",
                channel_username,
                exc,
            )
            return []

        for msg in messages:
            # Пропускаем сообщения без текста
            if not msg.text:
                continue

            # Фильтр по дате — msg.date в UTC
            msg_date = msg.date
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)

            if msg_date < cutoff:
                # Сообщения отсортированы по дате (новые первые),
                # значит дальше ещё старше — прерываем
                break

            vacancy = self._parse_message_to_vacancy(
                text=msg.text,
                channel=channel_username,
                msg_date=msg_date,
            )
            if vacancy:
                vacancies.append(vacancy)

        logger.info(
            "Канал {}: найдено {} записей за последние {} ч",
            channel_username,
            len(vacancies),
            hours_back,
        )
        return vacancies

    def _parse_message_to_vacancy(
        self,
        text: str,
        channel: str,
        msg_date: datetime,
    ) -> dict[str, Any] | None:
        """
        Разбор текста сообщения и нормализация в унифицированный формат.

        Args:
            text: полный текст сообщения
            channel: юзернейм канала-источника
            msg_date: дата сообщения (UTC)

        Returns:
            Словарь вакансии или None, если текст слишком короткий.
        """
        # Игнорируем слишком короткие сообщения (менее 30 символов)
        if len(text.strip()) < 30:
            return None

        # Заголовок — первая непустая строка текста
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        title = lines[0] if lines else text[:80]

        # Обрезаем слишком длинный заголовок
        if len(title) > 120:
            title = title[:117] + "..."

        # Поиск зарплаты
        salary_from, salary_to = self._extract_salary(text)

        # Поиск URL-ов в тексте
        urls = _URL_PATTERN.findall(text)
        url = urls[0] if urls else ""

        # Уникальный ID: SHA-256 хеш от первых 100 символов текста
        vacancy_id = hashlib.sha256(text[:100].encode("utf-8")).hexdigest()[:16]

        return {
            "source": "tg",
            "vacancy_id": vacancy_id,
            "title": title,
            "company": "",
            "salary_from": salary_from,
            "salary_to": salary_to,
            "description": text,
            "url": url,
            "schedule": "",
            "area": "",
            "published_at": msg_date.isoformat(),
            "extra": {"channel": channel},
        }

    @staticmethod
    def _extract_salary(text: str) -> tuple[int | None, int | None]:
        """
        Попытка извлечь диапазон зарплаты из текста.

        Ищет паттерны вида: «50 000 руб», «50к», «50k», «50 тыс», «от 80 000 до 120 000».
        Возвращает кортеж (salary_from, salary_to).
        """
        # Ищем контексты со словами «зарплата», «оплата», «оклад», «от», «до», «₽», «руб»
        salary_context_pattern = re.compile(
            r"(?:зарплата|оплата|оклад|з/?п|зп|ставка|доход)"
            r".{0,50}"
            r"(\d[\d\s]*\d|\d+)"
            r"\s*(000|к|k|тыс\.?|руб\.?|₽)?",
            re.IGNORECASE,
        )
        matches = salary_context_pattern.findall(text)

        if not matches:
            # Пробуем более широкий поиск по паттернам с «₽», «руб»
            rub_pattern = re.compile(
                r"(\d[\d\s]*\d|\d+)\s*(000|к|k|тыс\.?)?\s*(?:₽|руб)",
                re.IGNORECASE,
            )
            matches = rub_pattern.findall(text)

        if not matches:
            return None, None

        values: list[int] = []
        for raw_number, suffix in matches[:4]:  # макс 4 совпадения
            try:
                number = int(raw_number.replace(" ", "").replace("\u00a0", ""))
            except ValueError:
                continue

            suffix_lower = suffix.lower().rstrip(".")
            if suffix_lower in ("к", "k", "тыс"):
                number *= 1000
            elif suffix_lower == "000":
                pass  # число уже содержит 000

            # Адекватная зарплата — от 5 000 до 1 000 000
            if 5_000 <= number <= 1_000_000:
                values.append(number)

        if not values:
            return None, None
        if len(values) == 1:
            return values[0], None
        # Если нашли ≥2, берём min и max
        return min(values), max(values)

    async def fetch_all_channels(self) -> list[dict[str, Any]]:
        """
        Обойти все каналы из TG_CHANNELS_TO_MONITOR и собрать вакансии.

        Returns:
            Агрегированный список вакансий из всех каналов.
        """
        all_vacancies: list[dict[str, Any]] = []

        for channel in TG_CHANNELS_TO_MONITOR:
            try:
                posts = await self.get_channel_posts(channel)
                all_vacancies.extend(posts)
            except ChannelPrivateError:
                logger.warning("Канал {} приватный — пропускаем", channel)
            except FloodWaitError as exc:
                logger.warning(
                    "FloodWait при обходе {}: {} сек — пропускаем",
                    channel,
                    exc.seconds,
                )
            except Exception as exc:
                logger.error("Ошибка при парсинге канала {}: {}", channel, exc)

        logger.info(
            "Итого из TG-каналов собрано {} записей из {} каналов",
            len(all_vacancies),
            len(TG_CHANNELS_TO_MONITOR),
        )
        return all_vacancies

    async def close(self) -> None:
        """Отключение от Telegram."""
        try:
            await self.client.disconnect()
            logger.debug("Telethon-клиент отключён")
        except Exception as exc:
            logger.error("Ошибка при отключении Telethon: {}", exc)


async def fetch_tg_vacancies() -> list[dict[str, Any]]:
    """
    Главная функция модуля — собрать вакансии из всех TG-каналов.

    Проверяет наличие учётных данных Telethon. Если api_id/api_hash
    не заданы — возвращает пустой список с предупреждением.

    Returns:
        Список вакансий в унифицированном формате.
    """
    # Проверка доступности Telethon
    if not TELETHON_AVAILABLE:
        logger.warning("telethon не установлен — пропускаем парсинг TG-каналов")
        return []

    # Проверка учётных данных
    if TG_API_ID == 0 or not TG_API_HASH:
        logger.warning(
            "TG_API_ID или TG_API_HASH не заданы — "
            "парсинг Telegram-каналов отключён"
        )
        return []

    if not TG_CHANNELS_TO_MONITOR:
        logger.info("Список TG_CHANNELS_TO_MONITOR пуст — нечего парсить")
        return []

    parser = TelegramParser()
    try:
        await parser.start()
        vacancies = await parser.fetch_all_channels()
        return vacancies
    except Exception as exc:
        logger.error("Критическая ошибка при парсинге TG-каналов: {}", exc)
        return []
    finally:
        await parser.close()
