'use client';
import Link from 'next/link';
import { AcceptanceTerms } from '@/components/acceptance-terms';
import { ContractWorkspace } from '@/components/contract-workspace';
import Image from 'next/image';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiRequest, downloadWork } from '@/lib/api';
import {
  Field,
  Notice,
  PageShell,
  RemoteState,
  Status,
  readImage,
  useRemote,
} from '@/components/taskora-ui';
import { date, money } from '@/lib/i18n';
export default function ContractPage() {
  const { id } = useParams();
  const { t, language, session, ready } = useApp();
  const remote = useRemote(
    ready && session?.authenticated && id ? `contracts/${id}` : null,
    { token: session?.authenticated },
  );
  const [agree, setAgree] = useState(false),
    [file, setFile] = useState(null),
    [demoUrl, setDemoUrl] = useState(''),
    [verificationSteps, setVerificationSteps] = useState(''),
    [preview, setPreview] = useState(''),
    [image, setImage] = useState(''),
    [note, setNote] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const contract = remote.data;
  const customer = contract?.customer === session?.user?.id;
  const work = contract?.deliverables?.[0];
  const signed = customer
    ? contract?.customer_signed_at
    : contract?.freelancer_signed_at;
  async function act(action, body, success) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await apiRequest(`contracts/${id}/${action}`, {
        method: 'POST',
        token: session.authenticated,
        body,
      });
      setNotice(t(success));
      remote.reload();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function submit(event) {
    event.preventDefault();
    if (!file) {
      setError(t('noFile'));
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setError(t('fileSize'));
      return;
    }
    const data = new FormData();
    data.append('file', file);
    data.append('preview_text', preview);
    data.append('preview_image', image);
    data.append('demo_url', demoUrl);
    data.append('verification_steps', verificationSteps);
    await act('submit', data, 'workSent');
  }
  return (
    <PageShell>
      <Link className="back-link" href="/dashboard?view=contracts">
        ← {t('contracts')}
      </Link>
      <RemoteState remote={remote}>
        {contract && (
          <>
            <div className="page-heading">
              <div>
                <span className="eyebrow">
                  {t('contract')} #{contract.id}
                </span>
                <h1>{contract.project_title}</h1>
              </div>
              <Status value={contract.status} />
            </div>
            <Notice error>{error}</Notice>
            <Notice>{notice}</Notice>
            <section className="t-card">
              <div className="row-between">
                <h2>{t('terms')}</h2>
                <strong>
                  {money(contract.amount, language)} · {contract.delivery_days}{' '}
                  {t('days')}
                </strong>
              </div>
              <div className="contract-terms">{contract.terms}</div>
              <div className="signature-grid">
                {[
                  [
                    'client',
                    contract.customer_name,
                    contract.customer_signed_at,
                  ],
                  [
                    'freelancer',
                    contract.freelancer_name,
                    contract.freelancer_signed_at,
                  ],
                ].map(([role, name, time]) => (
                  <div key={role}>
                    <small>{t(role)}</small>
                    <p>
                      <strong>{name}</strong>
                    </p>
                    <Status
                      value={time ? 'accepted' : 'pending'}
                      label={t(time ? 'signed' : 'notSigned')}
                    />
                    {time && <p className="muted">{date(time, language)}</p>}
                  </div>
                ))}
              </div>
              {['draft', 'customer_accepted', 'freelancer_accepted'].includes(
                contract.status,
              ) &&
                !signed && (
                  <div className="t-form">
                    <label className="t-check">
                      <input
                        type="checkbox"
                        checked={agree}
                        onChange={(e) => setAgree(e.target.checked)}
                      />
                      {t('agree')}
                    </label>
                    <button
                      className="t-button"
                      disabled={!agree || busy}
                      onClick={() =>
                        act(
                          'sign',
                          {
                            accepted: true,
                            expected_version: contract.version,
                          },
                          'contractSigned',
                        )
                      }
                    >
                      {t('sign')}
                    </button>
                  </div>
                )}
            </section>
            <AcceptanceTerms
              key={contract.version}
              contract={contract}
              act={act}
              busy={busy}
            />
            {work && (
              <section className="t-card">
                <div className="row-between">
                  <h2>{t('preview')}</h2>
                  <span className="muted">
                    {date(work.created_at, language)}
                  </span>
                </div>
                <p className="preserve-lines">{work.preview_text}</p>
                {work.demo_url && /^https:\/\//i.test(work.demo_url) && (
                  <a
                    className="t-button secondary"
                    href={work.demo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t('inspectDemo')}
                  </a>
                )}
                {work.verification_steps && (
                  <>
                    <h3>{t('verification_steps')}</h3>
                    <p className="preserve-lines">{work.verification_steps}</p>
                  </>
                )}
                {work.review_due_at && (
                  <p>
                    {t('reviewDue')}: {date(work.review_due_at, language)}
                  </p>
                )}
                <p className="muted">{t('noAutomaticPayment')}</p>
                {work.preview_image && (
                  <>
                    <Image
                      width={1200}
                      height={800}
                      unoptimized
                      className="preview-image"
                      src={work.preview_image}
                      alt={t('preview')}
                    />
                    <p className="preview-watermark">
                      TASKORA · {t('preview')}
                    </p>
                  </>
                )}
                <Notice>
                  {t(
                    contract.can_download ? 'paymentSuccess' : 'previewNotice',
                  )}
                </Notice>
                {work.revision_note && (
                  <Notice>
                    <strong>{t('revisionRequested')}</strong>
                    <p className="preserve-lines">{work.revision_note}</p>
                  </Notice>
                )}
                <button
                  className="t-button"
                  disabled={!contract.can_download || busy}
                  onClick={async () => {
                    setBusy(true);
                    setError('');
                    try {
                      await downloadWork(
                        contract.id,
                        session.authenticated,
                        work.filename,
                      );
                    } catch (err) {
                      setError(err.message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  {t(contract.can_download ? 'download' : 'locked')}
                </button>
              </section>
            )}
            {contract.status === 'active' && !customer && (
              <section className="t-card">
                <h2>{t('submitWork')}</h2>
                <p className="muted">{t('previewHint')}</p>
                <form className="t-form" onSubmit={submit}>
                  <Field label={t('workFile')}>
                    <input
                      type="file"
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                      required
                    />
                  </Field>
                  <Field label={t('previewText')}>
                    <textarea
                      value={preview}
                      onChange={(e) => setPreview(e.target.value)}
                      maxLength={15000}
                      required
                    />
                  </Field>
                  <Field label={t('demo_url')}>
                    <input
                      type="url"
                      pattern="https://.*"
                      value={demoUrl}
                      onChange={(e) => setDemoUrl(e.target.value)}
                    />
                  </Field>
                  <Field label={t('verification_steps')}>
                    <textarea
                      value={verificationSteps}
                      onChange={(e) => setVerificationSteps(e.target.value)}
                      maxLength={5000}
                      required={contract.acceptance_workflow_version === 1}
                    />
                  </Field>
                  <Field label={t('previewImage')}>
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      onChange={async (e) => {
                        try {
                          setImage(await readImage(e.target.files?.[0]));
                        } catch (err) {
                          setError(err.message);
                          e.target.value = '';
                        }
                      }}
                    />
                  </Field>
                  <button className="t-button" disabled={busy}>
                    {busy ? t('loading') : t('submit')}
                  </button>
                </form>
              </section>
            )}
            {contract.status === 'submitted' && customer && (
              <section className="t-card">
                <h2>{t('inReview')}</h2>
                <form
                  className="t-form revision-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void act('revision', { note }, 'revisionRequested');
                  }}
                >
                  <Field label={t('revisionNote')}>
                    <textarea
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      maxLength={3000}
                      required
                    />
                  </Field>
                  <button className="t-button secondary" disabled={busy}>
                    {t('requestRevision')}
                  </button>
                </form>
              </section>
            )}
            <ContractWorkspace contract={contract} act={act} busy={busy} />
            <div className="actions contract-actions">
              <button
                className="t-button secondary"
                disabled={busy || remote.loading}
                onClick={remote.reload}
              >
                {t('refresh')}
              </button>
              <Link
                className="text-link"
                href={`/projects/${contract.project}`}
              >
                {t('orders')} →
              </Link>
            </div>
          </>
        )}
      </RemoteState>
    </PageShell>
  );
}
