'use client';
import Link from 'next/link';
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
    ready && session?.token && id ? `contracts/${id}` : null,
    { token: session?.token },
  );
  const integrations = useRemote('integrations');
  const [agree, setAgree] = useState(false),
    [file, setFile] = useState(null),
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
        token: session.token,
        body,
      });
      setNotice(t(success));
      remote.reload();
    } catch (err) {
      setError(err.message);
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
    await act('submit', data, 'workSent');
  }
  async function pay(provider) {
    setBusy(true);
    setError('');
    try {
      const result = await apiRequest('payments/checkout', {
        method: 'POST',
        token: session.token,
        body: { contract: Number(id), provider },
      });
      if (result.checkout_url) window.location.assign(result.checkout_url);
      else {
        setNotice(t('paymentSuccess'));
        remote.reload();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
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
              {contract.status === 'signing' && !signed && (
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
                      act('sign', { accepted: true }, 'contractSigned')
                    }
                  >
                    {t('sign')}
                  </button>
                </div>
              )}
            </section>
            {work && (
              <section className="t-card">
                <div className="row-between">
                  <h2>{t('preview')}</h2>
                  <span className="muted">
                    {date(work.created_at, language)}
                  </span>
                </div>
                <p className="preserve-lines">{work.preview_text}</p>
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
                        session.token,
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
            {contract.status === 'review' && customer && (
              <section className="t-card">
                <h2>{t('review')}</h2>
                {!integrations.data?.click && (
                  <Notice>{t('paymentUnavailable')}</Notice>
                )}
                <div className="actions">
                  <button
                    className="t-button"
                    disabled={busy || !integrations.data?.click}
                    onClick={() => pay('click')}
                  >
                    {t('payClick')}
                  </button>
                  <button
                    className="t-button secondary"
                    disabled={busy}
                    onClick={() => pay('wallet')}
                  >
                    {t('payWallet')}
                  </button>
                </div>
                <form
                  className="t-form section-heading"
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
            <div className="actions section-heading">
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
