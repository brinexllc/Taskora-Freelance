'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useApp } from '@/components/app-providers';
import { apiRequest, downloadFile } from '@/lib/api';
import { dateTime } from '@/lib/i18n';
import {
  Field,
  Notice,
  Pager,
  RemoteState,
  useRemote,
} from '@/components/taskora-ui';

export function ProposalDiscussion({ proposal }) {
  const { t } = useApp();
  const [conversation, setConversation] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <div className="proposal-discussion">
      <button
        className="t-button secondary"
        disabled={busy}
        onClick={async () => {
          if (conversation) {
            setConversation(null);
            return;
          }
          setBusy(true);
          setError('');
          try {
            setConversation(
              await apiRequest(`proposals/${proposal.id}/conversation`, {
                method: 'POST',
              }),
            );
          } catch (e) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {t(conversation ? 'close' : 'privateDiscussion')}
      </button>
      <Notice error>{error}</Notice>
      {conversation && <ProposalChat conversation={conversation} />}
    </div>
  );
}

export function ProposalChat({ conversation }) {
  const { t, session, language } = useApp();
  const [page, setPage] = useState(1);
  const [text, setText] = useState('');
  const [file, setFile] = useState(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const path = `proposal-conversations/${conversation.id}`;
  const remote = useRemote(`${path}/messages`, {
    token: session.authenticated,
    query: { page, page_size: 50 },
  });
  const reload = remote.reload;
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) reload();
    }, 7000);
    return () => clearInterval(timer);
  }, [reload]);
  useEffect(() => {
    const unread = remote.data?.results?.filter(
      (item) => !item.read_at && item.sender !== session.user.id,
    );
    if (!unread?.length || document.hidden) return;
    apiRequest(`${path}/read`, {
      method: 'POST',
      body: {
        through_id: Math.max(...remote.data.results.map((item) => item.id)),
      },
    })
      .then(reload)
      .catch((e) => setError(e.message));
  }, [remote.data, path, session.user.id, reload]);
  return (
    <section className="proposal-chat">
      <h3>
        {t('privateDiscussion')} #{conversation.proposal}
      </h3>
      <p className="muted">{t('conversationPrivacy')}</p>
      {conversation.contract && (
        <Link
          className="text-link"
          href={`/contracts/${conversation.contract}`}
        >
          {t('viewContract')}
        </Link>
      )}
      <Notice error>{error}</Notice>
      <Notice>{notice}</Notice>
      <RemoteState remote={remote}>
        <div className="chat-messages" aria-live="polite">
          {remote.data?.results?.map((item) => (
            <article
              className={`chat-message ${item.sender === session.user.id ? 'mine' : ''}`}
              key={item.id}
            >
              <strong>{item.sender_name}</strong>
              <p className="preserve-lines">{item.text}</p>
              {item.filename && (
                <button
                  className="chat-file"
                  onClick={() =>
                    downloadFile(
                      `${path}/messages/${item.id}/download`,
                      undefined,
                      item.filename,
                    ).catch((e) => setError(e.message))
                  }
                >
                  {item.filename}
                </button>
              )}
              <time>
                {dateTime(item.created_at, language)}{' '}
                {item.sender === session.user.id && item.read_at ? '✓✓' : ''}
              </time>
            </article>
          ))}
        </div>
        <Pager data={remote.data} page={page} onChange={setPage} />
      </RemoteState>
      <form
        className="t-form"
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          setBusy(true);
          setError('');
          try {
            if (file?.size > 25 * 1024 * 1024) throw new Error(t('fileSize'));
            const body = new FormData();
            body.append('text', text);
            if (file) body.append('file', file);
            await apiRequest(`${path}/messages`, { method: 'POST', body });
            setText('');
            setFile(null);
            form.reset();
            reload();
          } catch (e) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label={t('messageText')}>
          <textarea
            value={text}
            maxLength={5000}
            onChange={(e) => setText(e.target.value)}
          />
        </Field>
        <Field label={t('attachFile')}>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </Field>
        <button className="t-button" disabled={busy || (!text.trim() && !file)}>
          {t('send')}
        </button>
      </form>
      <details>
        <summary>{t('reportConversation')}</summary>
        <form
          className="t-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError('');
            setNotice('');
            try {
              await apiRequest(`${path}/report`, {
                method: 'POST',
                body: { reason },
              });
              setReason('');
              setNotice(t('reportSubmitted'));
            } catch (e) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field label={t('reportReason')}>
            <textarea
              required
              minLength={10}
              maxLength={3000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          <button className="t-button secondary" disabled={busy}>
            {t('reportConversation')}
          </button>
        </form>
      </details>
    </section>
  );
}

export function ProposalConversations() {
  const { t, session } = useApp();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const remote = useRemote('proposal-conversations', {
    token: session.authenticated,
    query: { page },
  });
  return (
    <section className="t-card">
      <h2>{t('proposalConversations')}</h2>
      <RemoteState remote={remote}>
        <div className="actions">
          {remote.data?.results?.map((item) => (
            <button
              key={item.id}
              className="t-button secondary"
              onClick={() =>
                setSelected(selected?.id === item.id ? null : item)
              }
            >
              {t('privateDiscussion')} #{item.proposal}{' '}
              {item.unread_count > 0
                ? `(${item.unread_count} ${t('unread')})`
                : ''}
            </button>
          ))}
        </div>
        <Pager data={remote.data} page={page} onChange={setPage} />
      </RemoteState>
      {selected && <ProposalChat key={selected.id} conversation={selected} />}
    </section>
  );
}
