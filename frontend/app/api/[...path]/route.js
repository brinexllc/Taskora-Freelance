import { proxyUpstream } from '@/lib/server-proxy';
export const dynamic = 'force-dynamic';
async function proxy(request, context) {
  const { path } = await context.params;
  return proxyUpstream(request, path);
}
export { proxy as GET, proxy as HEAD, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE, proxy as OPTIONS };
