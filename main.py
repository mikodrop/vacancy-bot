# -*- coding: utf-8 -*-
"""
Главная точка входа бота публикации вакансий.

Поддерживает два режима:
- Тестовый (--test): однократный запуск daily_job или тест конкретного источника
- Продакшн: запуск APScheduler с расписанием (09:00 и 18:00 по Москве)

Использование:
    python main.py                  — запуск по расписанию
    python main.py --test           — однократный сбор всех источников
    python main.py --test --source hh  — тест только HeadHunter
"""

import asyncio
import argparse
import os
import sys

from loguru import logger

# Гарантируем, что корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LOG_LEVEL, BASE_DIR
from db.database import Database
from scheduler.tasks import daily_job, test_source


def _setup_logging() -> None:
    """
    Настраивает loguru: файловый хендлер с ротацией и уровень логирования.

    - Файл: logs/bot.log
    - Ротация: 10 МБ
    - Хранение: 7 дней
    - Формат: время | уровень | модуль:функция:строка — сообщение
    """
    logs_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    log_file = os.path.join(logs_dir, "bot.log")

    # Убираем стандартный stderr-хендлер и добавляем свои
    logger.remove()

    # Консольный вывод
    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # Файловый лог
    logger.add(
        log_file,
        level=LOG_LEVEL,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{module}:{function}:{line} — "
            "{message}"
        ),
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        enqueue=True,       # потокобезопасная запись
        backtrace=True,     # расширенные трейсбеки
        diagnose=True,      # диагностика переменных в трейсбеках
    )


def _parse_args() -> argparse.Namespace:
    """
    Парсит аргументы командной строки.

    Returns:
        Namespace с полями test (bool) и source (str | None).
    """
    parser = argparse.ArgumentParser(
        description="Telegram-бот для автоматической публикации вакансий",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  python main.py                   Запуск по расписанию\n"
            "  python main.py --test            Однократный сбор и публикация\n"
            "  python main.py --test --source hh   Тест только HeadHunter\n"
        ),
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Запустить daily_job() один раз и завершиться",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="С --test: протестировать только указанный источник "
             "(hh, trudvsem, superjob, tg, vk, habr, avito)",
    )
    return parser.parse_args()


async def _run_test(source_name: str | None) -> None:
    """
    Запускает тестовый режим — однократный сбор вакансий.

    Args:
        source_name: имя конкретного источника или None для полного цикла.
    """
    if source_name:
        logger.info(f"Тестовый режим: источник '{source_name}'")
        await test_source(source_name)
    else:
        logger.info("Тестовый режим: полный цикл daily_job()")
        await daily_job()


async def _run_scheduler() -> None:
    """
    Запускает APScheduler с расписанием и ожидает сигнал завершения.

    Вакансии собираются и публикуются дважды в день:
    - 09:00 (Europe/Moscow)
    - 18:00 (Europe/Moscow)
    """
    # Ленивый импорт — APScheduler нужен только в продакшн-режиме
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error(
            "APScheduler не установлен. "
            "Установите: pip install apscheduler>=3.10"
        )
        sys.exit(1)

    # Инициализируем БД при старте (создаём таблицы)
    db = Database()
    try:
        await db.init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Не удалось инициализировать БД: {e}")
        sys.exit(1)
    finally:
        await db.close()

    # Настраиваем планировщик
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    scheduler.add_job(
        daily_job,
        trigger=CronTrigger(hour=9, minute=0),
        id="daily_job_morning",
        name="Утренний сбор вакансий (09:00)",
        misfire_grace_time=3600,
        replace_existing=True,
    )

    scheduler.add_job(
        daily_job,
        trigger=CronTrigger(hour=18, minute=0),
        id="daily_job_evening",
        name="Вечерний сбор вакансий (18:00)",
        misfire_grace_time=3600,
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Бот запущен, ожидание задач по расписанию...")
    logger.info("Расписание: 09:00 и 18:00 (Europe/Moscow)")
    logger.info("Для остановки нажмите Ctrl+C")

    # Держим event loop активным
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен сигнал завершения")
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Планировщик остановлен")


def main() -> None:
    """
    Точка входа: парсит аргументы, настраивает логирование и запускает
    нужный режим (тест или продакшн).
    """
    _setup_logging()
    args = _parse_args()

    logger.info("Telegram Vacancy Bot — запуск")

    try:
        if args.test:
            asyncio.run(_run_test(args.source))
        else:
            asyncio.run(_run_scheduler())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:
        logger.exception(f"Необработанная ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
