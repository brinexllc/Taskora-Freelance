'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  MessageSquare,
  Paperclip,
  Send,
  ShieldCheck,
  Star,
} from 'lucide-react';
import { useApp } from '@/components/app-providers';
import { apiRequest, downloadFile } from '@/lib/api';
import {
  Empty,
  Field,
  Notice,
  Pager,
  RemoteState,
  Status,
  useRemote,
} from '@/components/taskora-ui';
import { date, dateTime, money } from '@/lib/i18n';

export function ContractWorkspace({ contract, act, busy }) {
  const { t, language, session } = useApp();
  const [reason, setReason] = useState('');
  const [confirm, setConfirm] = useState('');
  const [rating, setRating] = useState('5');
  const [review, setReview] = useState('');
  const customer = session.user.id === contract.customer;
  const confirmAction = (action) => setConfirm(action);
  const settled = contract.actual_fee_amount !== null;
  const amounts = [
    ['amount', contract.amount],
    ...(settled
      ? [
          ['grossReleased', contract.released_amount],
          ['platformFee', contract.actual_fee_amount],
          ['netAmount', contract.actual_net_amount],
          ['customerRefund', contract.refunded_amount],
        ]
      : [
          ['platformFee', contract.fee_amount],
          ['netAmount', contract.net_amount],
        ]),
    ['frozenBalance', contract.escrow_amount],
  ];
  return (
    <>
      <section className="t-card escrow-panel">
        <div className="row-between">
          <h2>
            <ShieldCheck size={20} /> {t('securePayment')}
          </h2>
          <Status value={contract.status} />
        </div>
        <p>
          <strong>{t(settled ? 'actualSettlement' : 'originalPlan')}</strong> ·{' '}
          {t('platformFee')}: {contract.fee_percent}%
        </p>
        <dl className="escrow-amounts">
          {amounts.map(([label, value]) => (
            <div key={label}>
              <dt>{t(label)}</dt>
              <dd>{money(value, language)}</dd>
            </div>
          ))}
        </dl>
        {settled ? (
          <details>
            <summary>{t('originalPlan')}</summary>
            <p>
              {t('amount')}: {money(contract.amount, language)} ·{' '}
              {t('platformFee')}: {contract.fee_percent}% (
              {money(contract.fee_amount, language)}) · {t('netAmount')}:{' '}
              {money(contract.net_amount, language)}
            </p>
          </details>
        ) : (
          <p>
            {t('customerReserves')}: {money(contract.amount, language)}.{' '}
            {t('feeNotSettled')}
          </p>
        )}
        <p className="muted">{t('escrowHint')}</p>
        {contract.deadline && (
          <p>
            {t('deadline')}: {date(contract.deadline, language)}
          </p>
        )}
        {contract.status === 'awaiting_funding' && customer && (
          <div className="actions">
            <button
              className="t-button"
              disabled={busy}
              onClick={() => confirmAction('fund')}
            >
              {t('fundContract')}
            </button>
            <Link className="text-link" href="/dashboard?view=wallet">
              {t('topup')}
            </Link>
          </div>
        )}
        {contract.status === 'submitted' && customer && (
          <button
            className="t-button"
            disabled={busy}
            onClick={() => confirmAction('accept')}
          >
            {t('acceptWork')}
          </button>
        )}
        {[
          'draft',
          'customer_accepted',
          'freelancer_accepted',
          'awaiting_funding',
        ].includes(contract.status) && (
          <button
            className="text-link danger"
            disabled={busy}
            onClick={() => confirmAction('cancel')}
          >
            {t('cancelContract')}
          </button>
        )}
        {['active', 'submitted'].includes(contract.status) && (
          <details className="dispute-form">
            <summary>{t('openDispute')}</summary>
            <Field label={t('disputeReason')}>
              <textarea
                minLength={10}
                maxLength={5000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </Field>
            <button
              className="t-button secondary"
              disabled={busy || reason.trim().length < 10}
              onClick={() => confirmAction('dispute')}
            >
              {t('openDispute')}
            </button>
          </details>
        )}
        {confirm && (
          <div className="confirmation-panel" role="alert">
            <strong>{t(`confirm_${confirm}`)}</strong>
            <p>
              {money(contract.amount, language)} · {t('platformFee')}:{' '}
              {contract.fee_percent}% ({money(contract.fee_amount, language)}) ·{' '}
              {t('netAmount')}: {money(contract.net_amount, language)}
            </p>
            <div className="actions">
              <button
                className="t-button"
                disabled={busy}
                onClick={async () => {
                  await act(confirm, { confirmed: true, reason }, 'saved');
                  setConfirm('');
                }}
              >
                {t('confirm')}
              </button>
              <button
                className="t-button secondary"
                onClick={() => setConfirm('')}
              >
                {t('back')}
              </button>
            </div>
          </div>
        )}
      </section>
      {contract.dispute && (
        <section className="t-card">
          <h2>{t('dispute')}</h2>
          <Status value={contract.dispute.status} />
          <p>{contract.dispute.reason}</p>
          <Notice>{t('disputeEvidence')}</Notice>
          {contract.dispute.resolution && <p>{contract.dispute.resolution}</p>}
        </section>
      )}
      <Chat contract={contract} />
      {contract.status === 'completed' && (
        <section className="t-card">
          <h2>
            <Star size={20} /> {t('reviews')}
          </h2>
          {contract.reviews.map((item) => (
            <article className="review-item" key={item.id}>
              <strong>
                {item.author_name} · {'★'.repeat(item.rating)}
              </strong>
              <p>{item.text}</p>
            </article>
          ))}
          {!contract.reviews.some(
            (item) => item.author === session.user.id,
          ) && (
            <form
              className="t-form"
              onSubmit={(e) => {
                e.preventDefault();
                void act(
                  'review',
                  { rating: Number(rating), text: review },
                  'reviewSent',
                );
              }}
            >
              <Field label={t('rating')}>
                <select
                  value={rating}
                  onChange={(e) => setRating(e.target.value)}
                >
                  {[5, 4, 3, 2, 1].map((n) => (
                    <option key={n} value={n}>
                      {'★'.repeat(n)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('reviewText')}>
                <textarea
                  required
                  maxLength={3000}
                  value={review}
                  onChange={(e) => setReview(e.target.value)}
                />
              </Field>
              <button className="t-button" disabled={busy}>
                {t('leaveReview')}
              </button>
            </form>
          )}
        </section>
      )}
      <section className="t-card">
        <h2>{t('contractHistory')}</h2>
        <ol className="event-timeline">
          {contract.events.map((item) => (
            <li key={item.id}>
              <strong>{t(item.kind)}</strong>
              <p>{item.description}</p>
              <time>{dateTime(item.created_at, language)}</time>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

export function Chat({ contract }) {
  const { t, session, language } = useApp();
  const [page, setPage] = useState(1);
  const [text, setText] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const remote = useRemote(`contracts/${contract.id}/messages`, {
    token: session.token,
    query: { page, page_size: 50 },
  });
  const reloadMessages = remote.reload;
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) reloadMessages();
    }, 7000);
    return () => clearInterval(timer);
  }, [reloadMessages]);
  useEffect(() => {
    if (
      remote.data?.results.some(
        (m) => !m.read_at && !m.system && m.sender !== session.user.id,
      )
    )
      apiRequest(`contracts/${contract.id}/messages/read`, {
        method: 'POST',
        token: session.token,
      }).catch((e) => setError(e.message));
  }, [remote.data, contract.id, session.token, session.user.id]);
  async function send(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body = new FormData();
      body.append('text', text);
      if (file) body.append('file', file);
      await apiRequest(`contracts/${contract.id}/messages`, {
        method: 'POST',
        token: session.token,
        body,
      });
      setText('');
      setFile(null);
      e.target.reset();
      remote.reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="t-card chat-panel">
      <div className="row-between">
        <h2>
          <MessageSquare size={20} /> {t('workChat')}
        </h2>
        <span className="muted">#{contract.id}</span>
      </div>
      <Notice error>{error || remote.error}</Notice>
      <div className="chat-messages" aria-live="polite">
        {!remote.data && remote.loading && <p>{t('loading')}</p>}
        {remote.data?.results.map((m) => (
          <article
            key={m.id}
            className={`chat-message ${m.system ? 'system' : m.sender === session.user.id ? 'mine' : ''}`}
          >
            <strong>{m.sender_name || 'Taskora'}</strong>
            <p>{m.text}</p>
            {m.filename && (
              <button
                className="chat-file"
                onClick={() =>
                  downloadFile(
                    `contracts/${contract.id}/messages/${m.id}/download`,
                    session.token,
                    m.filename,
                  ).catch((e) => setError(e.message))
                }
              >
                <Paperclip size={14} /> {m.filename}
              </button>
            )}
            <time>
              {dateTime(m.created_at, language)}{' '}
              {m.sender === session.user.id && m.read_at ? '✓✓' : ''}
            </time>
          </article>
        ))}
      </div>
      <Pager data={remote.data} page={page} onChange={setPage} />
      {!['completed', 'cancelled'].includes(contract.status) && (
        <form className="chat-compose" onSubmit={send}>
          <textarea
            aria-label={t('messageText')}
            placeholder={t('messageText')}
            value={text}
            maxLength={5000}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="row-between">
            <label className="chat-attach">
              <Paperclip size={18} />
              <span>{file?.name || t('attachFile')}</span>
              <input
                type="file"
                aria-label={t('attachFile')}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <button
              className="t-button"
              disabled={busy || (!text.trim() && !file)}
            >
              <Send size={16} />
              {t('send')}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export function NotificationsView() {
  const { t, session, language } = useApp();
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');
  const remote = useRemote('notifications', {
    token: session.token,
    query: { page },
  });
  async function read(path) {
    try {
      await apiRequest(path, { method: 'POST', token: session.token });
      remote.reload();
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <>
      <div className="page-heading">
        <h1>{t('notifications')}</h1>
        <button
          className="t-button secondary"
          onClick={() => read('notifications/read-all')}
        >
          {t('readAll')}
        </button>
      </div>
      <Notice error>{error}</Notice>
      <RemoteState remote={remote}>
        {remote.data?.results.length ? (
          remote.data.results.map((n) => (
            <article
              className={`t-card notification-item ${n.read_at ? '' : 'unread'}`}
              key={n.id}
            >
              <Status value={n.kind} />
              <p>{n.text}</p>
              <small>{dateTime(n.created_at, language)}</small>
              <div className="actions">
                {n.link && (
                  <Link className="text-link" href={n.link}>
                    {t('details')} →
                  </Link>
                )}
                {!n.read_at && (
                  <button
                    className="text-link"
                    onClick={() => read(`notifications/${n.id}/read`)}
                  >
                    {t('markRead')}
                  </button>
                )}
              </div>
            </article>
          ))
        ) : (
          <Empty text={t('noNotifications')} />
        )}
        <Pager data={remote.data} page={page} onChange={setPage} />
      </RemoteState>
    </>
  );
}

export function MessagesView() {
  const { t, session } = useApp();
  const [selected, setSelected] = useState(null);
  const [page, setPage] = useState(1);
  const remote = useRemote('contracts', {
    token: session.token,
    query: { page },
  });
  return (
    <>
      <h1>{t('messages')}</h1>
      <div className="messenger-layout">
        <section className="conversation-list">
          <RemoteState remote={remote}>
            {remote.data?.results.length ? (
              remote.data.results.map((c) => (
                <button
                  className={selected?.id === c.id ? 'selected' : ''}
                  key={c.id}
                  onClick={() => setSelected(c)}
                >
                  <strong>
                    {c.customer === session.user.id
                      ? c.freelancer_name
                      : c.customer_name}
                  </strong>
                  <span>{c.project_title}</span>
                  <Status value={c.status} />
                </button>
              ))
            ) : (
              <Empty text={t('noContracts')} />
            )}
            <Pager data={remote.data} page={page} onChange={setPage} />
          </RemoteState>
        </section>
        {selected ? (
          <Chat key={selected.id} contract={selected} />
        ) : (
          <Empty text={t('selectConversation')} />
        )}
      </div>
    </>
  );
}
