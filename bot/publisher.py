"""
Модуль публикации вакансий в Telegram-канал.

Использует aiogram 3.x Bot для отправки HTML-сообщений.
Обрабатывает ошибки Telegram API: невалидный текст, rate-limit,
сетевые сбои.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import BOT_TOKEN, CHANNEL_ID

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from loguru import logger


class Publisher:
    """Публикатор сообщений в Telegram-канал через aiogram Bot.

    Attributes:
        bot: экземпляр aiogram.Bot для отправки сообщений.
        channel_id: ID целевого Telegram-канала.
    """

    def __init__(self) -> None:
        """Инициализирует Publisher с токеном бота и ID канала из конфига."""
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN не задан — публикация невозможна")
        if not CHANNEL_ID:
            logger.error("CHANNEL_ID не задан — публикация невозможна")

        self.bot = Bot(token=BOT_TOKEN)
        self.channel_id: str = CHANNEL_ID

    async def send_to_channel(self, text: str) -> bool:
        """Отправляет HTML-сообщение в Telegram-канал.

        Обрабатывает типичные ошибки Telegram API:
        - TelegramBadRequest — невалидный текст / формат
        - TelegramRetryAfter — превышен rate-limit (ждём и повторяем)
        - Прочие исключения — логируем и возвращаем False

        Args:
            text: HTML-текст сообщения для отправки.

        Returns:
            True при успешной отправке, False при ошибке.
        """
        try:
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            logger.info("Сообщение успешно отправлено в канал {}", self.channel_id)
            return True

        except TelegramRetryAfter as exc:
            wait_seconds = exc.retry_after
            logger.warning(
                "Telegram rate-limit: ждём {} сек. перед повтором",
                wait_seconds,
            )
            try:
                await asyncio.sleep(wait_seconds)
                await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                logger.info(
                    "Сообщение отправлено после ожидания rate-limit"
                )
                return True
            except Exception as retry_exc:
                logger.error(
                    "Ошибка при повторной отправке после rate-limit: {}",
                    retry_exc,
                )
                return False

        except TelegramBadRequest as exc:
            logger.error(
                "Telegram отклонил сообщение (BadRequest): {}",
                exc.message,
            )
            return False

        except Exception as exc:
            logger.error(
                "Неожиданная ошибка при отправке в канал: {}",
                exc,
            )
            return False

    async def close(self) -> None:
        """Закрывает сессию бота и освобождает ресурсы."""
        try:
            await self.bot.session.close()
            logger.debug("Сессия бота закрыта")
        except Exception as exc:
            logger.error("Ошибка при закрытии сессии бота: {}", exc)
