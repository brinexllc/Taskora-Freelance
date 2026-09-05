'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiRequest } from '@/lib/api';
import {
  Empty,
  Field,
  Notice,
  RemoteState,
  Status,
  useRemote,
} from '@/components/taskora-ui';
import { date, money } from '@/lib/i18n';
export function WalletView() {
  const { t, language, session } = useApp();
  const remote = useRemote('wallet', { token: session.token });
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
            <div className="two-columns">
              <section className="t-card">
                <h2>{t('topup')}</h2>
                {!data.click_available && (
                  <Notice>{t('paymentUnavailable')}</Notice>
                )}
                <form
                  className="t-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action('payments/checkout', {
                      amount,
                      provider: 'click',
                    });
                  }}
                >
                  <Field label={t('topupAmount')}>
                    <input
                      type="number"
                      min="1000"
                      step="0.01"
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                      required
                    />
                  </Field>
                  <button
                    className="t-button"
                    disabled={busy || !data.click_available}
                  >
                    {t('payClick')}
                  </button>
                  <small className="muted">{t('paymeSoon')}</small>
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
                      onChange={(e) => setWithdrawAmount(e.target.value)}
                      required
                    />
                  </Field>
                  <Field label={t('destination')} hint={t('destinationHint')}>
                    <input
                      value={destination}
                      onChange={(e) => setDestination(e.target.value)}
                      maxLength={160}
                      required
                    />
                  </Field>
                  <button
                    className="t-button secondary"
                    disabled={busy || Number(data.balance) <= 0}
                  >
                    {t('requestWithdrawal')}
                  </button>
                </form>
              </section>
            </div>
            <section className="t-card section-heading">
              <h2>{t('history')}</h2>
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
            <section className="t-card">
              <h2>{t('payments')}</h2>
              {data.payments.filter((p) => p.provider === 'click').length ? (
                <div className="list-stack">
                  {data.payments
                    .filter((p) => p.provider === 'click')
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
