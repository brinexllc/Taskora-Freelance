export const dynamic = 'force-dynamic';
export function GET() {
  return Response.json({ service: 'frontend', sha: process.env.RELEASE_SHA || process.env.RAILWAY_GIT_COMMIT_SHA || 'unversioned', environment: process.env.TASKORA_ENV || 'unconfigured' }, { headers: { 'Cache-Control': 'no-store' } });
}
