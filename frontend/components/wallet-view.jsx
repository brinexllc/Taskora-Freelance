'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiRequest } from '@/lib/api';
import {
  Empty,
  Pager,
  Field,
  Notice,
  RemoteState,
  Status,
  useRemote,
} from '@/components/taskora-ui';
import { date, money } from '@/lib/i18n';
export function WalletView() {
  const { t, language, session } = useApp();
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [paymentKey, setPaymentKey] = useState(null);
  const [withdrawKey, setWithdrawKey] = useState(null);
  const [provider, setProvider] = useState('click');
  const remote = useRemote('wallet', {
    token: session.token,
    query: { page, kind },
  });
  const [amount, setAmount] = useState(''),
    [withdrawAmount, setWithdrawAmount] = useState(''),
    [destination, setDestination] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function action(path, body) {
    setBusy(true);
    setError('');
    try {
      const result = await apiRequest(path, {
        method: 'POST',
        token: session.token,
        body,
      });
      if (result.checkout_url) window.location.assign(result.checkout_url);
      else {
        remote.reload();
        setWithdrawAmount('');
        setWithdrawKey(null);
        setConfirmed(false);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  const data = remote.data;
  return (
    <>
      <div className="page-heading">
        <h1>{t('wallet')}</h1>
        <button
          className="t-button secondary"
          onClick={remote.reload}
          disabled={remote.loading}
        >
          {t('refresh')}
        </button>
      </div>
      <Notice error>{error}</Notice>
      <RemoteState remote={remote}>
        {data && (
          <>
            <section className="balance-panel">
              <span>{t('balance')}</span>
              <strong>{money(data.balance, language)}</strong>
              <span>{t('history')}</span>
            </section>
            <div className="t-stats">
              {[
                ['frozen_balance', 'frozenBalance'],
                ['pending_balance', 'pendingBalance'],
                ['pending_withdrawal', 'pendingWithdrawal'],
              ].map(([key, label]) => (
                <div className="t-stat" key={key}>
                  <span>{t(label)}</span>
                  <strong>{money(data[key], language)}</strong>
                </div>
              ))}
            </div>
            <div className="two-columns">
              <section className="t-card">
                <h2>{t('topup')}</h2>
                {!data.click_available && !data.payme_available && (
                  <Notice>{t('paymentUnavailable')}</Notice>
                )}
                <form
                  className="t-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action('payments/checkout', {
                      amount,
                      idempotency_key: paymentKey || crypto.randomUUID(),
                      provider,
                    });
                  }}
                >
                  <Field label={t('paymentMethod')}>
                    <select
                      value={provider}
                      onChange={(e) => {
                        setProvider(e.target.value);
                        setPaymentKey(crypto.randomUUID());
                      }}
                    >
                      <option value="click">CLICK</option>
                      <option value="payme">PAYME</option>
                    </select>
                  </Field>
                  <Field label={t('topupAmount')}>
                    <input
                      type="number"
                      min="1000"
                      step="0.01"
                      value={amount}
                      onChange={(e) => {
                        setAmount(e.target.value);
                        setPaymentKey(crypto.randomUUID());
                      }}
                      required
                    />
                  </Field>
                  <button
                    className="t-button"
                    disabled={
                      busy ||
                      !(provider === 'click'
                        ? data.click_available
                        : data.payme_available)
                    }
                  >
                    {t(provider === 'click' ? 'payClick' : 'payPayme')}
                  </button>
                  {!(provider === 'click'
                    ? data.click_available
                    : data.payme_available) && (
                    <small className="muted">{t('paymentUnavailable')}</small>
                  )}
                </form>
              </section>
              <section className="t-card">
                <h2>{t('withdraw')}</h2>
                <p className="muted">{t('withdrawalHint')}</p>
                <form
                  className="t-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action('wallet/withdraw', {
                      amount: withdrawAmount,
                      destination,
                      confirmed,
                      idempotency_key: withdrawKey || crypto.randomUUID(),
                    });
                  }}
                >
                  <Field label={t('amount')}>
                    <input
                      type="number"
                      min="0.01"
                      max={data.balance}
                      step="0.01"
                      value={withdrawAmount}
                      onChange={(e) => {
                        setWithdrawAmount(e.target.value);
                        setWithdrawKey(crypto.randomUUID());
                        setConfirmed(false);
                      }}
                      required
                    />
                  </Field>
                  <Field label={t('destination')} hint={t('destinationHint')}>
                    <input
                      value={destination}
                      onChange={(e) => {
                        setDestination(e.target.value);
                        setWithdrawKey(crypto.randomUUID());
                        setConfirmed(false);
                      }}
                      maxLength={160}
                      required
                    />
                  </Field>
                  <label className="t-check">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      onChange={(e) => setConfirmed(e.target.checked)}
                    />
                    {t('confirmWithdrawal')}: {money(withdrawAmount, language)}
                  </label>
                  <button
                    className="t-button secondary"
                    disabled={busy || !confirmed || Number(data.balance) <= 0}
                  >
                    {t('requestWithdrawal')}
                  </button>
                </form>
              </section>
            </div>
            <section className="t-card">
              <div className="row-between">
                <h2>{t('history')}</h2>
                <select
                  aria-label={t('history')}
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">{t('all')}</option>
                  {[
                    'topup',
                    'escrow_hold',
                    'escrow_release',
                    'refund',
                    'withdrawal',
                    'platform_fee',
                  ].map((k) => (
                    <option key={k} value={k}>
                      {t(k === 'topup' ? 'topupKind' : k)}
                    </option>
                  ))}
                </select>
              </div>
              {data.entries.length ? (
                <div className="table-scroll">
                  <table className="t-table">
                    <thead>
                      <tr>
                        <th>{t('date')}</th>
                        <th>{t('description')}</th>
                        <th>{t('amount')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.entries.map((entry) => (
                        <tr key={entry.id}>
                          <td>{date(entry.created_at, language)}</td>
                          <td>
                            {t(
                              entry.kind === 'topup' ? 'topupKind' : entry.kind,
                            )}
                            <small
                              className="muted"
                              style={{ display: 'block' }}
                            >
                              #{entry.id}
                            </small>
                          </td>
                          <td
                            className={`amount ${Number(entry.amount) > 0 ? 'positive' : ''}`}
                          >
                            {Number(entry.amount) > 0 ? '+' : ''}
                            {money(entry.amount, language)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty text={t('noTransactions')} />
              )}
            </section>
            <Pager data={data} page={page} onChange={setPage} />
            <section className="t-card">
              <h2>{t('payments')}</h2>
              {data.payments.filter((p) =>
                ['click', 'payme'].includes(p.provider),
              ).length ? (
                <div className="list-stack">
                  {data.payments
                    .filter((p) => ['click', 'payme'].includes(p.provider))
                    .map((payment) => (
                      <article className="t-card" key={payment.reference}>
                        <div className="row-between">
                          <strong>{money(payment.amount, language)}</strong>
                          <Status
                            value={payment.status}
                            label={
                              payment.status === 'pending'
                                ? t('paymentPending')
                                : undefined
                            }
                          />
                        </div>
                        <p className="muted">
                          {payment.provider.toUpperCase()} ·{' '}
                          {date(payment.created_at, language)}
                        </p>
                        <div className="actions">
                          {payment.status === 'pending' && (
                            <button
                              className="text-link"
                              disabled={busy}
                              onClick={() =>
                                action(`payments/${payment.reference}/cancel`)
                              }
                            >
                              {t('cancel')}
                            </button>
                          )}
                          {payment.contract && (
                            <Link
                              className="text-link"
                              href={`/contracts/${payment.contract}`}
                            >
                              {t('contract')} #{payment.contract}
                            </Link>
                          )}
                        </div>
                      </article>
                    ))}
                </div>
              ) : (
                <Empty text={t('noTransactions')} />
              )}
            </section>
            <section className="t-card">
              <h2>{t('withdrawals')}</h2>
              {data.withdrawals.length ? (
                <div className="list-stack">
                  {data.withdrawals.map((item) => (
                    <article className="t-card" key={item.id}>
                      <div className="row-between">
                        <strong>{money(item.amount, language)}</strong>
                        <Status
                          value={item.status}
                          label={t(
                            item.status === 'pending'
                              ? 'processing'
                              : item.status === 'paid'
                                ? 'withdrawalPaid'
                                : item.status,
                          )}
                        />
                      </div>
                      <p>{item.destination}</p>
                      <p className="muted">
                        {date(item.created_at, language)} · #{item.id}
                      </p>
                      {item.provider_reference && (
                        <p>
                          {t('payoutReference')}: {item.provider_reference}
                        </p>
                      )}
                      {item.status === 'pending' && (
                        <button
                          className="text-link"
                          disabled={busy}
                          onClick={() =>
                            action(`wallet/withdrawals/${item.id}/cancel`)
                          }
                        >
                          {t('cancel')}
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              ) : (
                <Empty text={t('noTransactions')} />
              )}
            </section>
          </>
        )}
      </RemoteState>
    </>
  );
}
