import axios from 'axios';
import { config } from '../config/config.js';
import { logger } from '../utils/logger.js';
import { Vacancy } from '../db/database.js';

export async function fetchSuperjobVacancies(): Promise<Vacancy[]> {
  const vacancies: Vacancy[] = [];

  if (!config.SUPERJOB_SECRET) {
    logger.debug('SuperJob API: SUPERJOB_SECRET is not configured. Skipping SuperJob fetch.');
    return [];
  }

  logger.info('SuperJob API: Starting fetch...');
  const url = 'https://api.superjob.ru/2.0/vacancies/';

  try {
    const response = await axios.get(url, {
      params: {
        't[0]': 4, // Remote work code
        payment_from: config.FILTERS.salary_min,
        currency: 'rub',
        count: 50
      },
      headers: {
        'X-Api-App-Id': config.SUPERJOB_SECRET
      },
      timeout: 10000
    });

    const objects = response.data?.objects || [];
    for (const item of objects) {
      vacancies.push({
        source: 'superjob',
        vacancy_id: String(item.id),
        title: item.profession || '',
        company: item.client?.title || '',
        salary_from: item.payment_from || null,
        salary_to: item.payment_to || null,
        url: item.link || '',
        schedule: item.type_of_work?.title || 'Удалённая работа',
        area: item.town?.title || 'РФ',
        description: item.vacancyRich || item.candidat || '',
        requirements: item.candidat || ''
      });
    }

  } catch (error: any) {
    logger.error(`SuperJob API Error: ${error.message}`);
  }

  logger.info(`SuperJob API: Fetched ${vacancies.length} vacancies.`);
  return vacancies;
}
