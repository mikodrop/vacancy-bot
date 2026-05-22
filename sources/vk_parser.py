"""
Парсер ВКонтакте — получение вакансий из стен VK-групп через API.

Использует официальное VK API v5.131:
  - utils.resolveScreenName — получение ID группы по короткому имени
  - wall.get — получение постов со стены

Все запросы асинхронные через aiohttp. Каждая группа обрабатывается
независимо, ошибки в одной не блокируют остальные.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from loguru import logger

# ── Гарантируем доступ к config из корня проекта ──────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (  # noqa: E402
    HOURS_LOOKBACK,
    VK_ACCESS_TOKEN,
    VK_API_VERSION,
    VK_GROUPS_TO_MONITOR,
)

# ── Константы VK API ─────────────────────────────────────────
_VK_API_BASE = "https://api.vk.com/method"

# Паттерн для извлечения URL
_URL_PATTERN = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

# Паттерн для поиска зарплаты: «50000», «50 000», «50к», «50k», «50 тыс»
_SALARY_CONTEXT_PATTERN = re.compile(
    r"(?:зарплата|оплата|оклад|з/?п|зп|ставка|доход)"
    r".{0,50}"
    r"(\d[\d\s]*\d|\d+)"
    r"\s*(000|к|k|тыс\.?|руб\.?|₽)?",
    re.IGNORECASE,
)
_SALARY_RUB_PATTERN = re.compile(
    r"(\d[\d\s]*\d|\d+)\s*(000|к|k|тыс\.?)?\s*(?:₽|руб)",
    re.IGNORECASE,
)


def _extract_salary(text: str) -> tuple[int | None, int | None]:
    """
    Извлечь диапазон зарплаты из текста поста.

    Returns:
        Кортеж (salary_from, salary_to). Если не найдено — (None, None).
    """
    matches = _SALARY_CONTEXT_PATTERN.findall(text)
    if not matches:
        matches = _SALARY_RUB_PATTERN.findall(text)
    if not matches:
        return None, None

    values: list[int] = []
    for raw_number, suffix in matches[:4]:
        try:
            number = int(raw_number.replace(" ", "").replace("\u00a0", ""))
        except ValueError:
            continue

        suffix_lower = suffix.lower().rstrip(".")
        if suffix_lower in ("к", "k", "тыс"):
            number *= 1000

        if 5_000 <= number <= 1_000_000:
            values.append(number)

    if not values:
        return None, None
    if len(values) == 1:
        return values[0], None
    return min(values), max(values)


async def _vk_api_request(
    session: aiohttp.ClientSession,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Выполнить запрос к VK API.

    Args:
        session: aiohttp-сессия
        method: имя метода VK API (например 'wall.get')
        params: параметры запроса

    Returns:
        Словарь с ответом или None при ошибке.
    """
    params.setdefault("access_token", VK_ACCESS_TOKEN)
    params.setdefault("v", VK_API_VERSION)

    url = f"{_VK_API_BASE}/{method}"

    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.error("VK API {}: HTTP {}", method, resp.status)
                return None

            data = await resp.json()

            if "error" in data:
                error_info = data["error"]
                logger.error(
                    "VK API {} ошибка {}: {}",
                    method,
                    error_info.get("error_code"),
                    error_info.get("error_msg"),
                )
                return None

            return data.get("response")

    except aiohttp.ClientError as exc:
        logger.error("Сетевая ошибка VK API {}: {}", method, exc)
        return None
    except Exception as exc:
        logger.error("Непредвиденная ошибка VK API {}: {}", method, exc)
        return None


async def _resolve_group_id(
    session: aiohttp.ClientSession,
    group_name: str,
) -> int | None:
    """
    Получить числовой ID группы по короткому имени через utils.resolveScreenName.

    Args:
        group_name: короткое имя группы (без vk.com/)

    Returns:
        Числовой ID группы или None.
    """
    result = await _vk_api_request(
        session,
        "utils.resolveScreenName",
        {"screen_name": group_name},
    )

    if not result:
        # Пустой ответ — группа не найдена
        logger.warning("VK: группа '{}' не найдена через resolveScreenName", group_name)
        return None

    if result.get("type") not in ("group", "page"):
        logger.warning(
            "VK: '{}' — не группа (тип: {})",
            group_name,
            result.get("type"),
        )
        return None

    group_id = result.get("object_id")
    logger.debug("VK: группа '{}' → ID {}", group_name, group_id)
    return group_id


