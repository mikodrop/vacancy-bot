import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import readline from 'readline';
import { TelegramClient } from 'telegram';
import { StringSession } from 'telegram/sessions/index.js';
import { config } from '../config/config.js';
import { logger } from '../utils/logger.js';
import { Vacancy } from '../db/database.js';

const sessionFilePath = path.join(config.BASE_DIR, 'data/tg_session.txt');

// Readline helper for interactive logins
function askQuestion(query: string): Promise<string> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) =>
    rl.question(query, (ans) => {
      rl.close();
      resolve(ans.trim());
    })
  );
}

export async function fetchTgVacancies(): Promise<Vacancy[]> {
  const vacancies: Vacancy[] = [];

  if (config.TG_API_ID === 0 || !config.TG_API_HASH) {
    logger.debug('Telegram Client: TG_API_ID or TG_API_HASH is not configured. Skipping TG channels fetch.');
    return [];
  }

  logger.info('Telegram Client: Starting fetch from channels...');

  // Initialize StringSession
  let sessionString = '';
  if (fs.existsSync(sessionFilePath)) {
    try {
      sessionString = fs.readFileSync(sessionFilePath, 'utf-8').trim();
    } catch (e: any) {
      logger.error(`Failed to read session file: ${e.message}`);
    }
  }

  const stringSession = new StringSession(sessionString);
  const client = new TelegramClient(stringSession, config.TG_API_ID, config.TG_API_HASH, {
    connectionRetries: 5,
  });

  try {
    // Start client (this handles login interactively if session is expired/missing)
    await client.start({
      phoneNumber: async () => config.TG_PHONE || (await askQuestion('Please enter your Telegram phone number (e.g., +79991234567): ')),
      password: async () => await askQuestion('Please enter your Telegram 2FA password: '),
      phoneCode: async () => await askQuestion('Please enter the login code you received: '),
      onError: (err) => logger.error(`Telegram Client connection error: ${err.message}`)
    });

    // Save session string for next times
    const savedSession = client.session.save() as unknown as string;
    if (savedSession) {
      fs.writeFileSync(sessionFilePath, savedSession, 'utf-8');
    }

    logger.debug('Telegram Client: Connected and authenticated successfully.');

    const lookbackHours = config.HOURS_LOOKBACK;
    const cutoffTime = Math.floor((Date.now() - lookbackHours * 60 * 60 * 1000) / 1000); // Unix timestamp in seconds

    for (const channelName of config.TG_CHANNELS_TO_MONITOR) {
      try {
        logger.debug(`Telegram Client: Fetching posts from channel "${channelName}"...`);
        
        // Get messages from channel entity
        const messages = await client.getMessages(channelName, {
          limit: 50
        });

        logger.debug(`Telegram Client: Found ${messages.length} posts in "${channelName}".`);

        for (const msg of messages) {
          // GramJS messages sometimes have no text (media only) or are service messages
          if (!msg.message || !msg.date || msg.date < cutoffTime) {
            continue;
          }

          const text = msg.message;
          
          // Generate unique ID based on first 100 characters of text hash
          const textPrefix = text.slice(0, 100);
          const md5Hash = crypto.createHash('md5').update(textPrefix).digest('hex');

          // Extract first line as title
          const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
          const title = lines[0] ? (lines[0].length > 80 ? lines[0].slice(0, 80) + '...' : lines[0]) : 'Вакансия из Telegram';

          // Parse salary from text via regex
          let salaryFrom: number | null = null;
          let salaryTo: number | null = null;

          const salaryRangeRegex = /(?:зп|зарплата|оплата|от|до)?\s*(\d+[\s\d]*)\s*(?:-|до)\s*(\d+[\s\d]*)\s*(?:руб|₽|rur|к|k|тыс)/i;
          const rangeMatch = text.match(salaryRangeRegex);

          if (rangeMatch) {
            salaryFrom = parseNumber(rangeMatch[1]);
            salaryTo = parseNumber(rangeMatch[2]);
          } else {
            const singleSalaryRegex = /(?:зп|зарплата|оплата|от|до)?\s*(\d+[\s\d]*)\s*(?:руб|₽|rur|к|k|тыс)/i;
            const singleMatch = text.match(singleSalaryRegex);
            if (singleMatch) {
              const val = parseNumber(singleMatch[1]);
              if (text.toLowerCase().includes('от')) {
                salaryFrom = val;
              } else if (text.toLowerCase().includes('до')) {
                salaryTo = val;
              } else {
                salaryFrom = val;
              }
            }
          }

          // Extract URLs from message entities
          let externalUrl = `https://t.me/${channelName.replace('@', '')}/${msg.id}`;
          if (msg.entities) {
            for (const entity of msg.entities) {
              if (entity.className === 'MessageEntityTextUrl') {
                externalUrl = (entity as any).url;
                break;
              } else if (entity.className === 'MessageEntityUrl') {
                const offset = entity.offset;
                const length = entity.length;
                externalUrl = text.slice(offset, offset + length);
                break;
              }
            }
          }

          vacancies.push({
            source: 'tg',
            vacancy_id: md5Hash,
            title: title,
            company: '', // Usually not explicitly tag-formatted in plain posts
            salary_from: salaryFrom,
            salary_to: salaryTo,
            url: externalUrl,
            schedule: 'Удалённая работа', // Channels monitored are remote-work channels
            area: 'РФ',
            description: text,
            requirements: '',
            published_at: new Date(msg.date * 1000).toISOString()
          });
        }
      } catch (err: any) {
        logger.error(`Telegram Client: Error parsing channel "${channelName}": ${err.message}`);
      }
    }
  } catch (error: any) {
    logger.error(`Telegram Client Connection Error: ${error.message}`);
  } finally {
    // Close connection safely
    try {
      await client.disconnect();
      logger.debug('Telegram Client: Disconnected safely.');
    } catch (e: any) {
      logger.error(`Failed to disconnect Telegram Client: ${e.message}`);
    }
  }

  logger.info(`Telegram Client: Fetched ${vacancies.length} vacancies total.`);
  return vacancies;
}

function parseNumber(text: string): number {
  let valStr = text.toLowerCase().replace(/\s/g, '');
  let multiplier = 1;

  if (valStr.endsWith('к') || valStr.endsWith('k')) {
    multiplier = 1000;
    valStr = valStr.slice(0, -1);
  } else if (valStr.endsWith('тыс') || valStr.endsWith('тысяч')) {
    multiplier = 1000;
    valStr = valStr.replace(/(тыс|тысяч)/g, '');
  }

  const num = Number(valStr);
  return isNaN(num) ? 0 : num * multiplier;
}
