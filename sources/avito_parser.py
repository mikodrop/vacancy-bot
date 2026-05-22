"""
Парсер Авито — получение вакансий через HTML-парсинг.

⚠️  ОПЦИОНАЛЬНЫЙ МОДУЛЬ — ОТКЛЮЧЁН ПО УМОЛЧАНИЮ (SOURCE_AVITO=0).

Авито активно блокирует автоматический парсинг:
  - Капча после нескольких запросов
  - Блокировка по IP / fingerprint
  - Динамическая загрузка контента через JavaScript

Этот парсер работает как «best effort» — пытается получить данные,
но при любой ошибке (403, капча, изменение вёрстки) корректно
возвращает пустой список без прерывания работы остальных источников.

Рекомендуется использовать только для тестирования или как дополнительный
источник с ротацией IP (прокси).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import sys
from typing import Any

import aiohttp
from loguru import logger

# ── Гарантируем доступ к config из корня проекта ──────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import HEADERS_POOL  # noqa: E402

try:
    from bs4 import BeautifulSoup  # type: ignore[import-untyped]

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("beautifulsoup4 не установлен — парсинг Авито недоступен")

# ── Константы ────────────────────────────────────────────────
_AVITO_BASE_URL = "https://www.avito.ru"
_AVITO_VACANCIES_URL = f"{_AVITO_BASE_URL}/rossiya/vakansii"

# Параметры поиска: s=104 — сортировка по дате
_DEFAULT_PARAMS: dict[str, str] = {
    "s": "104",
}

# Задержка между запросами (секунды) — для снижения вероятности блокировки
_MIN_DELAY: float = 3.0
_MAX_DELAY: float = 7.0


def _get_random_headers() -> dict[str, str]:
    """
    Получить случайный набор HTTP-заголовков для маскировки запроса.

    Использует User-Agent из пула HEADERS_POOL (config.py).
    HEADERS_POOL — список строк User-Agent.
    """
    ua = random.choice(HEADERS_POOL) if HEADERS_POOL else (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    return {
        "User-Agent": ua,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }


def _parse_vacancy_items(html: str) -> list[dict[str, Any]]:
    """
    Разобрать HTML-страницу Авито и извлечь карточки вакансий.

    Авито может менять вёрстку, поэтому используем несколько
    стратегий поиска карточек.

    Args:
        html: HTML-контент страницы

    Returns:
        Список вакансий в унифицированном формате.
    """
    if not BS4_AVAILABLE:
        return []

    soup = BeautifulSoup(html, "lxml")
    vacancies: list[dict[str, Any]] = []

    # Стратегия 1: ищем элементы с data-marker='item'
    items = soup.find_all("div", attrs={"data-marker": "item"})

    if not items:
        # Стратегия 2: ищем по CSS-классу (Авито часто использует itmNmr* классы)
        items = soup.find_all("div", class_=lambda c: c and "item" in c.lower())

    if not items:
        logger.warning(
            "Авито: не найдено карточек вакансий — "
            "возможно, изменилась вёрстка или получена капча"
        )
        return []

    for item in items:
        try:
            vacancy = _parse_single_item(item)
            if vacancy:
                vacancies.append(vacancy)
        except Exception as exc:
            logger.debug("Авито: ошибка при разборе карточки: {}", exc)
            continue

    return vacancies


def _parse_single_item(item: Any) -> dict[str, Any] | None:
    """
    Разобрать одну карточку вакансии.

    Args:
        item: BeautifulSoup-элемент карточки

    Returns:
        Словарь вакансии или None при ошибке разбора.
    """
    # Заголовок: ищем ссылку с data-marker='item-title' или h3
    title_elem = item.find(attrs={"data-marker": "item-title"})
    if not title_elem:
        title_elem = item.find("a", attrs={"itemprop": "url"})
    if not title_elem:
        title_elem = item.find("h3")
    if not title_elem:
        title_elem = item.find("a")

    if not title_elem:
        return None

    title = title_elem.get_text(strip=True)
    if not title:
        return None

    # Ссылка на вакансию
    link = title_elem.get("href", "")
    if link and not link.startswith("http"):
        link = f"{_AVITO_BASE_URL}{link}"

    # Зарплата / цена
    salary_from: int | None = None
    salary_to: int | None = None

    price_elem = item.find(attrs={"data-marker": "item-price"})
    if not price_elem:
        price_elem = item.find("meta", attrs={"itemprop": "price"})
    if not price_elem:
        # Ищем span с ценой по контенту
        price_elem = item.find("span", class_=lambda c: c and "price" in c.lower())

    if price_elem:
        price_text = price_elem.get("content", "") or price_elem.get_text(strip=True)
        price_text = price_text.replace("\u00a0", "").replace(" ", "")
        # Извлекаем число
        import re

        price_match = re.search(r"(\d+)", price_text)
        if price_match:
            try:
                salary_from = int(price_match.group(1))
                # Адекватный диапазон зарплаты
                if salary_from < 1_000 or salary_from > 1_000_000:
                    salary_from = None
            except ValueError:
                salary_from = None

    # Описание (краткое, из карточки)
    description = ""
    desc_elem = item.find(attrs={"data-marker": "item-description"})
    if desc_elem:
        description = desc_elem.get_text(strip=True)

    # Уникальный ID на основе ссылки или заголовка
    id_source = link if link else title
    vacancy_id = hashlib.sha256(id_source.encode("utf-8")).hexdigest()[:16]

    return {
        "source": "avito",
        "vacancy_id": vacancy_id,
        "title": title,
        "company": "",
        "salary_from": salary_from,
        "salary_to": salary_to,
        "description": description,
        "url": link,
        "schedule": "",
        "area": "",
        "published_at": "",
        "extra": {},
    }


async def fetch_avito_vacancies() -> list[dict[str, Any]]:
    """
    Главная функция модуля — получить вакансии с Авито.

    ⚠️  Этот парсер опциональный и может быть заблокирован Авито.
    При любой ошибке возвращает пустой список и логирует предупреждение.

    Returns:
        Список вакансий в унифицированном формате.
    """
    if not BS4_AVAILABLE:
        logger.warning("beautifulsoup4 не установлен — парсинг Авито пропущен")
        return []

    logger.info("Авито: начинаем парсинг вакансий...")

    # Задержка перед запросом (имитация поведения пользователя)
    delay = random.uniform(_MIN_DELAY, _MAX_DELAY)
    logger.debug("Авито: задержка перед запросом {:.1f} сек", delay)
    await asyncio.sleep(delay)

    headers = _get_random_headers()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _AVITO_VACANCIES_URL,
                params=_DEFAULT_PARAMS,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=True,
            ) as resp:
                if resp.status == 403:
                    logger.warning(
                        "Авито: доступ запрещён (403) — "
                        "вероятно, обнаружен автоматический запрос"
                    )
                    return []

                if resp.status == 429:
                    logger.warning("Авито: слишком много запросов (429)")
                    return []

                if resp.status != 200:
                    logger.warning("Авито: неожиданный HTTP-статус {}", resp.status)
                    return []

                html = await resp.text()

                # Проверка на капчу
                if "captcha" in html.lower() or "blocked" in html.lower():
                    logger.warning(
                        "Авито: обнаружена капча или блокировка — "
                        "парсинг невозможен"
                    )
                    return []

                vacancies = _parse_vacancy_items(html)
                logger.info("Авито: найдено {} вакансий", len(vacancies))
                return vacancies

    except aiohttp.ClientError as exc:
        logger.warning("Авито: сетевая ошибка — {}", exc)
        return []
    except asyncio.TimeoutError:
        logger.warning("Авито: таймаут запроса")
        return []
    except Exception as exc:
        logger.error("Авито: непредвиденная ошибка — {}", exc)
        return []
