'use client';
import Link from 'next/link';
import { useState } from 'react';
import {
  AuthShell,
  OneIdDisabled,
  PasswordInput,
} from '@/components/auth-shell';
import { useApp } from '@/components/app-providers';
import { login, apiErrorMessage } from '@/lib/api';
export default function LoginPage() {
  const { t, setSession, ready } = useApp();
  const [totpCode, setTotpCode] = useState('');
  const [remember, setRemember] = useState(true);
  const [identifier, setIdentifier] = useState(''),
    [password, setPassword] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const data = await login({
        identifier,
        password,
        remember,
        totp_code: totpCode,
      });
      setSession(data, { remember });
      window.location.assign(
        data.user.is_staff
          ? '/dashboard?view=settings'
          : data.user.role
            ? '/dashboard'
            : '/role',
      );
    } catch (err) {
      setError(apiErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthShell variant="login">
      <h1>{t('welcome')}</h1>
      <p className="auth-subtitle">{t('login')}</p>
      <form onSubmit={submit} className="auth-form">
        <label>
          {t('identifier')}
          <input
            autoComplete="username"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            required
          />
        </label>
        <label>
          {t('password')}
          <PasswordInput
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label>
          {t('mfaCode')}
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            pattern="[0-9]{6}"
            value={totpCode}
            onChange={(e) => setTotpCode(e.target.value)}
          />
        </label>
        <div className="login-options">
          <label className="remember-me">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            {t('rememberMe')}
          </label>
          <Link className="text-link" href="/reset-password">
            {t('forgot')}
          </Link>
        </div>
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <button className="auth-primary" disabled={!ready || busy}>
          {busy ? t('loading') : t('login')}
        </button>
      </form>
      <div className="auth-divider">{t('or')}</div>
      <OneIdDisabled />
      <p className="auth-footer">
        {t('noAccount')} <Link href="/register">{t('register')}</Link>
      </p>
    </AuthShell>
  );
}
