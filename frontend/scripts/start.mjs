import { loadEnv } from 'vite';
import { validateEnvironment } from '../lib/environment.mjs';
const environment = { ...loadEnv(process.env.NODE_ENV || 'production', process.cwd(), ''), ...process.env };
validateEnvironment(environment);
for (const key of ['TASKORA_ENV', 'API_URL', 'NEXT_PUBLIC_API_URL', 'VINEXT_TRUST_PROXY', 'VINEXT_TRUSTED_HOSTS', 'RELEASE_SHA', 'PORT', 'HOST']) {
  if (environment[key] !== undefined) process.env[key] = environment[key];
}
await import('../dist/standalone/server.js');
