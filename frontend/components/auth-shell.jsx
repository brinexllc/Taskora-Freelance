'use client';
import Link from 'next/link';
import { Eye, EyeOff, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { languages } from '@/lib/i18n';

export function AuthShell({ children, wide = false }) {
  const { language, setLanguage } = useApp();
  return (
    <main className="auth-page">
      <Link className="auth-brand" href="/">
        ✣ Taskora
      </Link>
      <div className="auth-language" aria-label="Language">
        {languages.map(([key, label]) => (
          <button
            type="button"
            key={key}
            className={language === key ? 'active' : ''}
            onClick={() => setLanguage(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <section className={`auth-card ${wide ? 'auth-card-wide' : ''}`}>
        {children}
      </section>
    </main>
  );
}
export function PasswordInput({
  value,
  onChange,
  autoComplete = 'current-password',
  ...props
}) {
  const { t } = useApp();
  const [visible, setVisible] = useState(false);
  return (
    <div className="password-input">
      <input
        {...props}
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        maxLength={128}
        required
      />
      <button
        type="button"
        onClick={() => setVisible(!visible)}
        aria-label={t(visible ? 'hide' : 'show')}
      >
        {visible ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
    </div>
  );
}
export function OneIdDisabled() {
  const { t } = useApp();
  return (
    <button type="button" className="oneid-disabled" disabled>
      <ShieldCheck size={18} />
      {t('oneid')}
    </button>
  );
}
export function AuthBack() {
  const { t } = useApp();
  return (
    <Link className="auth-back" href="/login">
      ← {t('back')}
    </Link>
  );
}
