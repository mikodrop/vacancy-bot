import { config } from '../config/config.js';
import { Database, Vacancy } from '../db/database.js';
import { logger } from '../utils/logger.js';
import { Publisher } from '../bot/publisher.js';
import { filterVacancies } from '../filters/vacancyFilter.js';
import { formatPost } from '../templates/postTemplate.js';
import {
  fetchHhVacancies,
  fetchTrudvsemVacancies,
  fetchSuperjobVacancies,
  fetchHabrVacancies,
  fetchVkVacancies,
  fetchTgVacancies,
  fetchAvitoVacancies
} from '../sources/index.js';

// Helper to sleep/delay execution
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function dailyJob() {
  logger.info('Daily Job: Starting cycle...');
  
  const db = new Database();
  const publisher = new Publisher();
  
  let rawVacancies: Vacancy[] = [];

  // Run enabled sources concurrently using Promise.allSettled
  const activeSources: { name: string; promise: Promise<Vacancy[]> }[] = [];

  if (config.SOURCES.hh) activeSources.push({ name: 'hh', promise: fetchHhVacancies() });
  if (config.SOURCES.trudvsem) activeSources.push({ name: 'trudvsem', promise: fetchTrudvsemVacancies() });
  if (config.SOURCES.superjob) activeSources.push({ name: 'superjob', promise: fetchSuperjobVacancies() });
  if (config.SOURCES.habr) activeSources.push({ name: 'habr', promise: fetchHabrVacancies() });
  if (config.SOURCES.vk) activeSources.push({ name: 'vk', promise: fetchVkVacancies() });
  if (config.SOURCES.tg) activeSources.push({ name: 'tg', promise: fetchTgVacancies() });
  if (config.SOURCES.avito) activeSources.push({ name: 'avito', promise: fetchAvitoVacancies() });

  logger.info(`Daily Job: Triggering ${activeSources.length} active source parsers...`);

  const results = await Promise.allSettled(activeSources.map(s => s.promise));

  for (let i = 0; i < results.length; i++) {
    const res = results[i];
    const sourceName = activeSources[i].name;

    if (res.status === 'fulfilled') {
      rawVacancies = rawVacancies.concat(res.value);
    } else {
      logger.error(`Daily Job: Source "${sourceName}" failed to fetch: ${res.reason?.message || res.reason}`);
    }
  }

  logger.info(`Daily Job: Collected ${rawVacancies.length} raw vacancies from all sources.`);

  // 1. Filter out vacancies (salary, remote, stop-words)
  const filtered = filterVacancies(rawVacancies);
  logger.info(`Daily Job: ${filtered.length} vacancies left after applying filters.`);

  // 2. Filter out duplicates (anti-duplication)
  const newVacancies: Vacancy[] = [];
  for (const vacancy of filtered) {
    // Check by source + id
    if (db.exists(vacancy.source, vacancy.vacancy_id)) {
      logger.debug(`Deduplication: Skipping already published ID: ${vacancy.source}:${vacancy.vacancy_id}`);
      continue;
    }

    // Check by url
    if (vacancy.url && db.existsByUrl(vacancy.url)) {
      logger.debug(`Deduplication: Skipping already published URL: ${vacancy.url}`);
      continue;
    }

    // Check by title + company hash
    if (vacancy.title && vacancy.company && db.existsByHash(vacancy.title, vacancy.company)) {
      logger.debug(`Deduplication: Skipping duplicate hash for "${vacancy.title}" @ "${vacancy.company}"`);
      continue;
    }

    newVacancies.push(vacancy);
  }

  logger.info(`Daily Job: Found ${newVacancies.length} brand new vacancies to process.`);

  // 3. Limit to MAX_PER_SESSION
  const targetBatch = newVacancies.slice(0, config.MAX_PER_SESSION);
  logger.info(`Daily Job: Publishing up to ${targetBatch.length} vacancies in this session (limit: ${config.MAX_PER_SESSION}).`);

  let publishedCount = 0;

  // 4. Publish vacancies sequentially with delay
  for (const vacancy of targetBatch) {
    const text = formatPost(vacancy);
    
    // Publish
    const success = await publisher.sendToChannel(text);
    if (success) {
      // Save to database
      db.insert(vacancy);
      publishedCount++;
      
      // Delay to avoid hitting flood limits
      if (publishedCount < targetBatch.length) {
        logger.debug(`Sleeping for ${config.DELAY_BETWEEN_POSTS} seconds before next post...`);
        await sleep(config.DELAY_BETWEEN_POSTS * 1000);
      }
    }
  }

  logger.info(`Daily Job: Cycle complete. Published ${publishedCount}/${targetBatch.length} vacancies.`);

  // Cleanup connections
  db.close();
  await publisher.close();
}

export async function testSource(sourceName: string) {
  logger.info(`Test Mode: Testing single source parser "${sourceName}"...`);
  
  let fetcher: () => Promise<Vacancy[]>;

  switch (sourceName.toLowerCase()) {
    case 'hh':
      fetcher = fetchHhVacancies;
      break;
    case 'trudvsem':
      fetcher = fetchTrudvsemVacancies;
      break;
    case 'superjob':
      fetcher = fetchSuperjobVacancies;
      break;
    case 'habr':
      fetcher = fetchHabrVacancies;
      break;
    case 'vk':
      fetcher = fetchVkVacancies;
      break;
    case 'tg':
      fetcher = fetchTgVacancies;
      break;
    case 'avito':
      fetcher = fetchAvitoVacancies;
      break;
    default:
      logger.error(`Unknown source parser name: ${sourceName}. Available options: hh, trudvsem, superjob, habr, vk, tg, avito`);
      return;
  }

  try {
    const fetched = await fetcher();
    logger.info(`Test Mode: Found ${fetched.length} raw vacancies.`);

    const filtered = filterVacancies(fetched);
    logger.info(`Test Mode: ${filtered.length} passed filter criteria.`);

    if (filtered.length > 0) {
      logger.info('--- SAMPLE FORMATED POST (first 2 items) ---');
      const sampleBatch = filtered.slice(0, 2);
      for (const item of sampleBatch) {
        console.log('\n=============================================');
        console.log(formatPost(item));
        console.log('=============================================\n');
      }
    } else {
      logger.warn('Test Mode: No vacancies passed filters to show formatting.');
    }
  } catch (error: any) {
    logger.error(`Test Mode: Failed during test execution of ${sourceName}: ${error.message}`);
  }
}
