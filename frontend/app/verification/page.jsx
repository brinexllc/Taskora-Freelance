'use client';
import Link from 'next/link';
import { useState } from 'react';
import {
  ArrowRight,
  Check,
  CircleCheck,
  Clock3,
  Fingerprint,
  Info,
  KeyRound,
  Mail,
  ShieldCheck,
  UsersRound,
} from 'lucide-react';
import { AuthShell } from '@/components/auth-shell';
import { useApp } from '@/components/app-providers';
import { date } from '@/lib/i18n';

export default function VerificationPage() {
  const { t, session, ready, language } = useApp();
  const [view, setView] = useState('connect');
  const continueHref = !session?.user
    ? '/login'
    : session.user.role
      ? '/dashboard'
      : '/role';
  return (
    <AuthShell variant="verification">
      <ol className="verification-steps">
        {['connect', 'confirm', 'result'].map((step) => (
          <li key={step} className={view === step ? 'current' : ''}>
            <button
              type="button"
              onClick={() => setView(step)}
              aria-current={view === step ? 'step' : undefined}
            >
              {t(step)}
            </button>
          </li>
        ))}
      </ol>
      {!ready ? (
        <p>{t('loading')}</p>
      ) : view === 'connect' ? (
        <>
          <div className="auth-step-icon">
            <ShieldCheck />
          </div>
          <h1>{t('verification')}</h1>
          <p className="auth-subtitle">{t('verificationHint')}</p>
          <div className="verification-providers">
            {[
              [KeyRound, 'ONEID'],
              [Fingerprint, 'MYID'],
            ].map(([Icon, name]) => (
              <button key={name} disabled title={t('verificationUnavailable')}>
                <span>
                  <Icon size={24} />
                </span>
                <strong>{name}</strong>
                <ArrowRight size={18} />
              </button>
            ))}
          </div>
          <div className="verification-info">
            <Info size={20} />
            <p>{t('verificationProvider')}</p>
          </div>
          <output className="verification-unavailable">
            {t('verificationUnavailable')}
          </output>
          {session?.user && (
            <button
              className="text-link identity-details-link"
              onClick={() => setView('confirm')}
            >
              {t('identityDetailsLink')} →
            </button>
          )}
        </>
      ) : view === 'confirm' ? (
        <>
          <div className="auth-step-icon">
            <UsersRound />
          </div>
          <h1>{t('verificationDetails')}</h1>
          <p className="auth-subtitle">{t('identitySource')}</p>
          <div className="identity-card">
            <header>
              <strong>{t('verificationDetails')}</strong>
              <span>{t('identityNotVerified')}</span>
            </header>
            <dl>
              {[
                ['fullName', session?.user?.full_name],
                [
                  'birthDate',
                  session?.user?.birth_date
                    ? date(session.user.birth_date, language)
                    : null,
                ],
                ['passportSeries', null],
                ['personalId', null],
              ].map(([key, value]) => (
                <div key={key}>
                  <dt>{t(key)}</dt>
                  <dd>{value || t('identityMissing')}</dd>
                </div>
              ))}
            </dl>
          </div>
          <label className="identity-consent">
            <input type="checkbox" disabled />
            {t('identityConsent')}
          </label>
          <button
            className="auth-primary"
            disabled
            title={t('verificationUnavailable')}
          >
            {t('confirm')}
          </button>
          <p className="verification-unavailable">
            {t('verificationUnavailable')}
          </p>
        </>
      ) : (
        <VerificationResult status="unverified" />
      )}
      <Link className="auth-primary verification-continue" href={continueHref}>
        {t(
          !session?.user
            ? 'login'
            : session.user.role
              ? 'dashboard'
              : 'chooseRole',
        )}
        <ArrowRight size={16} />
      </Link>
    </AuthShell>
  );
}

// Provider-backed states are prepared for the integration. The current application
// only supplies "unverified"; URL parameters and self-declared profile fields cannot approve identity.
export function VerificationResult({ status }) {
  const { t } = useApp();
  const success = status === 'verified';
  const pending = status === 'pending';
  const Icon = success ? CircleCheck : pending ? Clock3 : ShieldCheck;
  return (
    <div
      className={`verification-result ${success ? 'success' : pending ? 'pending' : 'unverified'}`}
    >
      <div className="auth-step-icon">
        <Icon />
      </div>
      <h1>
        {t(
          success
            ? 'identitySuccess'
            : pending
              ? 'identityPending'
              : 'verificationUnavailableTitle',
        )}
      </h1>
      {success ? (
        <div className="identity-outcome">
          <p>
            <Check size={18} />
            {t('verificationComplete')}
          </p>
          <p>
            <Check size={18} />
            {t('identityAccountSecure')}
          </p>
        </div>
      ) : pending ? (
        <>
          <progress aria-label={t('identityPending')} />
          <div className="identity-outcome">
            <Mail size={22} />
            <p>{t('identityPendingHint')}</p>
          </div>
        </>
      ) : (
        <div className="identity-outcome">
          <Info size={22} />
          <p>{t('identityInactive')}</p>
        </div>
      )}
    </div>
  );
}
