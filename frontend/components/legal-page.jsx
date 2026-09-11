'use client';
import { useApp } from '@/components/app-providers';
import { PageShell, Notice } from '@/components/taskora-ui';
export function LegalPage({ privacy = false }) {
  const { t } = useApp();
  return (
    <PageShell>
      <article className="t-card legal-page">
        <span className="eyebrow">TASKORA · MVP 1.0</span>
        <h1>{t(privacy ? 'privacyLink' : 'termsLink')}</h1>
        <p>{t(privacy ? 'privacyBody' : 'termsBody')}</p>
        {!privacy && (
          <>
            <h2 id="how-it-works">{t('how')}</h2>
            <ol>
              {['step1', 'step2', 'step3'].map((key) => (
                <li key={key}>{t(key)}</li>
              ))}
            </ol>
            <h2 id="fees">{t('platformFee')}</h2>
            <p>{t('feeTerms')}</p>
            <h2 id="support">{t('designSupport')}</h2>
            <p>{t('supportGuidance')}</p>
          </>
        )}
        <Notice>{t('legalNotice')}</Notice>
      </article>
    </PageShell>
  );
}
