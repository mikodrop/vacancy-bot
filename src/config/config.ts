import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

// Resolve directory paths in ES Modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const BASE_DIR = path.resolve(__dirname, '../..');

// Load environment variables
dotenv.config({ path: path.join(BASE_DIR, '.env') });

// Ensure required directories exist
const DATA_DIR = path.join(BASE_DIR, 'data');
const LOGS_DIR = path.join(BASE_DIR, 'logs');

if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}
if (!fs.existsSync(LOGS_DIR)) {
  fs.mkdirSync(LOGS_DIR, { recursive: true });
}

export const config = {
  BASE_DIR,
  DB_PATH: path.join(DATA_DIR, 'vacancies.db'),
  LOG_LEVEL: process.env.LOG_LEVEL || 'info',
  
  // Telegram Bot Credentials
  BOT_TOKEN: process.env.BOT_TOKEN || '',
  CHANNEL_ID: process.env.CHANNEL_ID || '',

  // Telethon / GramJS MTProto Credentials
  TG_API_ID: Number(process.env.TG_API_ID) || 0,
  TG_API_HASH: process.env.TG_API_HASH || '',
  TG_PHONE: process.env.TG_PHONE || '',

  // VK API
  VK_ACCESS_TOKEN: process.env.VK_ACCESS_TOKEN || '',
  VK_API_VERSION: process.env.VK_API_VERSION || '5.131',

  // SuperJob Secret
  SUPERJOB_SECRET: process.env.SUPERJOB_SECRET || '',

  // Limits
  MAX_PER_SESSION: Number(process.env.MAX_PER_SESSION) || 10,
  DELAY_BETWEEN_POSTS: Number(process.env.DELAY_BETWEEN_POSTS) || 5, // in seconds
  HOURS_LOOKBACK: Number(process.env.HOURS_LOOKBACK) || 24,

  // Enabled sources
  SOURCES: {
    hh: process.env.SOURCE_HH !== '0',
    trudvsem: process.env.SOURCE_TRUDVSEM !== '0',
    superjob: process.env.SOURCE_SUPERJOB === '1',
    vk: process.env.SOURCE_VK === '1',
    tg: process.env.SOURCE_TG === '1',
    avito: process.env.SOURCE_AVITO === '1',
    habr: process.env.SOURCE_HABR !== '0',
  },

  // Filters configurations
  FILTERS: {
    schedule: ['remote', 'удалённая', 'удаленная', 'дистанционная'],
    salary_min: Number(process.env.SALARY_MIN) || 30000,
    keywords_include: [] as string[],
    keywords_exclude: [
      'вебкам', 'вебкамера', '18+', 'эротик', 'млм', 'сетевой маркетинг', 
      'инвестиц', 'криптовалют', 'крипто', 'форекс', 'бинарные опционы', 
      'финансовый советник', 'страховой агент', 'агент по страхованию',
      'ставки', 'казино', 'вулкан', 'пирамида'
    ],
  },

  // Targets to monitor
  TG_CHANNELS_TO_MONITOR: [
    '@TGwork', '@udalenka_vacansii', '@remote_ru', '@jobremote', 
    '@vdhl', '@work_editor', '@habrcareer', '@digital_jobz'
  ],
  VK_GROUPS_TO_MONITOR: [
    'remote_job_ru', 'udalennaya_rabota', 'it_remote_work', 
    'freelance_remote', 'vjob'
  ],

  // Rotation User-Agents for HH and Avito
  HEADERS_POOL: [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'TelegramJobPublisher/1.0 (admin@jobpublisher.ru)' // Custom UA required by HH API
  ]
};
