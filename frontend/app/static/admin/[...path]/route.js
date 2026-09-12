import { proxyUpstream } from '@/lib/server-proxy';
async function asset(request, context) {
  const { path } = await context.params;
  return proxyUpstream(request, ['static', 'admin', ...path], { api: false, asset: true });
}
export { asset as GET, asset as HEAD };
