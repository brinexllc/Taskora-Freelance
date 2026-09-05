'use client';
/* oxlint-disable jsx-a11y/autocomplete-valid -- given-name and family-name are standard HTML autocomplete tokens. */
import Link from 'next/link';
import { useState } from 'react';
import {
  AuthShell,
  OneIdDisabled,
  PasswordInput,
} from '@/components/auth-shell';
import { useApp } from '@/components/app-providers';
import { register } from '@/lib/api';
export default function RegisterPage() {
  const { t, language, setSession, ready } = useApp();
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    username: '',
    birth_date: '',
    phone: '+998',
    email: '',
    accept_terms: false,
    password: '',
    password_confirm: '',
  });
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const change = (key) => (event) => {
    const value = event.target.value;
    setForm((current) => ({ ...current, [key]: value }));
  };
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const data = await register({ ...form, language });
      setSession(data);
      window.location.assign('/role');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthShell wide>
      <h1>{t('createAccount')}</h1>
      <p className="auth-subtitle">{t('ageHint')}</p>
      <form onSubmit={submit} className="auth-form">
        <div className="form-columns">
          <label>
            {t('firstName')}
            <input
              name="first_name"
              autoComplete="given-name"
              maxLength={80}
              value={form.first_name}
              onChange={change('first_name')}
              required
            />
          </label>
          <label>
            {t('lastName')}
            <input
              name="last_name"
              autoComplete="family-name"
              maxLength={80}
              value={form.last_name}
              onChange={change('last_name')}
              required
            />
          </label>
        </div>
        <label>
          {t('username')}
          <input
            name="username"
            autoComplete="username"
            pattern="[a-zA-Z0-9_]{3,30}"
            title="3–30: A–Z, a–z, 0–9, _"
            value={form.username}
            onChange={change('username')}
            required
          />
        </label>
        <label>
          {t('birthDate')}
          <input
            name="birth_date"
            type="date"
            autoComplete="bday"
            value={form.birth_date}
            onChange={change('birth_date')}
            required
          />
        </label>
        <label>
          {t('phone')}
          <input
            name="phone"
            type="tel"
            autoComplete="tel"
            placeholder="+998901234567"
            value={form.phone}
            onChange={change('phone')}
            required
          />
        </label>
        <label>
          {t('email')}
          <input
            name="email"
            type="email"
            autoComplete="email"
            value={form.email}
            onChange={change('email')}
            required
          />
        </label>
        <label>
          {t('password')}
          <PasswordInput
            name="password"
            value={form.password}
            onChange={change('password')}
            autoComplete="new-password"
            minLength={8}
          />
        </label>
        <small className="muted">{t('passwordHint')}</small>
        <label>
          {t('passwordAgain')}
          <PasswordInput
            name="password_confirm"
            value={form.password_confirm}
            onChange={change('password_confirm')}
            autoComplete="new-password"
          />
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={form.accept_terms}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                accept_terms: event.target.checked,
              }))
            }
            required
          />
          <span>
            {t('acceptTerms')}{' '}
            <Link href="/terms" target="_blank">
              {t('termsLink')}
            </Link>{' '}
            ·{' '}
            <Link href="/privacy" target="_blank">
              {t('privacyLink')}
            </Link>
          </span>
        </label>
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <button className="auth-primary" disabled={!ready || busy}>
          {busy ? t('loading') : t('register')}
        </button>
      </form>
      <div className="auth-divider">{t('or')}</div>
      <OneIdDisabled />
      <p className="auth-footer">
        {t('hasAccount')} <Link href="/login">{t('login')}</Link>
      </p>
    </AuthShell>
  );
}
