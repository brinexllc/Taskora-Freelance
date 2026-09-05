'use client';
import { useState } from 'react';
import { AuthBack, AuthShell, PasswordInput } from '@/components/auth-shell';
import { useApp } from '@/components/app-providers';
import {
  confirmPasswordReset,
  requestPasswordReset,
  verifyPasswordReset,
} from '@/lib/api';
export default function ResetPasswordPage() {
  const { t, setSession, ready } = useApp();
  const [step, setStep] = useState(1),
    [identifier, setIdentifier] = useState(''),
    [code, setCode] = useState(''),
    [token, setToken] = useState(''),
    [password, setPassword] = useState(''),
    [confirm, setConfirm] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [consoleDelivery, setConsoleDelivery] = useState(false);
  async function send() {
    const data = await requestPasswordReset(identifier);
    setConsoleDelivery(data.development_delivery);
    setStep(2);
  }
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (step === 1) await send();
      else if (step === 2) {
        const data = await verifyPasswordReset(identifier, code);
        setToken(data.reset_token);
        setStep(3);
      } else {
        const data = await confirmPasswordReset({
          identifier,
          reset_token: token,
          password,
          password_confirm: confirm,
        });
        setSession(data);
        window.location.assign(data.user.role ? '/dashboard' : '/role');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthShell>
      <AuthBack />
      <div className="reset-steps">
        {[1, 2, 3].map((n) => (
          <span key={n} className={n <= step ? 'done' : ''}>
            {n}
          </span>
        ))}
      </div>
      <h1>{t(step === 1 ? 'reset' : step === 2 ? 'code' : 'newPassword')}</h1>
      <p className="auth-subtitle">
        {t(
          step === 2
            ? 'codeHint'
            : step === 3
              ? 'passwordHint'
              : 'resetIdentifier',
        )}
      </p>
      <form className="auth-form" onSubmit={submit}>
        {step === 1 && (
          <label>
            {t('resetIdentifier')}
            <input
              autoComplete="username"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
            />
          </label>
        )}
        {step === 2 && (
          <>
            <label>
              {t('code')}
              <input
                className="verification-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                required
              />
            </label>
            {consoleDelivery && <p className="notice">{t('consoleCode')}</p>}
            <button
              type="button"
              className="text-link"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError('');
                try {
                  await send();
                } catch (err) {
                  setError(err.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {t('resend')}
            </button>
            <button
              type="button"
              className="text-link"
              onClick={() => {
                setStep(1);
                setCode('');
                setError('');
              }}
            >
              {t('changeContact')}
            </button>
          </>
        )}
        {step === 3 && (
          <>
            <label>
              {t('newPassword')}
              <PasswordInput
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                minLength={8}
              />
            </label>
            <label>
              {t('passwordAgain')}
              <PasswordInput
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
              />
            </label>
          </>
        )}
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <button className="auth-primary" disabled={!ready || busy}>
          {busy
            ? t('loading')
            : t(
                step === 1
                  ? 'sendCode'
                  : step === 2
                    ? 'confirm'
                    : 'updatePassword',
              )}
        </button>
      </form>
    </AuthShell>
  );
}
