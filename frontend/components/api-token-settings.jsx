'use client';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiErrorMessage, apiRequest } from '@/lib/api';
import { dateTime } from '@/lib/i18n';
import { Field, Notice, RemoteState, useRemote } from '@/components/taskora-ui';
export function ApiTokenSettings() {
  const { t, session, language } = useApp();
  const remote = useRemote(session.user.is_staff ? null : 'auth/api-tokens');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [scope, setScope] = useState('profile:read');
  const [duration, setDuration] = useState(3600);
  const [issued, setIssued] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (session.user.is_staff) return null;
  return <section className="t-card"><h2>{t('apiTokens')}</h2><p>{t('apiTokensHint')}</p><Notice error>{error}</Notice>
    {issued && <Notice><p>{t('tokenOnce')}</p><code className="security-secret">{issued.token}</code><button className="text-link" onClick={() => setIssued(null)}>{t('close')}</button></Notice>}
    <form className="t-form" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setError('');
      try { setIssued(await apiRequest('auth/api-tokens', { method: 'POST', body: { name, password, scopes: [scope], expires_in: duration } })); setPassword(''); remote.reload(); }
      catch (e) { setError(apiErrorMessage(e,t)); } finally { setBusy(false); }
    }}>
      <Field label={t('tokenName')}><input value={name} maxLength={80} required onChange={(e) => setName(e.target.value)} /></Field>
      <Field label={t('tokenScope')}><select value={scope} onChange={(e) => setScope(e.target.value)}><option value="profile:read">{t('profile')}</option><option value="projects:read">{t('orders')}</option><option value="contracts:read">{t('contracts')}</option></select></Field>
      <Field label={t('tokenDuration')}><input type="number" min={300} max={86400} required value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></Field>
      <Field label={t('currentPassword')}><input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
      <button className="t-button secondary" disabled={busy || !!issued}>{t('issueToken')}</button>
    </form>
    <RemoteState remote={remote}><ul className="security-sessions">{(remote.data?.results || remote.data || []).map((item) => <li key={item.id}><strong>{item.name}</strong><p>{t('expiresAt')}: {dateTime(item.expires_at,language)}</p><button className="text-link" disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await apiRequest(`auth/api-tokens/${item.id}`, { method:'DELETE' }); if (issued?.id === item.id) setIssued(null); remote.reload(); } catch(e) { setError(apiErrorMessage(e,t)); } finally { setBusy(false); } }}>{t('revokeToken')}</button></li>)}</ul></RemoteState>
  </section>;
}
