'use client';
import { useEffect, useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiRequest, apiErrorMessage } from '@/lib/api';
import {
  beginOperation,
  completeOperation,
  readOperation,
} from '@/lib/pending-operation';
import { Field, Notice } from '@/components/taskora-ui';
export function ProjectClone({ project }) {
  const { t, session } = useApp();
  const [deadline, setDeadline] = useState('');
  const [copy, setCopy] = useState(false);
  const [pending, setPending] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const path = `projects/${project.id}/clone`;
  useEffect(() => {
    void Promise.resolve().then(() => {
      const saved = readOperation(session.user.id, path);
      setPending(saved);
      if (saved) {
        setDeadline(saved.deadline);
        setCopy(saved.copy_attachments);
      }
    });
  }, [session.user.id, path]);
  return (
    <section className="t-card">
      <h2>{t('cloneProject')}</h2>
      <p>{t('cloneHint')}</p>
      <Notice error>{error}</Notice>
      {pending && (
        <Notice>
          {t('uncertainRequest')}
          <br />
          <code>{pending.idempotency_key}</code>
        </Notice>
      )}
      <form
        className="t-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          try {
            const body = beginOperation(session.user.id, path, {
              deadline,
              copy_attachments: copy,
              attachments_rights_confirmed: copy,
            });
            setPending(body);
            const draft = await apiRequest(path, { method: 'POST', body });
            completeOperation(session.user.id, path);
            window.location.assign(`/projects/${draft.id}`);
          } catch (e) {
            setError(apiErrorMessage(e, t));
            if (!e.uncertain && e.status && e.status !== 409) {
              completeOperation(session.user.id, path);
              setPending(null);
            }
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label={t('deadline')}>
          <input
            type="date"
            required
            value={deadline}
            disabled={busy || !!pending}
            onChange={(e) => setDeadline(e.target.value)}
          />
        </Field>
        {!!project.attachments?.length && (
          <label className="t-check">
            <input
              type="checkbox"
              checked={copy}
              disabled={busy || !!pending}
              onChange={(e) => setCopy(e.target.checked)}
            />
            {t('copyAttachments')}
          </label>
        )}
        <button className="t-button" disabled={busy}>
          {t(pending ? 'retrySameRequest' : 'cloneProject')}
        </button>
      </form>
    </section>
  );
}
