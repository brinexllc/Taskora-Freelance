'use client';
/* oxlint-disable jsx-a11y/autocomplete-valid -- given-name and family-name are standard HTML autocomplete tokens. */
import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  AuthShell,
  OneIdDisabled,
  PasswordInput,
} from '@/components/auth-shell';
import { useApp } from '@/components/app-providers';
import { useRemote } from '@/components/taskora-ui';
import { LegalText } from '@/components/legal-page';
import { register, apiErrorMessage } from '@/lib/api';
export default function RegisterPage() {
  const { t, language, setSession, ready } = useApp();
  const legal = useRemote('legal/current', { query: { lang: language } });
  const [step, setStep] = useState(0);
  const [fullName, setFullName] = useState('');
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
  useEffect(() => {
    void Promise.resolve().then(() =>
      setForm((current) => ({ ...current, accept_terms: false })),
    );
  }, [language, legal.data?.hash]);
  const change = (key) => (event) => {
    const value = event.target.value;
    setForm((current) => ({ ...current, [key]: value }));
  };
  async function submit(event) {
    event.preventDefault();
    const submitted = Object.fromEntries(new FormData(event.currentTarget));
    if (step === 0) {
      const [first_name, ...remaining] = fullName.trim().split(/\s+/);
      setForm((current) => ({
        ...current,
        ...submitted,
        first_name,
        last_name: remaining.join(' '),
      }));
      setError('');
      setStep(1);
      return;
    }
    setBusy(true);
    setError('');
    try {
      if (!legal.data || !form.accept_terms)
        throw new Error(t('legalUnavailable'));
      const data = await register({
        ...form,
        ...submitted,
        language,
        terms_version: legal.data.version,
        terms_hash: legal.data.hash,
      });
      setSession(data);
      window.location.assign('/role');
    } catch (err) {
      setError(apiErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthShell variant="register">
      <h1>{t('createAccount')}</h1>
      <p className="auth-subtitle">
        {t(step === 0 ? 'registerSubtitle' : 'ageHint')}
      </p>
      <form onSubmit={submit} className="auth-form">
        {step === 1 ? (
          <>
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
          </>
        ) : (
          <>
            <label>
              {t('fullName')}
              <input
                name="full_name"
                autoComplete="name"
                maxLength={160}
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
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
            <div className="password-strength" aria-label={t('passwordHint')}>
              {[
                form.password.length >= 8,
                /[A-Z]/.test(form.password),
                /[0-9]/.test(form.password),
                /[^A-Za-z0-9]/.test(form.password),
              ].map((passed, index) => (
                <span key={index} className={passed ? 'passed' : ''} />
              ))}
            </div>
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
            <details className="registration-terms">
              <summary>
                {t('legalVersion')}: {legal.data?.version || t('loading')}
              </summary>
              <LegalText content={legal.data?.content} />
            </details>
            {!legal.data?.approved && <output>{t('legalUnapproved')}</output>}
            {legal.error && (
              <p role="alert">
                {t('legalUnavailable')}{' '}
                <button
                  type="button"
                  className="text-link"
                  onClick={legal.reload}
                >
                  {t('retry')}
                </button>
              </p>
            )}
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
          </>
        )}
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <button
          className="auth-primary"
          disabled={
            !ready || busy || legal.loading || !!legal.error || !legal.data
          }
        >
          {busy
            ? t('loading')
            : t(step === 0 ? 'register' : 'finishRegistration')}
        </button>
        {step === 1 && (
          <button
            type="button"
            className="text-link"
            onClick={() => {
              setStep(0);
              setError('');
            }}
          >
            ← {t('back')}
          </button>
        )}
      </form>
      {step === 0 && (
        <>
          <div className="auth-divider">{t('or')}</div>
          <OneIdDisabled />
        </>
      )}
      <p className="auth-footer">
        {t('hasAccount')} <Link href="/login">{t('login')}</Link>
      </p>
    </AuthShell>
  );
}
