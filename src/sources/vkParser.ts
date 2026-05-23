import { VK } from 'vk-io';
import { config } from '../config/config.js';
import { logger } from '../utils/logger.js';
import { Vacancy } from '../db/database.js';

export async function fetchVkVacancies(): Promise<Vacancy[]> {
  const vacancies: Vacancy[] = [];

  if (!config.VK_ACCESS_TOKEN) {
    logger.debug('VK API: VK_ACCESS_TOKEN is not configured. Skipping VK fetch.');
    return [];
  }

  logger.info('VK API: Starting fetch...');
  
  // Initialize VK SDK
  const vk = new VK({
    token: config.VK_ACCESS_TOKEN,
    apiVersion: config.VK_API_VERSION
  });

  const lookbackHours = config.HOURS_LOOKBACK;
  const cutoffTime = Math.floor((Date.now() - lookbackHours * 60 * 60 * 1000) / 1000); // VK uses Unix timestamps in seconds

  for (const groupName of config.VK_GROUPS_TO_MONITOR) {
    try {
      logger.debug(`VK API: Resolving screen name for group "${groupName}"...`);
      const resolved = await vk.api.utils.resolveScreenName({
        screen_name: groupName
      });

      if (!resolved || resolved.type !== 'group') {
        logger.warn(`VK API: Screen name "${groupName}" resolved to type "${resolved?.type || 'unknown'}", not a group. Skipping.`);
        continue;
      }

      const groupId = resolved.object_id;
      logger.debug(`VK API: Fetching wall posts for group "${groupName}" (ID: -${groupId})...`);
      
      const response = await vk.api.wall.get({
        owner_id: -groupId,
        count: 50,
        filter: 'owner'
      });

      const posts = response.items || [];
      logger.debug(`VK API: Found ${posts.length} posts for "${groupName}".`);

      for (const post of posts) {
        // Skip pinned posts or posts older than cutoffTime
        if (post.is_pinned || !post.date || post.date < cutoffTime) {
          continue;
        }

        const text = post.text || '';
        if (!text.trim()) continue;

        // Extract first line as title
        const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
        const title = lines[0] ? (lines[0].length > 80 ? lines[0].slice(0, 80) + '...' : lines[0]) : 'Вакансия из ВКонтакте';

        // Try to parse salary from text
        let salaryFrom: number | null = null;
        let salaryTo: number | null = null;
        
        // Regex patterns to look for salaries: e.g. 50000, 50 000, 50к, 50k, 50 тыс
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

        // Try to find URLs in attachments or text
        let postUrl = `https://vk.com/wall-${groupId}_${post.id}`;
        let externalUrl = postUrl;

        // Look for link attachments
        const linkAttachment = post.attachments?.find((att: any) => att.type === 'link');
        if (linkAttachment?.link?.url) {
          externalUrl = linkAttachment.link.url;
        } else {
          // Parse link from text via regex
          const urlRegex = /(https?:\/\/[^\s]+)/g;
          const textUrls = text.match(urlRegex);
          if (textUrls && textUrls[0]) {
            externalUrl = textUrls[0];
          }
        }

        vacancies.push({
          source: 'vk',
          vacancy_id: String(post.id),
          title: title,
          company: groupName, // VK group name as fallback company
          salary_from: salaryFrom,
          salary_to: salaryTo,
          url: externalUrl,
          schedule: 'Удалённая работа', // Group parsing is geared towards remote channels
          area: 'РФ',
          description: text,
          requirements: '',
          published_at: new Date(post.date * 1000).toISOString()
        });
      }

    } catch (error: any) {
      logger.error(`VK API Error parsing group "${groupName}": ${error.message}`);
    }
  }

  logger.info(`VK API: Fetched ${vacancies.length} vacancies.`);
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
