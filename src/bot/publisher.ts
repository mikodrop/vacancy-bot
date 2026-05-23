import { Bot, HttpError, TelegramError } from 'grammy';
import { config } from '../config/config.js';
import { logger } from '../utils/logger.js';

export class Publisher {
  private bot: Bot;

  constructor() {
    if (!config.BOT_TOKEN) {
      logger.error('BOT_TOKEN is missing in the configuration!');
    }
    this.bot = new Bot(config.BOT_TOKEN);
  }

  /**
   * Sends formatted HTML message to the Telegram channel.
   * Handles Rate Limits (Flood Retry) and other Telegram errors.
   */
  public async sendToChannel(text: string): Promise<boolean> {
    const channelId = config.CHANNEL_ID;
    if (!channelId) {
      logger.error('CHANNEL_ID is missing. Cannot publish message.');
      return false;
    }

    let retries = 3;
    while (retries > 0) {
      try {
        logger.debug(`Sending message to channel ${channelId}...`);
        await this.bot.api.sendMessage(channelId, text, {
          parse_mode: 'HTML',
          link_preview_options: {
            is_disabled: false // Keep link previews so the job site logo/preview shows
          }
        });
        logger.info(`Message published successfully to ${channelId}`);
        return true;
      } catch (error) {
        if (error instanceof TelegramError) {
          logger.error(`Telegram API Error (code ${error.error_code}): ${error.description}`);
          
          // Handle Flood Limit (429)
          if (error.error_code === 429) {
            const retryAfter = (error.parameters as any).retry_after || 10;
            logger.warn(`Rate limit hit. Sleeping for ${retryAfter + 1} seconds...`);
            await new Promise((resolve) => setTimeout(resolve, (retryAfter + 1) * 1000));
            retries--;
            continue;
          }
        } else if (error instanceof HttpError) {
          logger.error(`Network HTTP Error: ${error.message}`);
        } else {
          logger.error(error, 'Unexpected error while sending message to Telegram');
        }
        
        break; // Non-retryable error
      }
    }
    
    return false;
  }

  public async close(): Promise<void> {
    logger.debug('Publisher service closed');
  }
}
