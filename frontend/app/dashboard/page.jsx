'use client';
import Link from 'next/link';
import { BriefcaseBusiness, FileCheck2, Wallet } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useApp } from '@/components/app-providers';
import {
  Empty,
  Notice,
  Pager,
  ProjectCard,
  RemoteState,
  Status,
  useRemote,
  WorkspaceFrame,
} from '@/components/taskora-ui';
import {
  MessagesView,
  NotificationsView,
} from '@/components/contract-workspace';
import { WalletView } from '@/components/wallet-view';
import { SettingsView } from '@/components/settings-view';
import { ProfileShowcase } from '@/components/profile-showcase';
import { EliteDashboard } from '@/components/elite-dashboard';
import { OrdersList } from '@/app/projects/page';
import { apiRequest } from '@/lib/api';
import { useSearchParams } from 'next/navigation';
import { date, money } from '@/lib/i18n';

export default function DashboardPage() {
  const { t, session, ready, theme } = useApp();
  const search = useSearchParams();
  const view = search.get('view') || 'home';
  if (!ready || !session?.user || !session.user.role)
    return (
      <div className="taskora-app">
        <p className="empty-state">{t('loading')}</p>
      </div>
    );
  return (
    <WorkspaceFrame activeView={view}>
      {['orders', 'contracts', 'proposals'].includes(view) && (
        <nav className="workspace-order-tabs" aria-label={t('orders')}>
          {['orders', 'contracts', 'proposals'].map((key) => (
            <Link
              key={key}
              href={`/dashboard?view=${key}`}
              aria-current={view === key ? 'page' : undefined}
            >
              {t(key)}
            </Link>
          ))}
        </nav>
      )}
      {view === 'messages' ? (
        <MessagesView />
      ) : view === 'notifications' ? (
        <NotificationsView />
      ) : view === 'wallet' ? (
        <WalletView />
      ) : view === 'settings' ? (
        <SettingsView />
      ) : view === 'contracts' ? (
        <ContractList />
      ) : view === 'proposals' ? (
        <ProposalList />
      ) : view === 'orders' ? (
        <>
          <div className="page-heading">
            <div>
              <h1>
                {t(session.user.role === 'client' ? 'myOrders' : 'orders')}
              </h1>
              <p className="dashboard-subtitle">{t('ordersSubtitle')}</p>
            </div>
            {session.user.role === 'client' ? (
              <Link href="/projects/new" className="t-button">
                {t('createOrder')}
              </Link>
            ) : (
              <Link
                href="/dashboard?view=proposals"
                className="t-button secondary"
              >
                {t('myProposals')}
              </Link>
            )}
          </div>
          <OrdersList mine={session.user.role === 'client'} />
        </>
      ) : view === 'profile' ? (
        <ProfileShowcase profile={session.user.profile} />
      ) : theme === 'dark' ? (
        <EliteDashboard />
      ) : (
        <>
          <div className="page-heading">
            <div>
              <h1>
                {t('welcome')},{' '}
                {session.user.first_name || session.user.full_name}{' '}
                <span aria-hidden="true">👋</span>
              </h1>
              <p className="dashboard-subtitle">{t('dashboardPrompt')}</p>
            </div>
            <div className="actions">
              <Link
                className="t-button secondary"
                href={
                  session.user.role === 'client'
                    ? '/freelancers'
                    : '/dashboard?view=profile'
                }
              >
                {t(
                  session.user.role === 'client'
                    ? 'findFreelancers'
                    : 'profile',
                )}
              </Link>
              <Link
                className="t-button"
                href={
                  session.user.role === 'client' ? '/projects/new' : '/projects'
                }
              >
                {t(
                  session.user.role === 'client'
                    ? 'createOrder'
                    : 'browseOrders',
                )}
              </Link>
            </div>
          </div>
          <Stats />
          <RecommendedOrders />
          <div className="dashboard-mobile-extra">
            <ContractList compact />
            <RecentMessages />
          </div>
        </>
      )}
    </WorkspaceFrame>
  );
}
function Stats() {
  const { t, language, session } = useApp();
  const remote = useRemote('dashboard', { token: session.token });
  const primary = [
    ['active_orders', 'activeOrders', 'orders', BriefcaseBusiness],
    ['active_contracts', 'activeContracts', 'contracts', FileCheck2],
    [
      'completed_orders',
      'completedOrders',
      'contracts&status=completed',
      FileCheck2,
    ],
    ['balance', 'wallet', 'wallet', Wallet],
  ];
  return (
    <RemoteState remote={remote}>
      <div className="t-stats">
        {primary.map(([key, label, view, Icon]) => (
          <Link
            className={`t-stat ${key === 'balance' ? 'wallet-stat' : ''}`}
            key={key}
            href={`/dashboard?view=${String(view)}`}
          >
            <span>{t(label)}</span>
            <i>
              <Icon size={20} />
            </i>
            <strong>
              {key === 'balance'
                ? money(remote.data?.[key], language)
                : remote.data?.[key]}
            </strong>
          </Link>
        ))}
      </div>
      <div className="dashboard-activity">
        {[
          ['in_review', 'inReview', 'contracts'],
          ['new_proposals', 'newProposals', 'orders'],
          ['unread_messages', 'messages', 'messages'],
          ['unread_notifications', 'notifications', 'notifications'],
        ].map(([key, label, view]) => (
          <Link key={key} href={`/dashboard?view=${String(view)}`}>
            {t(label)} <b>{remote.data?.[key] || 0}</b>
          </Link>
        ))}
      </div>
    </RemoteState>
  );
}

