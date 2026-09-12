import { loadEnv } from 'vite';
import { validateEnvironment } from '../lib/environment.mjs';
const env = {
  ...loadEnv(process.env.NODE_ENV || 'production', process.cwd(), ''),
  ...process.env,
};
validateEnvironment(env);
console.log('Taskora environment validated.');
