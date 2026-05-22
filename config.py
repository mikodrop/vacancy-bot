"""
Конфигурация проекта vacancy_bot.

Загружает переменные окружения из .env файла и предоставляет
все настройки приложения через модульные константы.
"""

import pathlib
from dotenv import load_dotenv
import os

# ── Пути проекта ──────────────────────────────────────────────
BASE_DIR = pathlib.Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ── Telegram Bot ──────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")

# ── Telethon (чтение TG-каналов) ─────────────────────────────
TG_API_ID: int = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH: str = os.getenv("TG_API_HASH", "")
TG_PHONE: str = os.getenv("TG_PHONE", "")

# ── VK API ────────────────────────────────────────────────────
VK_ACCESS_TOKEN: str = os.getenv("VK_ACCESS_TOKEN", "")
VK_API_VERSION: str = os.getenv("VK_API_VERSION", "5.131")

# ── SuperJob ──────────────────────────────────────────────────
SUPERJOB_SECRET: str = os.getenv("SUPERJOB_SECRET", "")

# ── Лимиты и параметры сессии ─────────────────────────────────
SALARY_MIN: int = int(os.getenv("SALARY_MIN", "30000"))
SCHEDULE_TYPE: str = os.getenv("SCHEDULE_TYPE", "remote")
MAX_PER_SESSION: int = int(os.getenv("MAX_PER_SESSION", "10"))
DELAY_BETWEEN_POSTS: int = int(os.getenv("DELAY_BETWEEN_POSTS", "5"))
HOURS_LOOKBACK: int = int(os.getenv("HOURS_LOOKBACK", "24"))

# ── Источники (включены / выключены) ─────────────────────────
SOURCES: dict[str, bool] = {
    "hh":       os.getenv("SOURCE_HH", "1") == "1",
    "trudvsem": os.getenv("SOURCE_TRUDVSEM", "1") == "1",
    "superjob": os.getenv("SOURCE_SUPERJOB", "0") == "1",
    "vk":       os.getenv("SOURCE_VK", "1") == "1",
    "tg":       os.getenv("SOURCE_TG", "1") == "1",
    "avito":    os.getenv("SOURCE_AVITO", "0") == "1",
    "habr":     os.getenv("SOURCE_HABR", "1") == "1",
}

# ── Фильтры вакансий ─────────────────────────────────────────
FILTERS: dict = {
    "schedule_keywords": [
        "remote",
        "удалённая",
        "удаленная",
        "дистанционная",
    ],
    "salary_min": SALARY_MIN,
    "currency": "RUR",
    "keywords_include": [],
    "keywords_exclude": [
        "вебкам",
        "вебкамера",
        "18+",
        "эротик",
        "МЛМ",
        "сетевой маркетинг",
        "инвестиц",
        "криптовалют",
        "крипто",
        "форекс",
        "бинарные опционы",
        "финансовый советник",
        "страховой агент",
    ],
}

# ── Мониторинг: Telegram-каналы ──────────────────────────────
TG_CHANNELS_TO_MONITOR: list[str] = [
    "@TGwork",
    "@udalenka_vacansii",
    "@remote_ru",
    "@jobremote",
    "@vdhl",
    "@work_editor",
    "@habrcareer",
    "@digital_jobz",
]

# ── Мониторинг: VK-группы ────────────────────────────────────
VK_GROUPS_TO_MONITOR: list[str] = [
    "remote_job_ru",
    "udalennaya_rabota",
    "it_remote_work",
    "freelance_remote",
    "vjob",
]

# ── Ротация User-Agent ───────────────────────────────────────
HEADERS_POOL: list[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
]

# ── Логирование ──────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ── База данных ──────────────────────────────────────────────
DB_PATH: pathlib.Path = BASE_DIR / "data" / "vacancies.db"
