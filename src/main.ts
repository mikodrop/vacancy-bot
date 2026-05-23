import cron from 'node-cron';
import { logger } from './utils/logger.js';
import { config } from './config/config.js';
import { dailyJob, testSource } from './scheduler/tasks.js';

async function bootstrap() {
  // Parse command line arguments manually
  const args = process.argv.slice(2);
  const isTest = args.includes('--test') || args.includes('-t');
  
  let sourceName = '';
  const sourceIndex = args.indexOf('--source');
  if (sourceIndex !== -1 && args[sourceIndex + 1]) {
    sourceName = args[sourceIndex + 1].trim();
  }

  logger.info('Starting Telegram Vacancy Bot (TypeScript Node.js version)...');

  if (isTest) {
    logger.info('Running in TEST mode (one-time execution)...');
    try {
      if (sourceName) {
        await testSource(sourceName);
      } else {
        await dailyJob();
      }
      logger.info('Test execution finished successfully.');
      process.exit(0);
    } catch (error: any) {
      logger.error(`Critical error during test execution: ${error.message}`);
      process.exit(1);
    }
  } else {
    // Normal Scheduler Mode
    logger.info('Running in SCHEDULER mode...');
    logger.info('Scheduled jobs:');
    logger.info('- Daily parsing job 1: 09:00 (Moscow Time)');
    logger.info('- Daily parsing job 2: 18:00 (Moscow Time)');
    
    // Moscow time is 'Europe/Moscow'
    const cronTimezone = 'Europe/Moscow';
    
    // Schedule job 1: 09:00
    cron.schedule('0 9 * * *', async () => {
      logger.info('Scheduler triggered: Morning job (09:00)');
      try {
        await dailyJob();
      } catch (err: any) {
        logger.error(`Error in morning job: ${err.message}`);
      }
    }, {
      timezone: cronTimezone
    });

    // Schedule job 2: 18:00
    cron.schedule('0 18 * * *', async () => {
      logger.info('Scheduler triggered: Evening job (18:00)');
      try {
        await dailyJob();
      } catch (err: any) {
        logger.error(`Error in evening job: ${err.message}`);
      }
    }, {
      timezone: cronTimezone
    });

    logger.info('Scheduler initialized. Waiting for scheduled cycles...');
  }
}

// Handle termination signals gracefully
process.on('SIGINT', () => {
  logger.info('SIGINT signal received. Shutting down gracefully...');
  process.exit(0);
});

process.on('SIGTERM', () => {
  logger.info('SIGTERM signal received. Shutting down gracefully...');
  process.exit(0);
});

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
  logger.error(error, 'Uncaught Exception detected!');
});

process.on('unhandledRejection', (reason, promise) => {
  logger.error({ promise, reason }, 'Unhandled Rejection detected!');
});

bootstrap();
