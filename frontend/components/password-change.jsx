'use client';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiRequest } from '@/lib/api';
import { Field, Notice } from '@/components/taskora-ui';
export function PasswordChange() {
  const { t, session, setSession } = useApp();
  const [form, setForm] = useState({
    current_password: '',
    password: '',
    password_confirm: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    setSaved(false);
    try {
      setSession(
        await apiRequest('auth/change-password', {
          method: 'POST',
          token: session.token,
          body: form,
        }),
      );
      setForm({ current_password: '', password: '', password_confirm: '' });
      setSaved(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="t-card">
      <h2>{t('security')}</h2>
      <form className="t-form" onSubmit={submit}>
        {[
          ['current_password', 'currentPassword'],
          ['password', 'password'],
          ['password_confirm', 'passwordAgain'],
        ].map(([key, label]) => (
          <Field key={key} label={t(label)}>
            <input
              type="password"
              required
              autoComplete={
                key === 'current_password' ? 'current-password' : 'new-password'
              }
              minLength={8}
              maxLength={128}
              value={form[key]}
              onChange={(e) =>
                setForm((f) => ({ ...f, [key]: e.target.value }))
              }
            />
          </Field>
        ))}
        <small className="muted">{t('passwordHint')}</small>
        <Notice error>{error}</Notice>
        {saved && <Notice>{t('saved')}</Notice>}
        <button className="t-button secondary" disabled={busy}>
          {t('changePassword')}
        </button>
      </form>
    </section>
  );
}
