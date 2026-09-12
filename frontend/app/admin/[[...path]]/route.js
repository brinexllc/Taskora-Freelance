import { proxyUpstream } from '@/lib/server-proxy';
export const dynamic = 'force-dynamic';
async function proxy(request, context) {
  const { path = [] } = await context.params;
  return proxyUpstream(request, ['admin', ...path], { api: false });
}
export { proxy as GET, proxy as HEAD, proxy as POST };
