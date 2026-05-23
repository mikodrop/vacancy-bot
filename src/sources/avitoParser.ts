import { logger } from '../utils/logger.js';
import { Vacancy } from '../db/database.js';

export async function fetchAvitoVacancies(): Promise<Vacancy[]> {
  logger.debug('Avito Parser: Avito parser is disabled by default due to strict anti-scraping blocks.');
  return [];
}
