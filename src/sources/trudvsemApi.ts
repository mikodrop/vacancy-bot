import axios from 'axios';
import { config } from '../config/config.js';
import { logger } from '../utils/logger.js';
import { Vacancy } from '../db/database.js';

export async function fetchTrudvsemVacancies(): Promise<Vacancy[]> {
  const vacancies: Vacancy[] = [];
  logger.info('TrudVsem API: Starting fetch...');

  const baseUrl = 'https://opendata.trudvsem.ru/api/v1/vacancies';
  const limit = 50;
  const maxPages = 3;

  for (let page = 0; page < maxPages; page++) {
    const offset = page * limit;
    
    try {
      logger.debug(`TrudVsem API: Fetching offset ${offset}...`);
      const response = await axios.get(baseUrl, {
        params: {
          salaryFrom: config.FILTERS.salary_min,
          isRemote: 'true',
          limit: limit,
          offset: offset
        },
        timeout: 15000
      });

      // API structure is: { results: { vacancies: [ { vacancy: {...} }, ... ] } }
      const results = response.data?.results;
      const rawList = results?.vacancies || [];

      if (rawList.length === 0) {
        logger.debug(`TrudVsem API: No vacancies returned on offset ${offset}. Stopping pagination.`);
        break;
      }

      for (const item of rawList) {
        const v = item.vacancy;
        if (!v) continue;

        // Force schedule to be 'Удалённая работа' to pass the filter checks
        vacancies.push({
          source: 'trudvsem',
          vacancy_id: String(v.id),
          title: v['job-name'] || v.label || '', // Hyphenated key in TrudVsem API
          company: v.company?.name || '',
          salary_from: Number(v.salary_min) || null,
          salary_to: Number(v.salary_max) || null,
          url: v.vacancies_url || '',
          schedule: 'Удалённая работа', // Hardcoded as in Python to satisfy filter checks
          area: v.region?.name || 'РФ',
          description: v.duty || '',
          requirements: v.requirement && typeof v.requirement === 'object'
            ? `${(v.requirement as any).education || ''} ${(v.requirement as any).qualifications || ''}`.trim()
            : (v.requirement || ''),
          published_at: v.creation_date || ''
        });
      }

    } catch (error: any) {
      logger.error(`TrudVsem API Error on offset ${offset}: ${error.message}`);
      break;
    }
  }

  // Adjust keys if there are typos
  vacancies.forEach(v => {
    if ((v as any).title === undefined) {
      v.title = '';
    }
  });

  logger.info(`TrudVsem API: Fetched ${vacancies.length} vacancies.`);
  return vacancies;
}
