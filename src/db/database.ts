import sqlite from 'better-sqlite3';
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
  private db: sqlite.Database;

  constructor() {
    logger.debug(`Initializing database at: ${config.DB_PATH}`);
    this.db = new sqlite(config.DB_PATH);
    this.initDb();
  }

  private initDb() {
    try {
      this.db.exec(`
        CREATE TABLE IF NOT EXISTS published_vacancies (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          source      TEXT NOT NULL,
          vacancy_id  TEXT NOT NULL,
          title       TEXT,
          company     TEXT,
          salary_from INTEGER,
          salary_to   INTEGER,
          url         TEXT,
          published_at TEXT,
          posted_at   TEXT DEFAULT CURRENT_TIMESTAMP,
          title_hash  TEXT,
          UNIQUE(source, vacancy_id)
        );

        CREATE TABLE IF NOT EXISTS sources_config (
          source  TEXT PRIMARY KEY,
          enabled INTEGER DEFAULT 1,
          last_check TEXT
        );
      `);
      logger.debug('Database tables initialized successfully');
    } catch (error) {
      logger.error(error, 'Error initializing database tables');
      throw error;
    }
  }

  public getHash(title: string, company: string): string {
    const text = `${title.toLowerCase().trim()}|${company.toLowerCase().trim()}`;
    return crypto.createHash('md5').update(text).digest('hex');
  }

  public exists(source: string, vacancyId: string): boolean {
    try {
      const stmt = this.db.prepare(
        'SELECT 1 FROM published_vacancies WHERE source = ? AND vacancy_id = ?'
      );
      const result = stmt.get(source, vacancyId);
      return !!result;
    } catch (error) {
      logger.error(error, `Error checking vacancy existence for ${source}:${vacancyId}`);
      return false;
    }
  }

  public existsByUrl(url: string): boolean {
    if (!url) return false;
    try {
      const stmt = this.db.prepare(
        'SELECT 1 FROM published_vacancies WHERE url = ?'
      );
      const result = stmt.get(url);
      return !!result;
    } catch (error) {
      logger.error(error, `Error checking existence by URL: ${url}`);
      return false;
    }
  }

  public existsByHash(title: string, company: string): boolean {
    if (!title || !company) return false;
    const titleHash = this.getHash(title, company);
    try {
      const stmt = this.db.prepare(
        'SELECT 1 FROM published_vacancies WHERE title_hash = ?'
      );
      const result = stmt.get(titleHash);
      return !!result;
    } catch (error) {
      logger.error(error, `Error checking existence by hash for ${title} @ ${company}`);
      return false;
    }
  }

  public insert(vacancy: Vacancy): boolean {
    const titleHash = this.getHash(vacancy.title, vacancy.company);
    try {
      const stmt = this.db.prepare(`
        INSERT OR IGNORE INTO published_vacancies (
          source, vacancy_id, title, company, salary_from, salary_to, url, published_at, title_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `);
      const info = stmt.run(
        vacancy.source,
        vacancy.vacancy_id,
        vacancy.title,
        vacancy.company,
        vacancy.salary_from ?? null,
        vacancy.salary_to ?? null,
        vacancy.url,
        vacancy.published_at || null,
        titleHash
      );
      
      const success = info.changes > 0;
      if (success) {
        logger.debug(`Vacancy inserted into DB: ${vacancy.source}:${vacancy.vacancy_id}`);
      } else {
        logger.warn(`Vacancy already exists in DB (duplicate constraint): ${vacancy.source}:${vacancy.vacancy_id}`);
      }
      return success;
    } catch (error) {
      logger.error(error, `Error inserting vacancy: ${vacancy.source}:${vacancy.vacancy_id}`);
      return false;
    }
  }

  public getStats(): Record<string, number> {
    try {
      const stmt = this.db.prepare(
        'SELECT source, COUNT(*) as count FROM published_vacancies GROUP BY source'
      );
      const rows = stmt.all() as { source: string; count: number }[];
      const stats: Record<string, number> = {};
      for (const row of rows) {
        stats[row.source] = row.count;
      }
      return stats;
    } catch (error) {
      logger.error(error, 'Error getting database stats');
      return {};
    }
  }

  public getRecent(limit = 10): any[] {
    try {
      const stmt = this.db.prepare(
        'SELECT * FROM published_vacancies ORDER BY posted_at DESC LIMIT ?'
      );
      return stmt.all(limit);
    } catch (error) {
      logger.error(error, 'Error getting recent vacancies');
      return [];
    }
  }

  public close() {
    try {
      this.db.close();
      logger.debug('Database connection closed');
    } catch (error) {
      logger.error(error, 'Error closing database connection');
    }
  }
}
