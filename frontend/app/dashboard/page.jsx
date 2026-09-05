'use client';
import Link from 'next/link';
import {
  BriefcaseBusiness,
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
  RemoteState,
  Status,
  useRemote,
} from '@/components/taskora-ui';
import { WalletView } from '@/components/wallet-view';
import { SettingsView } from '@/components/settings-view';
import { OrdersList } from '@/app/projects/page';
import { logout } from '@/lib/api';
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
            <LanguageSelect />
          </div>
        </header>
        <main className="workspace-main">
          <Notice error>{error}</Notice>
          {view === 'wallet' ? (
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
                  <span className="eyebrow">{t(session.user.role)}</span>
                  <h1>
                    {t('welcome')},{' '}
                    {session.user.first_name || session.user.full_name}
                  </h1>
                </div>
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
              <Stats />
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
  return (
    <RemoteState remote={remote}>
      <div className="t-stats">
        {[
          ['active_orders', 'activeOrders', 'orders'],
          ['active_contracts', 'activeContracts', 'contracts'],
          ['completed_orders', 'completedOrders', 'contracts'],
          ['completed_contracts', 'completedContracts', 'contracts'],
        ].map(([key, label, view]) => (
          <Link
            className="t-stat"
            key={key}
            href={`/dashboard?view=${view}${key.startsWith('completed') ? '&status=completed' : ''}`}
          >
            <span>{t(label)}</span>
            <strong>{remote.data?.[key]}</strong>
          </Link>
        ))}
      </div>
      <Link className="text-link" href="/dashboard?view=wallet">
        {t('balance')}: {money(remote.data?.balance, language)}
      </Link>
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
    <section className={compact ? 'section-heading' : ''}>
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
  const remote = useRemote('proposals', {
    token: session.token,
    query: { page, mine: 1 },
  });
  return (
    <>
      <h1>{t('myProposals')}</h1>
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
