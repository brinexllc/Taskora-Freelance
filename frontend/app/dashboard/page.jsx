'use client';
import Link from 'next/link';
import {
  BriefcaseBusiness,
  Bell,
  MessageSquare,
  Send,
  FileCheck2,
  Home,
  LogOut,
  Menu,
  Settings,
  UserRound,
  Wallet,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { useApp } from '@/components/app-providers';
import {
  Avatar,
  Empty,
  LanguageSelect,
  Logo,
  Notice,
  Pager,
  ProfileSummary,
  ProjectCard,
  RemoteState,
  Status,
  useRemote,
} from '@/components/taskora-ui';
import {
  MessagesView,
  NotificationsView,
} from '@/components/contract-workspace';
import { WalletView } from '@/components/wallet-view';
import { SettingsView } from '@/components/settings-view';
import { OrdersList } from '@/app/projects/page';
import { apiRequest, logout } from '@/lib/api';
import { date, money } from '@/lib/i18n';

export default function DashboardPage() {
  const { t, session, ready, clearSession } = useApp();
  const [view, setView] = useState('home'),
    [mobile, setMobile] = useState(false),
    [error, setError] = useState('');
  useEffect(() => {
    void Promise.resolve().then(() => {
      const key = new URLSearchParams(window.location.search).get('view');
      if (
        [
          'home',
          'profile',
          'orders',
          'contracts',
          'wallet',
          'settings',
          'proposals',
          'messages',
          'notifications',
        ].includes(key)
      )
        setView(key);
    });
  }, []);
  async function signOut() {
    setError('');
    try {
      await logout(session.token);
      clearSession();
      window.location.assign('/');
    } catch (err) {
      setError(err.message);
    }
  }
  if (!ready || !session?.user || !session.user.role)
    return (
      <div className="taskora-app">
        <p className="empty-state">{t('loading')}</p>
      </div>
    );
  const nav = [
    [Home, 'home'],
    [UserRound, 'profile'],
    [BriefcaseBusiness, 'orders'],
    [FileCheck2, 'contracts'],
    [Send, 'proposals'],
    [MessageSquare, 'messages'],
    [Bell, 'notifications'],
    [Wallet, 'wallet'],
    [Settings, 'settings'],
  ];
  return (
    <div className="taskora-app workspace">
      {mobile && (
        <button
          className="sidebar-overlay"
          aria-label={t('close')}
          onClick={() => setMobile(false)}
        />
      )}
      <aside className={`workspace-sidebar ${mobile ? 'open' : ''}`}>
        <Logo />
        <nav>
          {nav.map(([Icon, key]) => (
            <Link
              href={`/dashboard?view=${String(key)}`}
              key={key}
              className={view === key ? 'active' : ''}
              aria-current={view === key ? 'page' : undefined}
            >
              <Icon size={19} />
              {t(key)}
            </Link>
          ))}
        </nav>
        <div className="sidebar-account">
          <div>
            <Avatar profile={session.user.profile} />
            <span>
              <strong>{session.user.full_name}</strong>
              <small>{t(session.user.role)}</small>
            </span>
          </div>
          <button onClick={signOut}>
            <LogOut size={18} />
            {t('logout')}
          </button>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="workspace-top">
          <button
            className="mobile-toggle"
            onClick={() => setMobile(!mobile)}
            aria-label={t('dashboard')}
            aria-expanded={mobile}
          >
            {mobile ? <X /> : <Menu />}
          </button>
          <Link className="text-link" href="/">
            Taskora / {t('home')}
          </Link>
          <div className="actions">
            <Link
              className="text-link"
              href={
                session.user.role === 'client' ? '/freelancers' : '/projects'
              }
            >
              {t(session.user.role === 'client' ? 'freelancers' : 'orders')}
            </Link>
            <Link href="/dashboard?view=messages" aria-label={t('messages')}>
              <MessageSquare size={19} />
            </Link>
            <Link
              href="/dashboard?view=notifications"
              aria-label={t('notifications')}
            >
              <Bell size={19} />
            </Link>
            <LanguageSelect />
          </div>
        </header>
        <main className="workspace-main">
          <Notice error>{error}</Notice>
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
                <h1>
                  {t(session.user.role === 'client' ? 'myOrders' : 'orders')}
                </h1>
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
            <>
              <ProfileSummary profile={session.user.profile} />
              <Stats />
              <div className="actions">
                <Link className="t-button" href="/dashboard?view=settings">
                  {t('editProfile')}
                </Link>
                <Link
                  className="t-button secondary"
                  href="/dashboard?view=contracts"
                >
                  {t('contracts')}
                </Link>
              </div>
            </>
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
                      session.user.role === 'client'
                        ? '/projects/new'
                        : '/projects'
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
              <ContractList compact />
              <p className="muted">{t('archiveHint')}</p>
            </>
          )}
        </main>
      </div>
    </div>
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
