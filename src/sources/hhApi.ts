import axios from 'axios';
import { config } from '../config/config.js';
import { logger } from '../utils/logger.js';
import { Vacancy } from '../db/database.js';

export async function fetchHhVacancies(): Promise<Vacancy[]> {
  const vacancies: Vacancy[] = [];
  const lookbackHours = config.HOURS_LOOKBACK;
  const dateFrom = new Date(Date.now() - lookbackHours * 60 * 60 * 1000).toISOString();
  
  logger.info(`HH API: Starting fetch (vacancies published since ${dateFrom})`);

  const url = 'https://api.hh.ru/vacancies';
  const perPage = 100;
  const maxPages = 5;

  for (let page = 0; page < maxPages; page++) {
    const randomUserAgent = config.HEADERS_POOL[Math.floor(Math.random() * config.HEADERS_POOL.length)];
    
    try {
      logger.debug(`HH API: Fetching page ${page}...`);
      const response = await axios.get(url, {
        params: {
          area: 113, // Russia
          schedule: 'remote',
          salary: config.FILTERS.salary_min,
          currency: 'RUR',
          only_with_salary: true,
          per_page: perPage,
          page: page,
          order_by: 'publication_time',
          date_from: dateFrom
        },
        headers: {
          'User-Agent': randomUserAgent
        },
        timeout: 10000
      });

      const items = response.data.items || [];
      if (items.length === 0) {
        logger.debug(`HH API: No vacancies returned on page ${page}. Stopping pagination.`);
        break;
      }

      for (const item of items) {
        vacancies.push({
          source: 'hh',
          vacancy_id: String(item.id),
          title: item.name,
          company: item.employer?.name || '',
          salary_from: item.salary?.from || null,
          salary_to: item.salary?.to || null,
          url: item.alternate_url,
          schedule: item.schedule?.name || 'Удалённая работа',
          area: item.area?.name || 'Россия',
          description: item.snippet?.responsibility || '',
          requirements: item.snippet?.requirement || '',
          published_at: item.published_at || ''
        });
      }

      const totalPages = response.data.pages || 1;
      if (page >= totalPages - 1) {
        break;
      }

    } catch (error: any) {
      logger.error(`HH API Error on page ${page}: ${error.message}`);
      break; // Exit loop on error
    }
  }

  logger.info(`HH API: Fetched ${vacancies.length} vacancies total.`);
  return vacancies;
}
