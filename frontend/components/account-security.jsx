'use client';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiRequest, apiErrorMessage } from '@/lib/api';
import { dateTime } from '@/lib/i18n';
import { Field, Notice, RemoteState, useRemote } from '@/components/taskora-ui';

export function AccountSecurity() {
  const { session, updateUser, t, language } = useApp();
  const [channel, setChannel] = useState('email');
  const [contact, setContact] = useState(session.user.email || '');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [setup, setSetup] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const sessions = useRemote('auth/sessions', { token: session.authenticated });
  async function action(path, body, method = 'POST', success) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await apiRequest(path, { method, body });
      if (result?.user) updateUser(result.user);
      if (success) setNotice(t(success));
      sessions.reload();
      return result;
    } catch (e) {
      setError(apiErrorMessage(e, t));
      return null;
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="list-stack account-security">
      <Notice error>{error}</Notice>
      <Notice>{notice}</Notice>
      <section className="t-card">
        <h2>{t('contactVerification')}</h2>
        <p>{t('contactPolicy')}</p>
        <ul>
          {['email', 'phone'].map((key) => (
            <li key={key}>
              {t(key)}: {session.user[key]} ·{' '}
              {t(
                session.user[`${key}_verified_at`]
                  ? 'verifiedContact'
                  : 'unverifiedContact',
              )}
            </li>
          ))}
        </ul>
        <form
          className="t-form"
          onSubmit={async (e) => {
            e.preventDefault();
            const result = await action('auth/verification/confirm', {
              channel,
              code,
            });
            if (result) {
              setCode('');
              setNotice(t('verifiedContact'));
            }
          }}
        >
          <Field label={t('contactVerification')}>
            <select
              value={channel}
              onChange={(e) => {
                setChannel(e.target.value);
                setContact(session.user[e.target.value] || '');
                setCode('');
              }}
            >
              {['email', 'phone'].map((key) => (
                <option key={key} value={key}>
                  {t(key)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t(channel)}>
            <input
              type={channel === 'email' ? 'email' : 'tel'}
              value={contact}
              onChange={(e) => setContact(e.target.value)}
            />
          </Field>
          <button
            className="t-button secondary"
            type="button"
            disabled={
              busy || !contact.trim() || contact === session.user[channel]
            }
            onClick={async () => {
              const user = await action(
                'auth/me',
                { [channel]: contact },
                'PATCH',
              );
              if (user) updateUser(user);
            }}
          >
            {t('save')}
          </button>
          <button
            className="t-button secondary"
            type="button"
            disabled={busy || contact !== session.user[channel]}
            onClick={() =>
              action(
                'auth/verification/request',
                { channel },
                'POST',
                'codeRequested',
              )
            }
          >
            {t('sendCode')}
          </button>
          <Field label={t('verificationCode')}>
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
          </Field>
          <button className="t-button" disabled={busy}>
            {t('confirm')}
          </button>
        </form>
      </section>
      <section className="t-card">
        <h2>{t('activeSessions')}</h2>
        <RemoteState remote={sessions}>
          <ul className="security-sessions">
            {(sessions.data?.results || sessions.data || []).map((item) => (
              <li key={item.id}>
                <strong>
                  {item.current
                    ? t('currentSession')
                    : item.user_agent || t('activeSessions')}
                </strong>
                <p>
                  {dateTime(item.last_seen_at, language)} · {t('expiresAt')}:{' '}
                  {dateTime(item.expires_at, language)}
                </p>
                {!item.current && (
                  <button
                    className="text-link"
                    disabled={busy}
                    onClick={() =>
                      action(`auth/sessions/${item.id}`, undefined, 'DELETE')
                    }
                  >
                    {t('revokeSession')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </RemoteState>
        <button
          className="t-button secondary"
          disabled={busy}
          onClick={() => action('auth/sessions/revoke-others')}
        >
          {t('revokeOtherSessions')}
        </button>
      </section>
      <section className="t-card">
        <h2>{t('mfaTitle')}</h2>
        {session.user.mfa_enabled ? (
          <Notice>{t('mfaEnabled')}</Notice>
        ) : (
          <p>{t('mfaHint')}</p>
        )}
        <form
          className="t-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (session.user.mfa_enabled)
              await action(
                'auth/confirm-sensitive',
                { password, code: mfaCode },
                'POST',
                'sensitiveConfirmed',
              );
            else if (setup) {
              const result = await action('auth/mfa/enable', { code: mfaCode });
              if (result) {
                setSetup(null);
                const user = await apiRequest('auth/me');
                updateUser(user);
              }
            } else setSetup(await action('auth/mfa/setup', { password }));
            setPassword('');
            setMfaCode('');
          }}
        >
          {!setup && (
            <Field label={t('currentPassword')}>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          )}
          {setup && (
            <p className="security-secret">
              <code>{setup.secret}</code>
            </p>
          )}
          {(setup || session.user.mfa_enabled) && (
            <Field label={t('mfaCode')}>
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                required
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
              />
            </Field>
          )}
          <button className="t-button secondary" disabled={busy}>
            {t(
              session.user.mfa_enabled
                ? 'sensitiveConfirmation'
                : setup
                  ? 'confirm'
                  : 'mfaSetup',
            )}
          </button>
        </form>
      </section>
    </div>
  );
}
