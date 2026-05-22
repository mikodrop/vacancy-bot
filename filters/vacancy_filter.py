"""
Модуль фильтрации вакансий.

Применяет набор фильтров (зарплата, стоп-слова, тип занятости,
ключевые слова) к списку вакансий перед публикацией в канал.
Все параметры фильтрации берутся из config.FILTERS.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import FILTERS
from loguru import logger


def is_valid_vacancy(vacancy: dict) -> bool:
    """Проверяет, проходит ли вакансия все фильтры.

    Вакансия — нормализованный словарь с полями:
        title, company, salary_from, salary_to, schedule,
        description, url, source, vacancy_id.

    Args:
        vacancy: словарь с данными вакансии.

    Returns:
        True — вакансия прошла все фильтры, False — отсеяна.
    """
    title = vacancy.get("title", "")

    # ── 1. Проверка зарплаты ──────────────────────────────────
    salary_from = vacancy.get("salary_from")
    if salary_from is not None and salary_from < FILTERS["salary_min"]:
        logger.debug(
            "Вакансия отсеяна по зарплате: «{}» — {} < {}",
            title,
            salary_from,
            FILTERS["salary_min"],
        )
        return False

    # ── 2. Проверка стоп-слов ─────────────────────────────────
    text_combined = f"{title} {vacancy.get('description', '')}".lower()

    for stop_word in FILTERS["keywords_exclude"]:
        if stop_word.lower() in text_combined:
            logger.debug(
                "Вакансия отсеяна по стоп-слову «{}»: «{}»",
                stop_word,
                title,
            )
            return False

    # ── 3. Проверка типа занятости (schedule) ─────────────────
    schedule_value = vacancy.get("schedule", "")
    # Поддерживаем оба ключа из config: "schedule" и "schedule_keywords"
    schedule_keywords = FILTERS.get("schedule", FILTERS.get("schedule_keywords", []))

    if schedule_value:
        schedule_lower = schedule_value.lower()
        if not any(kw.lower() in schedule_lower for kw in schedule_keywords):
            logger.debug(
                "Вакансия отсеяна по типу занятости: «{}» — schedule='{}'",
                title,
                schedule_value,
            )
            return False

    # ── 4. Проверка включающих ключевых слов ──────────────────
    keywords_include = FILTERS.get("keywords_include", [])
    if keywords_include:
        if not any(kw.lower() in text_combined for kw in keywords_include):
            logger.debug(
                "Вакансия отсеяна — не найдены ключевые слова: «{}»",
                title,
            )
            return False

    return True


def filter_vacancies(vacancies: list[dict]) -> list[dict]:
    """Фильтрует список вакансий, оставляя только прошедшие все проверки.

    Args:
        vacancies: исходный список словарей-вакансий.

    Returns:
        Отфильтрованный список вакансий.
    """
    count_before = len(vacancies)

    try:
        result = [v for v in vacancies if is_valid_vacancy(v)]
    except Exception as exc:
        logger.error("Ошибка при фильтрации вакансий: {}", exc)
        return []

    count_after = len(result)
    logger.info(
        "Фильтрация завершена: {} → {} (отсеяно {})",
        count_before,
        count_after,
        count_before - count_after,
    )
    return result