function RecentMessages() {
  const { t, session } = useApp();
  const remote = useRemote('contracts', {
    token: session.token,
    query: { page_size: 2 },
  });
  return (
    <section className="dashboard-recent-messages">
      <div className="page-heading">
        <h2>{t('recentMessages')}</h2>
        <Link href="/dashboard?view=messages" className="text-link">
          {t('all')} →
        </Link>
      </div>
      <RemoteState remote={remote}>
        {remote.data?.results.length ? (
          remote.data.results.map((c) => (
            <Link key={c.id} href={`/dashboard?view=messages&contract=${c.id}`}>
              <span className="conversation-avatar">
                {(c.customer === session.user.id
                  ? c.freelancer_name
                  : c.customer_name
                )?.slice(0, 1)}
              </span>
              <span className="conversation-copy">
                <strong>
                  {c.customer === session.user.id
                    ? c.freelancer_name
                    : c.customer_name}
                </strong>
                <span>{c.project_title}</span>
              </span>
            </Link>
          ))
        ) : (
          <Empty text={t('noContracts')} />
        )}
      </RemoteState>
    </section>
  );
}

function ContractList({ compact = false }) {
  const { t, language, session } = useApp();
  const [page, setPage] = useState(1),
    [filter, setFilter] = useState('');
  useEffect(() => {
    void Promise.resolve().then(() => {
      if (
        new URLSearchParams(window.location.search).get('status') ===
        'completed'
      )
        setFilter('completed');
    });
  }, []);
  const remote = useRemote('contracts', {
    token: session.token,
    query: { page, status: filter },
  });
  return (
    <section className="contract-list">
      <div className="page-heading">
        <h2>{t('contracts')}</h2>
        {compact && (
          <Link className="text-link" href="/dashboard?view=contracts">
            {t('all')} →
          </Link>
        )}
      </div>
      {!compact && (
        <div className="filter-tabs">
          {[
            ['', 'all'],
            ['active', 'activeContracts'],
            ['completed', 'completedContracts'],
          ].map(([value, label]) => (
            <button
              key={value}
              className={filter === value ? 'active' : ''}
              onClick={() => {
                setFilter(value);
                setPage(1);
              }}
            >
              {t(label)}
            </button>
          ))}
        </div>
      )}
      <RemoteState remote={remote}>
        {remote.data?.results.length ? (
          <div className="list-stack">
            {remote.data.results
              .slice(0, compact ? 3 : undefined)
              .map((contract) => (
                <article className="t-card" key={contract.id}>
                  <div className="row-between">
                    <span className="eyebrow">
                      {t('contract')} #{contract.id}
                    </span>
                    <Status value={contract.status} />
                  </div>
                  <h3>{contract.project_title}</h3>
                  <p className="muted">
                    {contract.customer_name} · {contract.freelancer_name}
                  </p>
                  <div className="row-between">
                    <strong>{money(contract.amount, language)}</strong>
                    <Link
                      className="t-button secondary"
                      href={`/contracts/${contract.id}`}
                    >
                      {t('viewContract')}
                    </Link>
                  </div>
                </article>
              ))}
          </div>
        ) : (
          <Empty text={t('noContracts')} />
        )}{' '}
        {!compact && (
          <Pager data={remote.data} page={page} onChange={setPage} />
        )}
      </RemoteState>
    </section>
  );
}
function ProposalList() {
  const { t, session, language } = useApp();
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');
  const remote = useRemote('proposals', {
    token: session.token,
    query: { page, mine: 1 },
  });
  return (
    <>
      <h1>{t('myProposals')}</h1>
      <Notice error>{error}</Notice>
      <RemoteState remote={remote}>
        {remote.data?.results.length ? (
          remote.data.results.map((item) => (
            <article className="t-card" key={item.id}>
              <div className="row-between">
                <h3>{item.project_title}</h3>
                <Status value={item.status} />
              </div>
              <p>{item.cover_letter}</p>
              <p>
                {money(item.amount, language)} · {item.delivery_days}{' '}
                {t('days')} · {date(item.created_at, language)}
              </p>
              {item.status === 'pending' && (
                <button
                  className="text-link"
                  onClick={async () => {
                    try {
                      await apiRequest(`proposals/${item.id}/withdraw`, {
                        method: 'POST',
                        token: session.token,
                      });
                      remote.reload();
                    } catch (e) {
                      setError(e.message);
                    }
                  }}
                >
                  {t('withdrawProposal')}
                </button>
              )}
              <Link
                className="text-link"
                href={
                  item.contract_id
                    ? `/contracts/${item.contract_id}`
                    : `/projects/${item.project}`
                }
              >
                {t(item.contract_id ? 'viewContract' : 'details')}
              </Link>
            </article>
          ))
        ) : (
          <Empty text={t('noProposals')} />
        )}
        <Pager data={remote.data} page={page} onChange={setPage} />
      </RemoteState>
    </>
  );
}

function RecommendedOrders() {
  const { t } = useApp();
  const remote = useRemote('projects', { query: { page_size: 3 } });
  return (
    <section className="dashboard-recommended">
      <div className="page-heading">
        <h2>{t('latestOrders')}</h2>
        <Link className="text-link" href="/projects">
          {t('all')} →
        </Link>
      </div>
      <RemoteState remote={remote}>
        {remote.data?.results.length ? (
          <div className="t-grid">
            {remote.data.results.map((project) => (
              <ProjectCard key={project.id} project={project} compact />
            ))}
          </div>
        ) : (
          <Empty text={t('noOrders')} />
        )}
      </RemoteState>
    </section>
  );
}
