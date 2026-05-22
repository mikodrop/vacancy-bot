"""
Парсер вакансий SuperJob через официальный API.

Требует ключ API (SUPERJOB_SECRET), который передаётся
в заголовке X-Api-App-Id.

Регистрация ключа: https://api.superjob.ru/
Документация API: https://api.superjob.ru/info/
"""

import sys
import os
import random

import aiohttp
from loguru import logger

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SALARY_MIN, SUPERJOB_SECRET, HEADERS_POOL


# ── Константы ────────────────────────────────────────────────
SUPERJOB_API_URL: str = "https://api.superjob.ru/2.0/vacancies/"
MAX_PAGES: int = 3
COUNT: int = 50


def _get_headers() -> dict[str, str]:
    """
    Возвращает заголовки запроса с авторизацией SuperJob и случайным User-Agent.
    """
    ua = random.choice(HEADERS_POOL)
    return {
        "User-Agent": ua,
        "Accept": "application/json",
        "X-Api-App-Id": SUPERJOB_SECRET,
    }


def _normalize_vacancy(item: dict) -> dict:
    """
    Приводит вакансию из ответа SuperJob API к единому формату.

    Args:
        item: Словарь вакансии из JSON-ответа SuperJob.

    Returns:
        Нормализованный словарь вакансии.
    """
    # SuperJob возвращает payment_from / payment_to напрямую
    salary_from = item.get("payment_from")
    salary_to = item.get("payment_to")

    # Приводим 0 к None для единообразия
    if salary_from == 0:
        salary_from = None
    if salary_to == 0:
        salary_to = None

    # Извлекаем данные о городе/регионе
    town_data = item.get("town") or {}
    place_of_work = item.get("place_of_work") or {}

    return {
        "source": "superjob",
        "vacancy_id": str(item.get("id", "")),
        "title": item.get("profession", ""),
        "company": item.get("firm_name", ""),
        "salary_from": salary_from,
        "salary_to": salary_to,
        "url": item.get("link", ""),
        "schedule": place_of_work.get("title", ""),
        "area": town_data.get("title", ""),
        "description": item.get("candidat", "") or "",
        "requirements": item.get("work", "") or "",
        "published_at": "",  # SuperJob отдаёт UNIX timestamp, преобразуем ниже
    }


async def fetch_superjob_vacancies() -> list[dict]:
    """
    Получает список удалённых вакансий с SuperJob.

    Если SUPERJOB_SECRET не задан в конфигурации,
    логирует предупреждение и возвращает пустой список.

    Returns:
        Список нормализованных словарей вакансий.
        При ошибке или отсутствии ключа возвращает пустой список.
    """
    # Проверяем наличие ключа API
    if not SUPERJOB_SECRET:
        logger.warning(
            "SuperJob: SUPERJOB_SECRET не задан — пропускаем источник. "
            "Получите ключ на https://api.superjob.ru/"
        )
        return []

    vacancies: list[dict] = []

    logger.info(
        "SuperJob: запуск сбора вакансий (salary≥{}, count={}, pages≤{})",
        SALARY_MIN,
        COUNT,
        MAX_PAGES,
    )

    try:
        async with aiohttp.ClientSession() as session:
            for page in range(MAX_PAGES):
                params: dict = {
                    "t[0]": 4,                  # Тип занятости: дистанционная работа
                    "payment_from": SALARY_MIN,
                    "currency": "rub",
                    "count": COUNT,
                    "page": page,
                }

                headers = _get_headers()
                logger.debug("SuperJob: запрос страницы {}", page)

                try:
                    async with session.get(
                        SUPERJOB_API_URL,
                        params=params,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status == 403:
                            logger.error(
                                "SuperJob: доступ запрещён (403) — проверьте SUPERJOB_SECRET"
                            )
                            return vacancies

                        if response.status != 200:
                            logger.warning(
                                "SuperJob: получен статус {} на странице {}",
                                response.status,
                                page,
                            )
                            break

                        data: dict = await response.json()

                except aiohttp.ClientError as exc:
                    logger.error(
                        "SuperJob: сетевая ошибка при запросе страницы {}: {}",
                        page,
                        exc,
                    )
                    break

                items: list = data.get("objects", [])
                if not items:
                    logger.debug(
                        "SuperJob: страница {} пуста, пагинация завершена", page
                    )
                    break

                for item in items:
                    try:
                        normalized = _normalize_vacancy(item)

                        # Преобразуем UNIX timestamp в ISO-строку
                        date_published = item.get("date_published")
                        if date_published:
                            from datetime import datetime, timezone

                            normalized["published_at"] = (
                                datetime.fromtimestamp(
                                    date_published, tz=timezone.utc
                                ).isoformat()
                            )

                        vacancies.append(normalized)
                    except (KeyError, TypeError, ValueError) as exc:
                        logger.warning(
                            "SuperJob: ошибка нормализации вакансии id={}: {}",
                            item.get("id", "?"),
                            exc,
                        )

                logger.debug(
                    "SuperJob: страница {}, получено {} вакансий",
                    page,
                    len(items),
                )

                # Проверяем, есть ли ещё данные
                more: bool = data.get("more", False)
                if not more:
                    break

    except Exception as exc:
        logger.error("SuperJob: непредвиденная ошибка при сборе вакансий: {}", exc)

    logger.info("SuperJob: всего собрано {} вакансий", len(vacancies))
    return vacancies
