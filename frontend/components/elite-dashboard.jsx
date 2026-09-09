'use client';
import Link from 'next/link';
import {
  Award,
  BriefcaseBusiness,
  CirclePlus,
  FileCheck2,
  Wallet,
} from 'lucide-react';
import { useApp } from '@/components/app-providers';
import {
  Avatar,
  Empty,
  RemoteState,
  Status,
  useRemote,
} from '@/components/taskora-ui';
import { date, money } from '@/lib/i18n';

export function EliteDashboard() {
  const { t, session, language } = useApp();
  const customer = session.user.role === 'client';
  const stats = useRemote('dashboard', { token: session.token });
  const contracts = useRemote('contracts', {
    token: session.token,
    query: { status: 'active', page_size: 5 },
  });
  const people = useRemote(customer ? 'profiles' : 'projects', {
    query: { page_size: 2 },
  });
  const measures = [
    ['active_contracts', 'activeContracts', BriefcaseBusiness, false],
    [
      customer ? 'total_spent' : 'total_earned',
      customer ? 'totalSpent' : 'totalEarned',
      Wallet,
      true,
    ],
    ['in_review', 'inReview', FileCheck2, false],
    [
      customer ? 'frozen_balance' : 'pending_balance',
      'escrowBalance',
      Wallet,
      true,
    ],
  ];
  return (
    <div className="elite-dashboard">
      <div className="page-heading">
        <div>
          <h1>
            {t('welcome')}, {session.user.first_name || session.user.full_name}{' '}
            <span aria-hidden="true">👋</span>
          </h1>
          <p className="dashboard-subtitle">{t('dashboardPrompt')}</p>
        </div>
        <Link className="t-button secondary" href="/dashboard?view=wallet">
          {t('viewReport')}
        </Link>
      </div>
      <RemoteState remote={stats}>
        <div className="elite-stat-grid">
          {measures.map(([key, label, Icon, currency]) => (
            <Link
              key={String(key)}
              href={`/dashboard?view=${currency ? 'wallet' : 'contracts'}`}
            >
              <Icon size={20} />
              <span>{t(label)}</span>
              <strong>
                {currency
                  ? money(stats.data?.[key], language)
                  : (stats.data?.[key] ?? '—')}
              </strong>
            </Link>
          ))}
        </div>
      </RemoteState>
      <div className="elite-dashboard-columns">
        <section>
          <div className="row-between">
            <h2>{t('activeProjects')}</h2>
            <Link className="text-link" href="/dashboard?view=contracts">
              {t('all')} →
            </Link>
          </div>
          <RemoteState remote={contracts}>
            {contracts.data?.results.length ? (
              <div className="elite-project-table">
                <table>
                  <thead>
                    <tr>
                      <th>{t('project')}</th>
                      <th>{t(customer ? 'freelancer' : 'client')}</th>
                      <th>{t('status')}</th>
                      <th>{t('amount')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contracts.data.results.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <Link href={`/contracts/${c.id}`}>
                            {c.project_title}
                          </Link>
                          <small>
                            {t('deadline')}: {date(c.deadline, language)}
                          </small>
                        </td>
                        <td>
                          <span className="elite-table-person">
                            <i>
                              {(customer
                                ? c.freelancer_name
                                : c.customer_name
                              )?.slice(0, 1)}
                            </i>
                            {customer ? c.freelancer_name : c.customer_name}
                          </span>
                        </td>
                        <td>
                          <Status value={c.status} />
                        </td>
                        <td>{money(c.amount, language)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="elite-panel">
                <Empty text={t('noContracts')} />
                <Link
                  className="text-link"
                  href={customer ? '/projects/new' : '/projects'}
                >
                  {t(customer ? 'createOrder' : 'browseOrders')} →
                </Link>
              </div>
            )}
          </RemoteState>
        </section>
        <aside>
          <section className="elite-panel elite-quick-actions">
            <h2>{t('quickActions')}</h2>
            <Link
              className="t-button"
              href={customer ? '/projects/new' : '/projects'}
            >
              <CirclePlus size={19} />
              {t(customer ? 'createOrder' : 'browseOrders')}
            </Link>
            <Link className="t-button secondary" href="/dashboard?view=wallet">
              <Wallet size={17} />
              {t(customer ? 'topUp' : 'wallet')}
            </Link>
          </section>
          <section className="elite-recommendations">
            <h2>{t('recommended')}</h2>
            <RemoteState remote={people}>
              {people.data?.results.length ? (
                people.data.results.map((p) => (
                  <Link
                    className="elite-panel"
                    key={p.id}
                    href={
                      customer ? `/freelancers/${p.id}` : `/projects/${p.id}`
                    }
                  >
                    {customer ? (
                      <Avatar profile={p} />
                    ) : (
                      <BriefcaseBusiness size={24} />
                    )}
                    <span>
                      <strong>{customer ? p.full_name : p.title}</strong>
                      <small>
                        {customer
                          ? p.professional_title ||
                            p.skill_details
                              ?.slice(0, 2)
                              .map((s) => s.label)
                              .join(' · ')
                          : money(p.budget_max, language)}
                      </small>
                    </span>
                  </Link>
                ))
              ) : (
                <Empty text={t(customer ? 'noFreelancers' : 'noOrders')} />
              )}
            </RemoteState>
          </section>
        </aside>
      </div>
      <section className="elite-program elite-panel">
        <div>
          <h2>{t('profileReadiness')}</h2>
          <p>{t('completeProfileHint')}</p>
          <Link className="t-button secondary" href="/dashboard?view=settings">
            {t('editProfile')}
          </Link>
        </div>
        <Award size={64} />
      </section>
    </div>
  );
}
