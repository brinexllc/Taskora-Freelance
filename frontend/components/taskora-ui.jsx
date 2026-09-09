'use client';
import Link from 'next/link';
import Image from 'next/image';
import {
  ArrowRight,
  FileText,
  Menu,
  Moon,
  Sun,
  X,
  Bell,
  MessageSquare,
  LayoutDashboard,
  BriefcaseBusiness,
  UserRound,
  Wallet,
  Settings,
  Plus,
  LogOut,
  Search,
  CircleHelp,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '@/components/app-providers';
import { logout, remoteRequest } from '@/lib/api';
import { usePathname, useSearchParams } from 'next/navigation';
import { date, languages, money } from '@/lib/i18n';

export function useRemote(path, { token, query } = {}) {
  const { language } = useApp();
  const [data, setData] = useState(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true),
    [version, setVersion] = useState(0);
  const encoded = JSON.stringify({ ...query, lang: language });
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      if (!path) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError('');
      return remoteRequest(path, {
        token,
        query: JSON.parse(encoded),
        signal: controller.signal,
      })
        .then((value) => {
          if (!controller.signal.aborted) setData(value);
        })
        .catch((err) => {
          if (!controller.signal.aborted) setError(err.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    });
    return () => controller.abort();
  }, [path, token, encoded, version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, loading, reload };
}
export function Logo({ stacked = false }) {
  return (
    <Link
      href="/"
      className={`t-logo${stacked ? ' t-logo-stacked' : ''}`}
      aria-label="Taskora"
    >
      <svg className="taskora-mark" viewBox="0 0 100 104" aria-hidden="true">
        <g fill="currentColor">
          <circle cx="50" cy="35" r="13" />
          <circle cx="20" cy="35" r="10.5" />
          <circle cx="80" cy="35" r="10.5" />
          <circle cx="50" cy="64" r="13" />
          <circle cx="50" cy="94" r="10.5" />
        </g>
        <g fill="#3faaa5">
          <circle cx="34" cy="15" r="6" />
          <circle cx="50" cy="8" r="3.5" />
          <circle cx="66" cy="15" r="6" />
          <circle cx="9" cy="58" r="6" />
          <circle cx="27" cy="64" r="6" />
          <circle cx="12" cy="75" r="3.5" />
          <circle cx="25" cy="87" r="6" />
          <circle cx="75" cy="87" r="6" />
          <circle cx="88" cy="75" r="3.5" />
          <circle cx="73" cy="64" r="6" />
          <circle cx="91" cy="58" r="6" />
        </g>
      </svg>
      <strong>Taskora</strong>
      {stacked && <small>Work with Confidence</small>}
    </Link>
  );
}
export function LanguageSelect() {
  const { language, setLanguage, t } = useApp();
  return (
    <select
      className="language-select"
      aria-label={t('language')}
      value={language}
      onChange={(e) => setLanguage(e.target.value)}
    >
      {languages.map(([key, label]) => (
        <option value={key} key={key}>
          {label}
        </option>
      ))}
    </select>
  );
}
export function Header({ landing = false }) {
  const { t, session, theme, setTheme } = useApp();
  const [open, setOpen] = useState(false);
  return (
    <header className="t-header">
      <div className="t-container t-header-inner">
        <Logo stacked={landing} />
        <button
          className="mobile-toggle"
          onClick={() => setOpen(!open)}
          aria-label={t(open ? 'close' : 'orders')}
          aria-expanded={open}
        >
          {open ? <X /> : <Menu />}
        </button>
        <nav className={open ? 'is-open' : ''}>
          <Link href="/projects">{t('orders')}</Link>
          <Link href="/freelancers">{t('freelancers')}</Link>
          {session?.user && (
            <>
              <Link href="/dashboard?view=messages" aria-label={t('messages')}>
                <MessageSquare size={19} />
              </Link>
              <Link
                href="/dashboard?view=notifications"
                aria-label={t('notifications')}
              >
                <Bell size={19} />
              </Link>
            </>
          )}
          <LanguageSelect />
          <button
            className="icon-button"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label={t(theme === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
          </button>
          <Link
            className="t-button"
            href={
              session?.user
                ? session.user.role
                  ? '/dashboard'
                  : '/role'
                : '/login'
            }
          >
            {t(session?.user ? 'profile' : 'login')}
            <ArrowRight size={16} />
          </Link>
        </nav>
      </div>
    </header>
  );
}
export function PageShell({ children, publicView = false }) {
  const { session, t } = useApp();
  if (session?.user?.role && !publicView)
    return <WorkspaceFrame>{children}</WorkspaceFrame>;
  return (
    <div className="taskora-app">
      <Header />
      <main
        className={`t-container page-content ${publicView ? 'public-profile-content' : ''}`}
      >
        {children}
      </main>
      {publicView && (
        <footer className="public-profile-footer">
          <Logo />
          <span>
            © {new Date().getFullYear()} Taskora. {t('rights')}
          </span>
          <nav>
            <Link href="/privacy">{t('privacyLink')}</Link>
            <Link href="/terms">{t('termsLink')}</Link>
            <Link href="/projects">{t('orders')}</Link>
          </nav>
        </footer>
      )}
    </div>
  );
}
export function WorkspaceFrame({ children, activeView }) {
  const { t, session, clearSession, theme, setTheme } = useApp();
  const pathname = usePathname();
  const search = useSearchParams();
  const [error, setError] = useState('');
  const stats = useRemote(session?.token ? 'dashboard' : null, {
    token: session?.token,
  });
  const view =
    activeView ||
    (pathname === '/dashboard'
      ? search.get('view') || 'home'
      : pathname.startsWith('/freelancers/')
        ? 'profile'
        : 'orders');
  const orderView = ['orders', 'contracts', 'proposals'].includes(view);
  const selected = orderView
    ? theme === 'dark' && session?.user?.role === 'client'
      ? 'home'
      : 'orders'
    : view;
  const nav =
    theme === 'dark' && session?.user?.role === 'client'
      ? [
          [BriefcaseBusiness, 'home'],
          [MessageSquare, 'messages'],
          [Wallet, 'wallet'],
          [Settings, 'settings'],
        ]
      : [
          [LayoutDashboard, 'home'],
          [UserRound, 'profile'],
          [BriefcaseBusiness, 'orders'],
          [MessageSquare, 'messages'],
          [Wallet, 'wallet'],
          [Settings, 'settings'],
        ];
  const createUrl =
    session?.user?.role === 'client' ? '/projects/new' : '/projects';
  async function signOut() {
    try {
      await logout(session.token);
      clearSession();
      window.location.assign('/');
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <div
      className={`taskora-app workspace figma-workspace ${theme === 'dark' ? 'elite-workspace' : ''}`}
    >
      <aside className="workspace-sidebar">
        <div className="workspace-wordmark">
          <Logo />
          <small>ELITE MARKETPLACE</small>
        </div>
        <nav aria-label={t('dashboard')}>
          {nav.map(([Icon, key]) => (
            <Link
              href={`/dashboard?view=${String(key)}`}
              key={key}
              className={selected === key ? 'active' : ''}
              aria-current={selected === key ? 'page' : undefined}
            >
              <Icon size={20} />{' '}
              <span>
                {t(
                  theme === 'dark' &&
                    session?.user?.role === 'client' &&
                    key === 'home'
                    ? 'orders'
                    : key,
                )}
              </span>
              {key === 'messages' && stats.data?.unread_messages > 0 && (
                <b className="nav-count">{stats.data.unread_messages}</b>
              )}
            </Link>
          ))}
        </nav>
        <details className="sidebar-account account-menu">
          <summary>
            <Avatar profile={session?.user?.profile || {}} />
            <span>
              <strong>{session?.user?.full_name}</strong>
              <small>{t(session?.user?.role || 'profile')}</small>
            </span>
          </summary>
          <div className="account-menu-content">
            <LanguageSelect />
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
              {t(theme === 'dark' ? 'light' : 'dark')}
            </button>
            <Link href="/dashboard?view=notifications">
              <Bell size={18} />
              {t('notifications')}
            </Link>
            <button onClick={signOut}>
              <LogOut size={18} />
              {t('logout')}
            </button>
          </div>
        </details>
        <Link className="t-button sidebar-create" href={createUrl}>
          {t(session?.user?.role === 'client' ? 'createOrder' : 'browseOrders')}
        </Link>
      </aside>
      <div className="workspace-body">
        <header className="elite-topbar">
          <form action="/projects">
            <Search size={17} />
            <input
              name="search"
              type="search"
              aria-label={t('search')}
              placeholder={t('searchProjects')}
            />
          </form>
          <div>
            <Link
              href="/dashboard?view=notifications"
              aria-label={t('notifications')}
            >
              <Bell size={19} />
            </Link>
            <Link href="/terms" aria-label={t('termsLink')}>
              <CircleHelp size={19} />
            </Link>
            <Link href="/dashboard?view=profile" aria-label={t('profile')}>
              <Avatar profile={session?.user?.profile || {}} />
            </Link>
          </div>
        </header>
        <header className="workspace-mobile-header">
          <Logo />
          <div className="actions">
            <Link
              href="/dashboard?view=notifications"
              aria-label={t('notifications')}
            >
              <Bell size={20} />
              {stats.data?.unread_notifications > 0 && (
                <span className="notification-dot" />
              )}
            </Link>
            <Link href="/dashboard?view=settings" aria-label={t('settings')}>
              <Avatar profile={session?.user?.profile || {}} />
            </Link>
          </div>
        </header>
        <main className={`workspace-main workspace-view-${view}`}>
          <Notice error>{error}</Notice>
          {children}
        </main>
        <footer className="elite-workspace-footer">
          <span>
            © {new Date().getFullYear()} TASKORA. {t('rights')}
          </span>
          <div>
            <Link href="/terms">{t('termsLink')}</Link>
            <Link href="/privacy">{t('privacyLink')}</Link>
          </div>
        </footer>
      </div>
      <nav className="workspace-bottom-nav" aria-label={t('dashboard')}>
        {[
          [LayoutDashboard, 'home'],
          [BriefcaseBusiness, 'orders'],
          [Plus, 'create'],
          [MessageSquare, 'messages'],
          [UserRound, 'profile'],
        ].map(([Icon, key]) => (
          <Link
            key={key}
            href={
              key === 'create' ? createUrl : `/dashboard?view=${String(key)}`
            }
            className={
              key === 'create'
                ? 'bottom-create'
                : selected === key
                  ? 'active'
                  : ''
            }
            aria-label={t(
              key === 'create'
                ? session?.user?.role === 'client'
                  ? 'createOrder'
                  : 'browseOrders'
                : key,
            )}
            aria-current={selected === key ? 'page' : undefined}
          >
            <Icon size={20} />
            {key !== 'create' && <span>{t(key)}</span>}
            {key === 'messages' && stats.data?.unread_messages > 0 && (
              <b>{stats.data.unread_messages}</b>
            )}
          </Link>
        ))}
      </nav>
    </div>
  );
}
export function Notice({ children, error = false }) {
  if (!children) return null;
  return error ? (
    <div className="notice notice-error" role="alert">
      {children}
    </div>
  ) : (
    <output className="notice">{children}</output>
  );
}
export function RemoteState({ remote, empty, children }) {
  const { t } = useApp();
  if (remote.loading)
    return <output className="empty-state">{t('loading')}</output>;
  if (remote.error)
    return (
      <Notice error>
        {remote.error}{' '}
        <button className="text-link" onClick={remote.reload}>
          {t('retry')}
        </button>
      </Notice>
    );
  if (!remote.data) return <Empty text={empty || t('empty')} />;
  return children;
}
export function Empty({ text }) {
  return (
    <div className="empty-state">
      <FileText size={30} />
      <p>{text}</p>
    </div>
  );
}
export function Status({ value, label }) {
  const { t } = useApp();
  return (
    <span className={`status status-${value}`}>
      {label || t(value === 'review' ? 'inReview' : value)}
    </span>
  );
}
export function Avatar({ profile, large = false }) {
  const name = profile?.full_name || '';
  return profile?.avatar ? (
    <Image
      width={large ? 94 : 48}
      height={large ? 94 : 48}
      unoptimized
      className={`t-avatar ${large ? 'large' : ''}`}
      src={profile.avatar}
      alt={name}
    />
  ) : (
    <span className={`t-avatar ${large ? 'large' : ''}`} aria-label={name}>
      {name
        .split(' ')
        .filter(Boolean)
        .map((p) => p[0])
        .slice(0, 2)
        .join('')
        .toUpperCase() || 'T'}
    </span>
  );
}
export function Field({ label, hint, children }) {
  return (
    <label className="t-field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Pager({ data, page, onChange }) {
  const { t } = useApp();
  if (!data || (!data.previous && !data.next)) return null;
  return (
    <nav className="pager" aria-label="Pagination">
      <button
        type="button"
        className="t-button secondary"
        disabled={!data.previous}
        onClick={() => onChange(page - 1)}
      >
        {t('previous')}
      </button>
      <span>{page}</span>
      <button
        className="t-button secondary"
        disabled={!data.next}
        type="button"
        onClick={() => onChange(page + 1)}
      >
        {t('next')}
      </button>
    </nav>
  );
}
export function ProjectCard({ project, compact = false }) {
  const { t, language } = useApp();
  return (
    <article
      className={`t-card project-row ${compact ? 'compact-project' : ''}`}
    >
      <div className="row-between">
        <span className="eyebrow">{project.category_label}</span>
        {compact && project.deadline ? (
          <span className="compact-deadline">
            {date(project.deadline, language)}
          </span>
        ) : (
          <Status value={project.status} />
        )}
      </div>
      <Link href={`/projects/${project.id}`}>
        <h3>{project.title}</h3>
      </Link>
      <p className="muted line-clamp">{project.description}</p>
      <div className="skill-tags">
        {project.skills_unspecified && (
          <span>{t('technologiesDiscussed')}</span>
        )}
        {project.skill_details?.map((skill) => (
          <span key={skill.id}>{skill.label}</span>
        ))}
      </div>
      <div className="project-row-footer">
        <div>
          {compact && <span className="budget-label">{t('budget')}</span>}
          <strong>
            {money(project.budget_min, language)} –{' '}
            {money(project.budget_max, language)}
          </strong>
          <small>
            {project.client_name} · {t('proposals')}: {project.proposal_count}
            {project.deadline
              ? ` · ${t('deadline')}: ${date(project.deadline, language)}`
              : ''}
          </small>
        </div>
        <Link className="text-link" href={`/projects/${project.id}`}>
          {t('details')} <ArrowRight size={16} />
        </Link>
      </div>
    </article>
  );
}
export function ProfileSummary({ profile }) {
  const { t, language } = useApp();
  return (
    <>
      <section className="t-card profile-top">
        <Avatar profile={profile} large />
        <div>
          <span className="eyebrow">{t(profile.role)}</span>
          <h1>{profile.full_name}</h1>
          <p className="muted">
            @{profile.username}
            {profile.age != null ? ` · ${profile.age} ${t('years')}` : ''}
          </p>
        </div>
      </section>
      <div className="two-columns">
        <section className="t-card">
          <h2>{t('about')}</h2>
          <p className="preserve-lines">{profile.about || t('noAbout')}</p>
          <dl className="detail-list">
            <div>
              <dt>{t('firstName')}</dt>
              <dd>{profile.first_name || '—'}</dd>
            </div>
            <div>
              <dt>{t('lastName')}</dt>
              <dd>{profile.last_name || '—'}</dd>
            </div>
            <div>
              <dt>{t('memberSince')}</dt>
              <dd>{date(profile.created_at, language)}</dd>
            </div>
            {profile.role === 'freelancer' && (
              <>
                <div>
                  <dt>{t('experience')}</dt>
                  <dd>
                    {profile.experience_days} {t('days')}
                  </dd>
                </div>
                <div>
                  <dt>{t('rate')}</dt>
                  <dd>
                    {money(profile.rate, language)} / {t(profile.rate_unit)}
                  </dd>
                </div>
              </>
            )}
          </dl>
        </section>
        {profile.role === 'freelancer' && (
          <section className="t-card">
            <h2>{t('skills')}</h2>
            <div className="skill-tags">
              {profile.skills?.length ? (
                profile.skill_details.map((skill) => (
                  <span key={skill.id}>{skill.label}</span>
                ))
              ) : (
                <span>{t('empty')}</span>
              )}
            </div>
            <h2>{t('verifiedSkills')}</h2>
            <div className="skill-tags verified">
              {profile.verified_skills?.length ? (
                profile.verified_skills.map((skill) => (
                  <span key={skill}>✓ {skill}</span>
                ))
              ) : (
                <p className="muted">{t('noVerified')}</p>
              )}
            </div>
          </section>
        )}
      </div>
    </>
  );
}
export async function readImage(file) {
  if (!file) return '';
  if (file.size > 2 * 1024 * 1024)
    throw new Error('PNG / JPEG / WebP: максимум 2 MB');
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type))
    throw new Error('PNG / JPEG / WebP');
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('File read failed'));
    reader.readAsDataURL(file);
  });
}
