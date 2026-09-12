'use client';
import { BriefcaseBusiness, ClipboardList } from 'lucide-react';
import { useState } from 'react';
import { AuthShell } from '@/components/auth-shell';
import { useApp } from '@/components/app-providers';
import { setRole, apiErrorMessage } from '@/lib/api';
export default function RolePage() {
  const { t, session, updateUser, ready } = useApp();
  const [role, setChosen] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function submit() {
    if (!session?.authenticated || !role) return;
    setBusy(true);
    setError('');
    try {
      updateUser(await setRole(role, session.authenticated));
      window.location.assign('/dashboard');
    } catch (err) {
      setError(apiErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthShell wide variant="role">
      <h1>{t('chooseRole')}</h1>
      <p className="auth-subtitle">{t('roleHint')}</p>
      <div className="role-grid">
        {[
          ['freelancer', BriefcaseBusiness],
          ['client', ClipboardList],
        ].map(([key, Icon]) => (
          <button
            type="button"
            key={key}
            aria-pressed={role === key}
            onClick={() => setChosen(key)}
            className={`role-card ${role === key ? 'selected' : ''}`}
          >
            <Icon />
            <strong>{t(key)}</strong>
            <span>{t(`${String(key)}Hint`)}</span>
          </button>
        ))}
      </div>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      <button
        className="auth-primary"
        onClick={submit}
        disabled={!ready || !role || busy}
      >
        {busy ? t('loading') : t('continue')}
      </button>
    </AuthShell>
  );
}
