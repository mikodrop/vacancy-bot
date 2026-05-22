"""
Парсер вакансий HeadHunter (hh.ru) через официальное REST API.

ПРИОРИТЕТ №1 — основной источник вакансий.
Использует публичный API без авторизации.
Лимиты: 5 запросов/сек без токена.

Документация API: https://github.com/hhru/api
"""

import sys
import os
import random
from datetime import datetime, timedelta, timezone

import aiohttp
from loguru import logger

# Обеспечиваем доступ к корневому пакету проекта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SALARY_MIN, HOURS_LOOKBACK, HEADERS_POOL


# ── Константы ────────────────────────────────────────────────
HH_API_URL: str = "https://api.hh.ru/vacancies"
MAX_PAGES: int = 5
PER_PAGE: int = 100


def _get_headers() -> dict[str, str]:
    """Возвращает специальный User-Agent, необходимый для HH API."""
    return {
        "User-Agent": "TelegramJobPublisher/1.0 (admin@jobpublisher.ru)",
        "Accept": "application/json"
    }


def _normalize_vacancy(item: dict) -> dict:
    """
    Приводит сырую вакансию из ответа HH API к единому формату.

    Args:
        item: Словарь вакансии из JSON-ответа hh.ru.

    Returns:
        Нормализованный словарь вакансии.
    """
    salary_data = item.get("salary") or {}
    employer_data = item.get("employer") or {}
    snippet_data = item.get("snippet") or {}
    schedule_data = item.get("schedule") or {}
    area_data = item.get("area") or {}

    return {
        "source": "hh",
        "vacancy_id": str(item["id"]),
        "title": item.get("name", ""),
        "company": employer_data.get("name", ""),
        "salary_from": salary_data.get("from"),
        "salary_to": salary_data.get("to"),
        "url": item.get("alternate_url", ""),
        "schedule": schedule_data.get("name", ""),
        "area": area_data.get("name", ""),
        "description": snippet_data.get("responsibility", "") or "",
        "requirements": snippet_data.get("requirement", "") or "",
        "published_at": item.get("published_at", ""),
    }


async def fetch_hh_vacancies() -> list[dict]:
    """
    Получает список удалённых вакансий с hh.ru за последние HOURS_LOOKBACK часов.

    Выполняет пагинацию до MAX_PAGES страниц.
    Каждый запрос использует случайный User-Agent из HEADERS_POOL.

    Returns:
        Список нормализованных словарей вакансий.
        При ошибке возвращает пустой список.
    """
    vacancies: list[dict] = []
    date_from = (
        datetime.now(timezone.utc) - timedelta(hours=HOURS_LOOKBACK)
    ).strftime("%Y-%m-%dT%H:%M:%S")

    logger.info(
        "HH: запуск сбора вакансий (salary≥{}, lookback={}ч, date_from={})",
        SALARY_MIN,
        HOURS_LOOKBACK,
        date_from,
    )

    try:
        async with aiohttp.ClientSession() as session:
            for page in range(MAX_PAGES):
                params: dict = {
                    "area": 113,                     # Россия
                    "schedule": "remote",             # Удалёнка
                    "salary": SALARY_MIN,
                    "currency": "RUR",
                    "only_with_salary": "true",
                    "per_page": PER_PAGE,
                    "page": page,
                    "order_by": "publication_time",
                    "date_from": date_from,
                }

                headers = _get_headers()
                logger.debug("HH: запрос страницы {} с UA '{}'", page, headers.get("User-Agent", "")[:40])

                try:
                    async with session.get(
                        HH_API_URL, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status != 200:
                            logger.warning(
                                "HH: получен статус {} на странице {}", response.status, page
                            )
                            break

                        data: dict = await response.json()

                except aiohttp.ClientError as exc:
                    logger.error("HH: сетевая ошибка при запросе страницы {}: {}", page, exc)
                    break

                items: list = data.get("items", [])
                if not items:
                    logger.debug("HH: страница {} пуста, пагинация завершена", page)
                    break

                for item in items:
                    try:
                        normalized = _normalize_vacancy(item)
                        vacancies.append(normalized)
                    except (KeyError, TypeError) as exc:
                        logger.warning(
                            "HH: ошибка нормализации вакансии id={}: {}",
                            item.get("id", "?"),
                            exc,
                        )

                # Проверяем, есть ли ещё страницы
                total_pages: int = data.get("pages", 0)
                logger.debug(
                    "HH: страница {}/{}, получено {} вакансий",
                    page + 1,
                    total_pages,
                    len(items),
                )

                if page + 1 >= total_pages:
                    break

    except Exception as exc:
        logger.error("HH: непредвиденная ошибка при сборе вакансий: {}", exc)

    logger.info("HH: всего собрано {} вакансий", len(vacancies))
    return vacancies
