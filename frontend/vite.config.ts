import tailwindcss from '@tailwindcss/postcss';
import vinext from 'vinext';
import { defineConfig, loadEnv } from 'vite';
import { validateEnvironment } from './lib/environment.mjs';

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env };
  validateEnvironment(env);
  for (const key of ['TASKORA_ENV', 'API_URL', 'NEXT_PUBLIC_API_URL']) {
    if (env[key]) process.env[key] = env[key];
  }
  return {
    css: { postcss: { plugins: [tailwindcss()] } },
    server:
      process.env.CODEX_SANDBOX === 'seatbelt'
        ? { watch: { useFsEvents: false, usePolling: true } }
        : undefined,
    // Railway/Docker runs the generated Node standalone server. Using a worker
    // dev runtime here would hide the server-only runtime environment and cookies.
    plugins: [vinext()],
  };
});
