import pino from 'pino';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const BASE_DIR = path.resolve(__dirname, '../..');

// Multi-stream logs: pretty console logs + file log
const transport = pino.transport({
  targets: [
    {
      target: 'pino-pretty',
      options: { colorize: true },
      level: process.env.LOG_LEVEL || 'info',
    },
    {
      target: 'pino/file',
      options: { destination: path.join(BASE_DIR, 'logs', 'bot.log') },
      level: process.env.LOG_LEVEL || 'info',
    }
  ]
});

export const logger = pino(transport);
export default logger;
