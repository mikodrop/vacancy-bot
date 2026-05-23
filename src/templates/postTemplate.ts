import { Vacancy } from '../db/database.js';

export function escapeHtml(text: string): string {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export function formatSalary(vacancy: Vacancy): string {
  const from = vacancy.salary_from;
  const to = vacancy.salary_to;

  const fmt = (num: number) => num.toLocaleString('ru-RU') + ' ₽';

  if (from && to) {
    return `${fmt(from)} — ${fmt(to)}`;
  } else if (from) {
    return `от ${fmt(from)}`;
  } else if (to) {
    return `до ${fmt(to)}`;
  } else {
    return 'не указана';
  }
}

export function slugify(text: string): string {
  if (!text) return '';
  // Keep only Cyrillic, Latin characters and numbers, convert to lowercase
  const clean = text
    .toLowerCase()
    .replace(/[^a-zа-яё0-9]/gi, '');
  return clean;
}

export function formatPost(vacancy: Vacancy): string {
  const title = vacancy.title;
  const company = vacancy.company;
  const salary = formatSalary(vacancy);
  const schedule = vacancy.schedule || 'Удалённо';
  const area = vacancy.area || 'РФ';

  // Clean description and requirements (limit length)
  const desc = vacancy.description || '';
  const req = vacancy.requirements || '';

  const cleanDesc = desc.replace(/<[^>]*>/g, '').trim(); // Remove any HTML tags if present
  const cleanReq = req.replace(/<[^>]*>/g, '').trim();

  const descSnippet = cleanDesc.length > 300 ? cleanDesc.slice(0, 300) + '...' : cleanDesc;
  const reqSnippet = cleanReq.length > 200 ? cleanReq.slice(0, 200) + '...' : cleanReq;

  const sourceTag = slugify(vacancy.source);

  // If there's no description or requirements, use the short template
  if (!cleanDesc && !cleanReq) {
    return formatPostShort(vacancy);
  }

  return `💼 <b>${escapeHtml(title)}</b>

🏢 Компания: <b>${escapeHtml(company)}</b>
💰 Зарплата: <b>${escapeHtml(salary)}</b>
📍 Формат: ${escapeHtml(schedule)}
🗺️ Регион: ${escapeHtml(area)}

📝 <b>О задачах:</b>
${escapeHtml(descSnippet)}

✅ <b>Требования:</b>
${escapeHtml(reqSnippet)}

🔗 <a href="${vacancy.url}">Смотреть вакансию</a>

#удалёнка #вакансия #${sourceTag}`;
}

export function formatPostShort(vacancy: Vacancy): string {
  const title = vacancy.title;
  const company = vacancy.company;
  const salary = formatSalary(vacancy);
  const sourceTag = slugify(vacancy.source);

  return `💼 <b>${escapeHtml(title)}</b>
🏢 <b>${escapeHtml(company)}</b> | 💰 <b>${escapeHtml(salary)}</b> | 🌐 Удалённо

🔗 <a href="${vacancy.url}">Открыть вакансию</a>

#удалёнка #вакансия #${sourceTag}`;
}
