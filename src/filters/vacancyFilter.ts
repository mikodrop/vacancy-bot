import { config } from '../config/config.js';
import { logger } from '../utils/logger.js';
import { Vacancy } from '../db/database.js';

export function isValidVacancy(vacancy: Vacancy): boolean {
  const title = String(vacancy.title || '').toLowerCase();
  const description = String(vacancy.description || '').toLowerCase();
  const requirements = String(vacancy.requirements || '').toLowerCase();
  const schedule = String(vacancy.schedule || '').toLowerCase();

  const combinedText = `${title} ${description} ${requirements}`;

  // 1. Check salary (salary_from)
  if (vacancy.salary_from && vacancy.salary_from < config.FILTERS.salary_min) {
    logger.debug(
      `Filtered out (Salary too low: ${vacancy.salary_from} < ${config.FILTERS.salary_min}): "${vacancy.title}"`
    );
    return false;
  }

  // 2. Check excluded keywords (stop words)
  for (const stopWord of config.FILTERS.keywords_exclude) {
    if (combinedText.includes(stopWord)) {
      logger.debug(
        `Filtered out (Stop word matched "${stopWord}"): "${vacancy.title}"`
      );
      return false;
    }
  }

  // 3. Check schedule type (remote-only check)
  if (schedule) {
    const hasRemoteKeyword = config.FILTERS.schedule.some((keyword) =>
      schedule.includes(keyword)
    );
    if (!hasRemoteKeyword) {
      logger.debug(
        `Filtered out (Not remote schedule: "${vacancy.schedule}"): "${vacancy.title}"`
      );
      return false;
    }
  } else {
    // If no schedule information is provided, check if the title or description mentions remote work
    const textHasRemoteKeyword = config.FILTERS.schedule.some(
      (keyword) => title.includes(keyword) || description.includes(keyword)
    );
    if (!textHasRemoteKeyword) {
      logger.debug(
        `Filtered out (No remote work keywords found in text): "${vacancy.title}"`
      );
      return false;
    }
  }

  // 4. Check included keywords (if defined)
  if (config.FILTERS.keywords_include.length > 0) {
    const hasIncludeKeyword = config.FILTERS.keywords_include.some((keyword) =>
      combinedText.includes(keyword.toLowerCase())
    );
    if (!hasIncludeKeyword) {
      logger.debug(
        `Filtered out (Missing required keywords): "${vacancy.title}"`
      );
      return false;
    }
  }

  return true;
}

export function filterVacancies(vacancies: Vacancy[]): Vacancy[] {
  const countBefore = vacancies.length;
  const filtered = vacancies.filter(isValidVacancy);
  const countAfter = filtered.length;

  logger.info(`Filtering summary: ${countBefore} -> ${countAfter} (filtered out ${countBefore - countAfter})`);
  return filtered;
}
