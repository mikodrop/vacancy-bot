"""
Парсер вакансий с портала «Работа России» (trudvsem.ru) — Роструд.

Использует официальное бесплатное API opendata.trudvsem.ru.
Авторизация не требуется.

Документация: https://trudvsem.ru/information-rest/swagger-ui.html
"""

import sys
import os
import random
from datetime import datetime, timezone

import aiohttp
from loguru import logger

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SALARY_MIN, HOURS_LOOKBACK, HEADERS_POOL


# ── Константы ────────────────────────────────────────────────
TRUDVSEM_API_URL: str = "https://opendata.trudvsem.ru/api/v1/vacancies"
MAX_PAGES: int = 3
LIMIT: int = 50


def _get_headers() -> dict[str, str]:
    """Возвращает случайный набор заголовков из пула для ротации."""
    ua = random.choice(HEADERS_POOL)
    return {"User-Agent": ua, "Accept": "application/json"}


def _normalize_vacancy(vacancy_data: dict) -> dict | None:
    """
    Приводит вакансию из ответа Trudvsem API к единому формату.

    Ответ API имеет вложенную структуру:
      results -> vacancies -> [{vacancy: {...}}, ...]

    Args:
        vacancy_data: Внутренний словарь вакансии (содержимое ключа 'vacancy').

    Returns:
        Нормализованный словарь или None при ошибке парсинга.
    """
    try:
        # Извлекаем зарплату
        salary_min = vacancy_data.get("salary_min")
        salary_max = vacancy_data.get("salary_max")
        if salary_min is not None:
            salary_min = int(salary_min)
        if salary_max is not None:
            salary_max = int(salary_max)

        # Извлекаем данные компании
        company_data = vacancy_data.get("company") or {}

        # Извлекаем регион
        addresses = vacancy_data.get("addresses") or {}
        address_list = addresses.get("address") or []
        area = ""
        if isinstance(address_list, list) and address_list:
            area = address_list[0].get("region", "")
        elif isinstance(address_list, dict):
            area = address_list.get("region", "")

        return {
            "source": "trudvsem",
            "vacancy_id": str(vacancy_data.get("id", "")),
            "title": vacancy_data.get("job-name", ""),
            "company": company_data.get("name", ""),
            "salary_from": salary_min,
            "salary_to": salary_max,
            "url": vacancy_data.get("vac_url", ""),
            "schedule": f"Удалённая работа ({vacancy_data.get('schedule', '')})",
            "area": area,
            "description": vacancy_data.get("duty", "") or "",
            "requirements": vacancy_data.get("requirement", "") or "",
            "published_at": vacancy_data.get("creation-date", ""),
        }
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Trudvsem: ошибка нормализации вакансии: {}", exc)
        return None


async def fetch_trudvsem_vacancies() -> list[dict]:
    """
    Получает список удалённых вакансий с портала «Работа России».

    Выполняет пагинацию до MAX_PAGES страниц (по LIMIT записей на страницу).
    Формат ответа API: results -> vacancies -> [{vacancy: {...}}, ...]

    Returns:
        Список нормализованных словарей вакансий.
        При ошибке возвращает пустой список.
    """
    vacancies: list[dict] = []

    logger.info(
        "Trudvsem: запуск сбора вакансий (salary≥{}, limit={}, pages≤{})",
        SALARY_MIN,
        LIMIT,
        MAX_PAGES,
    )

    try:
        async with aiohttp.ClientSession() as session:
            for page in range(MAX_PAGES):
                offset = page * LIMIT
                params: dict = {
                    "salaryFrom": SALARY_MIN,
                    "isRemote": "true",
                    "limit": LIMIT,
                    "offset": offset,
                }

                headers = _get_headers()
                logger.debug(
                    "Trudvsem: запрос offset={}, limit={}", offset, LIMIT
                )

                try:
                    async with session.get(
                        TRUDVSEM_API_URL,
                        params=params,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status != 200:
                            logger.warning(
                                "Trudvsem: получен статус {} (offset={})",
                                response.status,
                                offset,
                            )
                            break

                        data: dict = await response.json(content_type=None)

                except aiohttp.ClientError as exc:
                    logger.error(
                        "Trudvsem: сетевая ошибка при запросе (offset={}): {}",
                        offset,
                        exc,
                    )
                    break

                # Структура ответа: {"results": {"vacancies": [{"vacancy": {...}}, ...]}}
                results = data.get("results") or {}
                vacancy_list = results.get("vacancies") or []

                if not vacancy_list:
                    logger.debug(
                        "Trudvsem: offset={} — пустой ответ, пагинация завершена",
                        offset,
                    )
                    break

                page_count = 0
                for entry in vacancy_list:
                    vacancy_data = entry.get("vacancy")
                    if not vacancy_data:
                        continue

                    normalized = _normalize_vacancy(vacancy_data)
                    if normalized:
                        vacancies.append(normalized)
                        page_count += 1

                logger.debug(
                    "Trudvsem: offset={}, получено {} вакансий",
                    offset,
                    page_count,
                )

                # Если получили меньше лимита — больше страниц нет
                if len(vacancy_list) < LIMIT:
                    break

    except Exception as exc:
        logger.error("Trudvsem: непредвиденная ошибка при сборе вакансий: {}", exc)

    logger.info("Trudvsem: всего собрано {} вакансий", len(vacancies))
    return vacancies