async def fetch_vk_group_posts(
    group_name: str,
    session: aiohttp.ClientSession | None = None,
) -> list[dict[str, Any]]:
    """
    Получить посты вакансий из стены VK-группы.

    Получает последние 50 постов через wall.get, фильтрует по дате
    (последние HOURS_LOOKBACK часов), извлекает зарплаты и ссылки.

    Args:
        group_name: короткое имя группы (например, 'remote_job_ru')
        session: опциональная aiohttp-сессия (если None — создаётся новая)

    Returns:
        Список вакансий в унифицированном формате.
    """
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()

    vacancies: list[dict[str, Any]] = []

    try:
        # Получаем ID группы
        group_id = await _resolve_group_id(session, group_name)
        if group_id is None:
            return []

        # Получаем посты со стены
        result = await _vk_api_request(
            session,
            "wall.get",
            {
                "owner_id": f"-{group_id}",
                "count": 50,
                "filter": "owner",
            },
        )

        if not result or "items" not in result:
            logger.warning("VK: пустой ответ wall.get для группы '{}'", group_name)
            return []

        # Порог по дате — только посты за последние HOURS_LOOKBACK часов
        cutoff_ts = (
            datetime.now(tz=timezone.utc) - timedelta(hours=HOURS_LOOKBACK)
        ).timestamp()

        for post in result["items"]:
            # Фильтр по дате
            post_date = post.get("date", 0)
            if post_date < cutoff_ts:
                continue

            text = post.get("text", "")
            if not text or len(text.strip()) < 30:
                continue

            # Заголовок — первая непустая строка
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            title = lines[0] if lines else text[:80]
            if len(title) > 120:
                title = title[:117] + "..."

            # Зарплата
            salary_from, salary_to = _extract_salary(text)

            # Ссылки из текста
            urls = _URL_PATTERN.findall(text)

            # Ссылки из вложений
            for attachment in post.get("attachments", []):
                if attachment.get("type") == "link":
                    link_url = attachment.get("link", {}).get("url", "")
                    if link_url:
                        urls.append(link_url)

            # Прямая ссылка на пост VK
            post_id = post.get("id", 0)
            vk_post_url = f"https://vk.com/wall-{group_id}_{post_id}"

            # Первый найденный URL или ссылка на пост
            url = urls[0] if urls else vk_post_url

            vacancy: dict[str, Any] = {
                "source": "vk",
                "vacancy_id": str(post_id),
                "title": title,
                "company": "",
                "salary_from": salary_from,
                "salary_to": salary_to,
                "description": text,
                "url": url,
                "schedule": "",
                "area": "",
                "published_at": datetime.fromtimestamp(
                    post_date, tz=timezone.utc
                ).isoformat(),
                "extra": {
                    "group": group_name,
                    "vk_post_url": vk_post_url,
                },
            }
            vacancies.append(vacancy)

        logger.info(
            "VK группа '{}': найдено {} записей за последние {} ч",
            group_name,
            len(vacancies),
            HOURS_LOOKBACK,
        )

    except Exception as exc:
        logger.error("Ошибка при парсинге VK-группы '{}': {}", group_name, exc)
    finally:
        if own_session and session:
            await session.close()

    return vacancies


async def fetch_vk_vacancies() -> list[dict[str, Any]]:
    """
    Главная функция модуля — собрать вакансии из всех VK-групп.

    Проверяет наличие VK_ACCESS_TOKEN. Если токен не задан —
    возвращает пустой список с предупреждением.

    Returns:
        Агрегированный список вакансий из всех VK-групп.
    """
    if not VK_ACCESS_TOKEN:
        logger.warning(
            "VK_ACCESS_TOKEN не задан — парсинг VK-групп отключён"
        )
        return []

    if not VK_GROUPS_TO_MONITOR:
        logger.info("Список VK_GROUPS_TO_MONITOR пуст — нечего парсить")
        return []

    all_vacancies: list[dict[str, Any]] = []

    async with aiohttp.ClientSession() as session:
        for group_name in VK_GROUPS_TO_MONITOR:
            try:
                posts = await fetch_vk_group_posts(group_name, session=session)
                all_vacancies.extend(posts)
            except Exception as exc:
                logger.error(
                    "Ошибка при обработке VK-группы '{}': {}",
                    group_name,
                    exc,
                )

    logger.info(
        "Итого из VK собрано {} записей из {} групп",
        len(all_vacancies),
        len(VK_GROUPS_TO_MONITOR),
    )
    return all_vacancies
