'use client';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiRequest, apiErrorMessage } from '@/lib/api';
import {
  PageShell,
  Notice,
  RemoteState,
  useRemote,
} from '@/components/taskora-ui';
export function LegalText({ content }) {
  const { t } = useApp();
  if (!content) return null;
  if (typeof content === 'string')
    return <p className="preserve-lines">{content}</p>;
  return (
    <div className="legal-text">
      {Object.entries(content).map(([key, value]) => {
        if (Array.isArray(value))
          return (
            <ol key={key}>
              {value.map((line, index) => (
                <li key={index}>{String(line)}</li>
              ))}
            </ol>
          );
        if (value && typeof value === 'object')
          return (
            <dl key={key}>
              {Object.entries(value).map(([label, text]) => (
                <div key={label}>
                  <dt>{t(label)}</dt>
                  <dd className="preserve-lines">{String(text)}</dd>
                </div>
              ))}
            </dl>
          );
        return (
          <p className="preserve-lines" key={key}>
            {String(value || '')}
          </p>
        );
      })}
    </div>
  );
}
export function LegalPage({ privacy = false }) {
  const { t, language, session } = useApp();
  const [busy, setBusy] = useState(false);
  const [acceptedHash, setAcceptedHash] = useState('');
  const [error, setError] = useState('');
  const legal = useRemote('legal/current', { query: { lang: language } });
  const document = legal.data;
  return (
    <PageShell>
      <article className="t-card legal-page">
        <h1>{t(privacy ? 'privacyLink' : 'termsLink')}</h1>
        <RemoteState remote={legal}>
          {document && (
            <>
              {!document.approved && (
                <Notice error>{t('legalUnapproved')}</Notice>
              )}
              <p>
                {t('legalVersion')}: {document.version} · {document.language}
              </p>
              <LegalText content={Object.fromEntries(Object.entries(document.content || {}).filter(([key]) => !['operator', 'support'].includes(key)))} />
              <details>
                <summary>SHA-256</summary>
                <code className="legal-hash">{document.hash}</code>
              </details>
              <h2 id="support">{t('operatorContacts')}</h2>
              <LegalText content={{ operator: Object.fromEntries(Object.entries(document.operator || {}).filter(([, value]) => typeof value === 'string' && value.trim())), support: Object.fromEntries(Object.entries(document.support || {}).filter(([, value]) => typeof value === 'string' && value.trim())) }} />
              {!document.support?.email && <p>{t('contactNotConfigured')}</p>}
              <Notice error>{error}</Notice>
              {acceptedHash === document.hash && <Notice>{t('consentSaved')}</Notice>}
              {session?.authenticated && <button className="t-button" disabled={busy || acceptedHash === document.hash} onClick={async () => {
                setBusy(true); setError('');
                try { await apiRequest('auth/consent', { method: 'POST', body: { accept_terms: true, terms_version: document.version, terms_hash: document.hash, language: document.language } }); setAcceptedHash(document.hash); }
                catch (e) { setError(apiErrorMessage(e, t)); } finally { setBusy(false); }
              }}>{t('acceptCurrentTerms')} · {document.version}</button>}
            </>
          )}
        </RemoteState>
      </article>
    </PageShell>
  );
}
