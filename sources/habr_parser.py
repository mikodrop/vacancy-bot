"""
Парсер вакансий Habr Career через RSS-ленту.

Читает RSS XML и извлекает вакансии с зарплатой.
Фильтрует по дате публикации (HOURS_LOOKBACK).

RSS-лента: https://career.habr.com/vacancies/rss?type=all&with_salary=1&qid=2
"""

import sys
import os
import hashlib
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import aiohttp
from loguru import logger

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import HOURS_LOOKBACK, HEADERS_POOL


# ── Константы ────────────────────────────────────────────────
HABR_RSS_URL: str = (
    "https://career.habr.com/vacancies/rss?schedule[]=remote&with_salary=1"
)


def _get_headers() -> dict[str, str]:
    """Возвращает случайный набор заголовков из пула для ротации."""
    ua = random.choice(HEADERS_POOL)
    return {"User-Agent": ua, "Accept": "application/xml, application/rss+xml, text/xml"}


def _generate_vacancy_id(link: str) -> str:
    """
    Генерирует уникальный vacancy_id на основе хеша ссылки.

    Args:
        link: URL вакансии на Habr Career.

    Returns:
        Шестнадцатеричный SHA-256 хеш (первые 16 символов).
    """
    return hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]


def _parse_salary(title: str) -> tuple[int | None, int | None]:
    """
    Пытается извлечь зарплату из заголовка вакансии Habr Career.

    Habr обычно включает зарплату в заголовок в формате:
      «Должность (от X до Y руб.)» или «Должность (X–Y руб.)»

    Args:
        title: Заголовок вакансии.

    Returns:
        Кортеж (salary_from, salary_to). Значения None, если не удалось разобрать.
    """
    import re

    salary_from: int | None = None
    salary_to: int | None = None

    # Паттерн: «от 100 000 до 200 000» или «100 000 – 200 000»
    range_match = re.search(
        r"(?:от\s*)?([\d\s]+)\s*(?:–|-|—|до)\s*([\d\s]+)\s*(?:₽|руб|р\.?|RUR|USD|\$|€)?",
        title,
    )
    if range_match:
        try:
            salary_from = int(range_match.group(1).replace(" ", "").replace("\u00a0", ""))
            salary_to = int(range_match.group(2).replace(" ", "").replace("\u00a0", ""))
            return salary_from, salary_to
        except ValueError:
            pass

    # Паттерн: «от 100 000»
    from_match = re.search(
        r"от\s*([\d\s]+)\s*(?:₽|руб|р\.?|RUR|USD|\$|€)?", title
    )
    if from_match:
        try:
            salary_from = int(from_match.group(1).replace(" ", "").replace("\u00a0", ""))
        except ValueError:
            pass

    # Паттерн: «до 200 000»
    to_match = re.search(
        r"до\s*([\d\s]+)\s*(?:₽|руб|р\.?|RUR|USD|\$|€)?", title
    )
    if to_match:
        try:
            salary_to = int(to_match.group(1).replace(" ", "").replace("\u00a0", ""))
        except ValueError:
            pass

    return salary_from, salary_to


def _parse_pub_date(pub_date_str: str) -> datetime | None:
    """
    Парсит строку даты из RSS (формат RFC 822).

    Args:
        pub_date_str: Строка даты, например 'Mon, 20 May 2026 10:00:00 +0300'.

    Returns:
        datetime-объект с timezone или None при ошибке.
    """
    try:
        return parsedate_to_datetime(pub_date_str)
    except (ValueError, TypeError):
        logger.debug("Habr: не удалось разобрать дату '{}'", pub_date_str)
        return None


def _normalize_item(item_element: ET.Element) -> dict | None:
    """
    Приводит XML-элемент <item> из RSS к единому формату вакансии.

    Args:
        item_element: XML-элемент <item> из RSS-ленты.

    Returns:
        Нормализованный словарь или None, если элемент невалидный.
    """
    title = (item_element.findtext("title") or "").strip()
    link = (item_element.findtext("link") or "").strip()
    description = (item_element.findtext("description") or "").strip()
    pub_date_str = (item_element.findtext("pubDate") or "").strip()
    author = (item_element.findtext("author") or "").strip()

    if not title or not link:
        return None

    vacancy_id = _generate_vacancy_id(link)
    salary_from, salary_to = _parse_salary(title)
    pub_date = _parse_pub_date(pub_date_str)

    return {
        "source": "habr",
        "vacancy_id": vacancy_id,
        "title": title,
        "company": author,  # RSS содержит компанию в теге <author>
        "salary_from": salary_from,
        "salary_to": salary_to,
        "url": link,
        "schedule": "Удалённая работа",
        "area": "",
        "description": description,
        "requirements": "",
        "published_at": pub_date.isoformat() if pub_date else "",
        "_pub_datetime": pub_date,  # внутреннее поле для фильтрации по дате
    }


async def fetch_habr_vacancies() -> list[dict]:
    """
    Получает список вакансий из RSS-ленты Habr Career.

    Загружает RSS XML, парсит элементы <item>, фильтрует
    по дате публикации (только за последние HOURS_LOOKBACK часов).

    Returns:
        Список нормализованных словарей вакансий.
        При ошибке возвращает пустой список.
    """
    vacancies: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_LOOKBACK)

    logger.info(
        "Habr: запуск сбора вакансий из RSS (lookback={}ч, cutoff={})",
        HOURS_LOOKBACK,
        cutoff.isoformat(),
    )

    try:
        headers = _get_headers()

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    HABR_RSS_URL,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "Habr: получен статус {} при загрузке RSS",
                            response.status,
                        )
                        return vacancies

                    xml_text: str = await response.text()

            except aiohttp.ClientError as exc:
                logger.error("Habr: сетевая ошибка при загрузке RSS: {}", exc)
                return vacancies

        # Парсим XML
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.error("Habr: ошибка парсинга XML RSS: {}", exc)
            return vacancies

        # Ищем все элементы <item>
        channel = root.find("channel")
        if channel is None:
            # Пробуем найти items напрямую в root
            items = root.findall(".//item")
        else:
            items = channel.findall("item")

        logger.debug("Habr: найдено {} элементов <item> в RSS", len(items))

        for item_el in items:
            try:
                normalized = _normalize_item(item_el)
                if normalized is None:
                    continue

                # Фильтрация по дате: только свежие вакансии
                pub_datetime = normalized.pop("_pub_datetime", None)
                if pub_datetime is not None:
                    # Приводим cutoff к aware datetime для корректного сравнения
                    if pub_datetime.tzinfo is None:
                        pub_datetime = pub_datetime.replace(tzinfo=timezone.utc)

                    if pub_datetime < cutoff:
                        continue

                vacancies.append(normalized)

            except Exception as exc:
                logger.warning(
                    "Habr: ошибка обработки элемента RSS: {}", exc
                )

    except Exception as exc:
        logger.error("Habr: непредвиденная ошибка при сборе вакансий: {}", exc)

    logger.info("Habr: всего собрано {} вакансий", len(vacancies))
    return vacancies
