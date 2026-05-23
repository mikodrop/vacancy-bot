import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { config } from '../config/config.js';
import { logger } from '../utils/logger.js';

export interface Vacancy {
  source: string;
  vacancy_id: string;
  title: string;
  company: string;
  salary_from?: number | null;
  salary_to?: number | null;
  url: string;
  schedule?: string;
  area?: string;
  description?: string;
  requirements?: string;
  published_at?: string;
}

export class Database {
  private filePath: string;
  private vacancies: Vacancy[] = [];

  constructor() {
    this.filePath = path.join(config.BASE_DIR, 'data/vacancies.json');
    logger.debug(`Initializing JSON database at: ${this.filePath}`);
    this.initDb();
  }

  private initDb() {
    try {
      const dir = path.dirname(this.filePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }

      if (fs.existsSync(this.filePath)) {
        const data = fs.readFileSync(this.filePath, 'utf-8');
        this.vacancies = JSON.parse(data || '[]');
      } else {
        this.vacancies = [];
        this.save();
      }
      logger.debug(`JSON database loaded: ${this.vacancies.length} vacancies.`);
    } catch (error) {
      logger.error(error, 'Error initializing JSON database. Resetting to empty.');
      this.vacancies = [];
    }
  }

  private save() {
    try {
      fs.writeFileSync(this.filePath, JSON.stringify(this.vacancies, null, 2), 'utf-8');
    } catch (error) {
      logger.error(error, 'Error saving JSON database');
    }
  }

  public getHash(title: string, company: string): string {
    const text = `${title.toLowerCase().trim()}|${company.toLowerCase().trim()}`;
    return crypto.createHash('md5').update(text).digest('hex');
  }

  public exists(source: string, vacancyId: string): boolean {
    return this.vacancies.some(
      (v) => v.source === source && v.vacancy_id === vacancyId
    );
  }

  public existsByUrl(url: string): boolean {
    if (!url) return false;
    return this.vacancies.some((v) => v.url === url);
  }

  public existsByHash(title: string, company: string): boolean {
    if (!title || !company) return false;
    const targetHash = this.getHash(title, company);
    return this.vacancies.some(
      (v) => this.getHash(v.title, v.company) === targetHash
    );
  }

  public insert(vacancy: Vacancy): boolean {
    if (this.exists(vacancy.source, vacancy.vacancy_id)) {
      return false;
    }
    this.vacancies.push(vacancy);
    this.save();
    logger.debug(`Vacancy inserted into JSON database: ${vacancy.source}:${vacancy.vacancy_id}`);
    return true;
  }

  public getStats(): Record<string, number> {
    const stats: Record<string, number> = {};
    for (const v of this.vacancies) {
      stats[v.source] = (stats[v.source] || 0) + 1;
    }
    return stats;
  }

  public getRecent(limit = 10): any[] {
    return this.vacancies.slice(-limit).reverse();
  }

  public close() {
    logger.debug('JSON Database connection closed (no-op)');
  }
}
