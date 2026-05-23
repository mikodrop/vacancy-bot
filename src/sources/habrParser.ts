import axios from 'axios';
import { XMLParser } from 'fast-xml-parser';
import crypto from 'crypto';
import { config } from '../config/config.js';
import { logger } from '../utils/logger.js';
import { Vacancy } from '../db/database.js';

export async function fetchHabrVacancies(): Promise<Vacancy[]> {
  const vacancies: Vacancy[] = [];
  logger.info('Habr RSS: Starting fetch...');

  const rssUrl = 'https://career.habr.com/vacancies/rss?schedule[]=remote&with_salary=1';
  
  try {
    const response = await axios.get(rssUrl, {
      timeout: 10000,
      headers: {
        'User-Agent': config.HEADERS_POOL[0]
      }
    });

    const parser = new XMLParser({
      ignoreAttributes: false,
      attributeNamePrefix: '@_'
    });
    const jsonObj = parser.parse(response.data);
    const channel = jsonObj?.rss?.channel;
    let items = channel?.item || [];

    // Ensure items is an array (fast-xml-parser might parse a single item as an object)
    if (!Array.isArray(items)) {
      items = [items];
    }

    logger.debug(`Habr RSS: Found ${items.length} raw feed items.`);

    const lookbackHours = config.HOURS_LOOKBACK;
    const cutoffTime = Date.now() - lookbackHours * 60 * 60 * 1000;

    for (const item of items) {
      if (!item.link) continue;

      // Parse pubDate
      const pubDateStr = item.pubDate || item.pubdate;
      const pubTime = pubDateStr ? new Date(pubDateStr).getTime() : Date.now();

      if (pubTime < cutoffTime) {
        // Skip older vacancies
        continue;
      }

      // Generate vacancy_id from link hash
      const md5Hash = crypto.createHash('md5').update(item.link).digest('hex');

      // In Habr RSS, the author is usually the company name.
      const company = item.author || item['dc:creator'] || '';

      // Try to parse salary from title if possible (e.g., "Web Developer (от 150 000 руб.)")
      let salaryFrom: number | null = null;
      let salaryTo: number | null = null;
      const title = item.title || '';
      
      const salaryRegex = /(?:от|до)?\s*(\d+[\s\d]*)\s*(?:-|до)\s*(\d+[\s\d]*)\s*(?:руб|₽|rur)/i;
      const match = title.match(salaryRegex);
      if (match) {
        salaryFrom = Number(match[1].replace(/\s/g, ''));
        salaryTo = Number(match[2].replace(/\s/g, ''));
      } else {
        const singleSalaryRegex = /(?:от|до)?\s*(\d+[\s\d]*)\s*(?:руб|₽|rur)/i;
        const singleMatch = title.match(singleSalaryRegex);
        if (singleMatch) {
          const val = Number(singleMatch[1].replace(/\s/g, ''));
          if (title.includes('от')) {
            salaryFrom = val;
          } else if (title.includes('до')) {
            salaryTo = val;
          } else {
            salaryFrom = val;
          }
        }
      }

      // Normalize
      vacancies.push({
        source: 'habr',
        vacancy_id: md5Hash,
        title: title,
        company: company,
        salary_from: salaryFrom,
        salary_to: salaryTo,
        url: item.link,
        schedule: 'Удалённая работа', // Habr RSS url has schedule[]=remote
        area: 'РФ',
        description: item.description || '',
        requirements: '',
        published_at: pubDateStr || ''
      });
    }

  } catch (error: any) {
    logger.error(`Habr RSS Parser Error: ${error.message}`);
  }

  logger.info(`Habr RSS: Parsed ${vacancies.length} vacancies from last ${config.HOURS_LOOKBACK} hours.`);
  return vacancies;
}
