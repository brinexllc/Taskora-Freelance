'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useApp } from '@/components/app-providers';
import {
  beginOperation,
  readOperation,
  completeOperation,
} from '@/lib/pending-operation';
import { apiRequest, apiErrorMessage } from '@/lib/api';
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
  const [pendingPayment, setPendingPayment] = useState(null);
  const [pendingWithdrawal, setPendingWithdrawal] = useState(null);
  const [provider, setProvider] = useState('click');
  const [returnedPayment, setReturnedPayment] = useState(null);
  const [checkingPayment, setCheckingPayment] = useState(false);
  const remote = useRemote('wallet', {
    token: session.authenticated,
    query: { page, kind },
  });
  const [amount, setAmount] = useState(''),
    [withdrawAmount, setWithdrawAmount] = useState(''),
    [recipient, setRecipient] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  useEffect(() => {
    void Promise.resolve().then(() => {
      const payment = readOperation(session.user.id, 'payments/checkout');
      const withdrawal = readOperation(session.user.id, 'wallet/withdraw');
      setPendingPayment(payment);
      setPendingWithdrawal(withdrawal);
      if (payment) {
        setAmount(payment.amount);
        setProvider(payment.provider);
      }
      if (withdrawal) {
        setWithdrawAmount(withdrawal.amount);
        setRecipient(String(withdrawal.recipient));
        setConfirmed(withdrawal.confirmed);
      }
    });
  }, [session.user.id]);
  const reloadWallet = remote.reload;
  useEffect(() => {
    const reference = new URLSearchParams(window.location.search).get(
      'payment',
    );
    if (!reference || !session.authenticated) return;
    const controller = new AbortController();
    let timer;
    let attempts = 0;
    async function checkPayment() {
      setCheckingPayment(true);
      try {
        const payment = await apiRequest(
          `payments/${encodeURIComponent(reference)}`,
          {
            token: session.authenticated,
            signal: controller.signal,
          },
        );
        if (controller.signal.aborted) return;
        setReturnedPayment(payment);
        if (['paid', 'cancelled'].includes(payment.status)) {
          reloadWallet();
          setCheckingPayment(false);
          return;
        }
        if (++attempts < 30) timer = window.setTimeout(checkPayment, 4000);
        else setCheckingPayment(false);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(apiErrorMessage(err, t));
          setCheckingPayment(false);
        }
      }
    }
    void checkPayment();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [session.authenticated, reloadWallet, t]);
  async function action(path, body) {
    setBusy(true);
    setError('');
    try {
      const financial = ['payments/checkout', 'wallet/withdraw'].includes(path);
      const savedBody = financial
        ? beginOperation(session.user.id, path, body)
        : body;
      if (path === 'payments/checkout') setPendingPayment(savedBody);
      if (path === 'wallet/withdraw') setPendingWithdrawal(savedBody);
      const result = await apiRequest(path, {
        method: 'POST',
        token: session.authenticated,
        body: savedBody,
      });
      if (financial) completeOperation(session.user.id, path);
      if (path === 'payments/checkout') setPendingPayment(null);
      if (path === 'wallet/withdraw') setPendingWithdrawal(null);
      if (result.checkout_url) window.location.assign(result.checkout_url);
      else {
        remote.reload();
        setWithdrawAmount('');

        setConfirmed(false);
      }
    } catch (err) {
      setError(apiErrorMessage(err, t));
      if (!err.uncertain && err.status && err.status !== 409) {
        completeOperation(session.user.id, path);
        if (path === 'payments/checkout') setPendingPayment(null);
        if (path === 'wallet/withdraw') setPendingWithdrawal(null);
      }
    } finally {
      setBusy(false);
    }
  }
  const data = remote.data;
  const returnedStatus =
    data?.payments.find(
      (payment) => payment.reference === returnedPayment?.reference,
    )?.status || returnedPayment?.status;
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
      {(checkingPayment || returnedPayment) && (
        <Notice>
          {returnedStatus === 'paid'
            ? t('paymentConfirmed')
            : returnedStatus === 'cancelled'
              ? t('paymentCancelled')
              : checkingPayment
                ? t('paymentChecking')
                : t('paymentWaiting')}
        </Notice>
      )}
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
                {data.payme_test_mode && provider === 'payme' && (
                  <Notice>{t('testPayment')}</Notice>
                )}
                {pendingPayment && (
                  <Notice>
                    {t('uncertainRequest')}
                    <br />
                    {t('requestKey')}:{' '}
                    <code>{pendingPayment.idempotency_key}</code>
                  </Notice>
                )}

                {!data.click_available && !data.payme_available && (
                  <Notice>{t('paymentUnavailable')}</Notice>
                )}
                <form
                  className="t-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action('payments/checkout', { amount, provider });
                  }}
                >
                  <Field label={t('paymentMethod')}>
                    <select
                      disabled={busy || !!pendingPayment}
                      value={provider}
                      onChange={(e) => {
                        setProvider(e.target.value);
                      }}
                    >
                      <option value="click" disabled={!data.click_available}>
                        CLICK
                      </option>
                      <option value="payme" disabled={!data.payme_available}>
                        PAYME
                      </option>
                    </select>
                  </Field>
                  <Field label={t('topupAmount')}>
                    <input
                      type="number"
                      min="1000"
                      step="0.01"
                      disabled={busy || !!pendingPayment}
                      value={amount}
                      onChange={(e) => {
                        setAmount(e.target.value);
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
                    {t(
                      pendingPayment
                        ? 'retrySameRequest'
                        : provider === 'click'
                          ? 'payClick'
                          : 'payPayme',
                    )} · {money(amount, language)}
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
                {pendingWithdrawal && (
                  <Notice>
                    {t('uncertainRequest')}
                    <br />
                    {t('requestKey')}:{' '}
                    <code>{pendingWithdrawal.idempotency_key}</code>
                  </Notice>
                )}
                {!session.user.email_verified_at &&
                  !session.user.phone_verified_at && (
                    <Notice>
                      <Link href="/verification">{t('contactPolicy')}</Link>
                    </Notice>
                  )}

                <p className="muted">{t('withdrawalHint')}</p>
                <form
                  className="t-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action('wallet/withdraw', {
                      amount: withdrawAmount,
                      recipient: Number(recipient),
                      confirmed,
                    });
                  }}
                >
                  <Field label={t('amount')}>
                    <input
                      type="number"
                      min="0.01"
                      max={data.balance}
                      step="0.01"
                      disabled={busy || !!pendingWithdrawal}
                      value={withdrawAmount}
                      onChange={(e) => {
                        setWithdrawAmount(e.target.value);
                        setConfirmed(false);
                      }}
                      required
                    />
                  </Field>
                  <Field
                    label={t('confirmedRecipient')}
                    hint={t('recipientRequired')}
                  >
                    <select
                      value={recipient}
                      disabled={busy || !!pendingWithdrawal}
                      onChange={(e) => {
                        setRecipient(e.target.value);
                        setConfirmed(false);
                      }}
                      required
                    >
                      <option value="">—</option>
                      {(data.recipients || []).map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.destination} · {item.provider}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <label className="t-check">
                    <input
                      type="checkbox"
                      disabled={busy || !!pendingWithdrawal}
                      checked={confirmed}
                      onChange={(e) => setConfirmed(e.target.checked)}
                    />
                    {t('confirmWithdrawal')}: {money(withdrawAmount, language)}
                  </label>
                  <button
                    className="t-button secondary"
                    disabled={
                      busy ||
                      !confirmed ||
                      !recipient ||
                      (!pendingWithdrawal && Number(data.balance) <= 0)
                    }
                  >
                    {t(
                      pendingWithdrawal
                        ? 'retrySameRequest'
                        : 'requestWithdrawal',
                    )} · {money(withdrawAmount, language)}
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
                              {entry.withdrawal
                                ? ` · ${t('withdrawal')} #${entry.withdrawal}`
                                : ''}
                            </small>
                            {entry.contract && (
                              <Link
                                className="text-link"
                                href={`/contracts/${entry.contract}`}
                              >
                                {t('contract')} #{entry.contract}
                              </Link>
                            )}
                            {['escrow_release', 'refund'].includes(
                              entry.kind,
                            ) &&
                              entry.contract_actual_fee_amount === '0.00' && (
                                <small style={{ display: 'block' }}>
                                  {t('platformFee')}: {money('0.00', language)}
                                </small>
                              )}
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
                          {payment.status === 'paid' &&
                            payment.receipt?.status === 'ready' &&
                            payment.receipt?.url && (
                              <a
                                className="text-link"
                                href={payment.receipt.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                {t('fiscalReceipt')}
                              </a>
                            )}
                          {payment.receipt?.status === 'pending' && (
                            <small className="muted">
                              {t('fiscalReceiptPending')}
                            </small>
                          )}
                          {payment.receipt?.status === 'unavailable' && (
                            <small className="muted">
                              {t('fiscalReceiptUnavailable')}
                            </small>
                          )}
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
                              ? 'withdrawalPending'
                              : item.status === 'paid'
                                ? 'withdrawalPaid'
                                : item.status,
                          )}
                        />
                      </div>
                      <p>{item.destination}</p>
                      {['processing', 'reconciliation_required'].includes(
                        item.status,
                      ) && <Notice>{t('withdrawalLocked')}</Notice>}
                      {item.provider_reference && (
                        <p>{item.provider_reference}</p>
                      )}
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
