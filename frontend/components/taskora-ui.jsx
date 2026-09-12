'use client';
import Link from 'next/link';
import Image from 'next/image';
import {
  ArrowRight,
  ArrowLeft,
  FileText,
  Clock3,
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
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '@/components/app-providers';
import { logout, remoteRequest, apiErrorMessage } from '@/lib/api';
import { usePathname, useSearchParams } from 'next/navigation';
import { date, languages, money } from '@/lib/i18n';

export function useRemote(path, { token, query } = {}) {
  const { language, t } = useApp();
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
        setData(null);
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
          if (!controller.signal.aborted) setError(apiErrorMessage(err, t));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    });
    return () => controller.abort();
  }, [path, token, encoded, version, t]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, loading, reload };
}
export function Logo({ stacked = false, symbol = false }) {
  return (
    <Link
      href="/"
      className={`t-logo${stacked ? ' t-logo-stacked' : ''}${symbol ? ' t-logo-symbol' : ''}`}
      aria-label="Taskora"
    >
      {stacked ? (
        <span className="brand-lockup" aria-hidden="true">
          <Image
            unoptimized
            className="brand-color"
            src="/brand/taskora-color.png"
            alt=""
            width={4096}
            height={2320}
          />
          <Image
            unoptimized
            className="brand-white"
            src="/brand/taskora-white.png"
            alt=""
            width={4096}
            height={2320}
          />
        </span>
      ) : (
        <>
          <span className="brand-symbol" aria-hidden="true" />
          {!symbol && <strong>Taskora</strong>}
        </>
      )}
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
export function PageShell({
  children,
  publicView = false,
  mobileTitle,
  mobileStatus,
  backHref,
}) {
  const { session, t } = useApp();
  if (session?.user?.role && !publicView)
    return (
      <WorkspaceFrame
        mobileTitle={mobileTitle}
        mobileStatus={mobileStatus}
        backHref={backHref}
      >
        {children}
      </WorkspaceFrame>
    );
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
export function WorkspaceFrame({
  children,
  activeView,
  mobileTitle,
  mobileStatus,
  backHref,
}) {
  const { t, session, clearSession, theme, setTheme } = useApp();
  const pathname = usePathname();
  const search = useSearchParams();
  const [error, setError] = useState('');
  const stats = useRemote(session?.authenticated ? 'dashboard' : null, {
    token: session?.authenticated,
  });
  const view =
    activeView ||
    (pathname === '/dashboard'
      ? search.get('view') || 'home'
      : pathname.startsWith('/freelancers/')
        ? 'profile'
        : 'orders');
  const orderView = ['orders', 'contracts', 'proposals'].includes(view);
  const selected = orderView ? 'orders' : view;
  const nav = [
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
      await logout(session.authenticated);
      clearSession();
      window.location.assign('/');
    } catch (err) {
      setError(apiErrorMessage(err, t));
    }
  }
  return (
    <div className="taskora-app workspace figma-workspace">
      <aside className="workspace-sidebar">
        <div className="workspace-wordmark">
          <Logo />
        </div>
        <nav aria-label={t('dashboard')}>
          {nav.map(([Icon, key]) => (
            <Link
              href={`/dashboard?view=${String(key)}`}
              key={key}
              className={selected === key ? 'active' : ''}
              aria-current={selected === key ? 'page' : undefined}
            >
              <Icon size={20} /> <span>{t(key)}</span>
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
      </aside>
      <div className="workspace-body">
        <header className="workspace-mobile-header">
          {mobileTitle || view === 'profile' ? (
            <div className="mobile-page-title">
              <Link href={backHref || '/dashboard'} aria-label={t('back')}>
                <ArrowLeft size={22} />
              </Link>
              <strong>{mobileTitle || t('profile')}</strong>
            </div>
          ) : (
            <Logo symbol />
          )}
          {mobileStatus ? (
            <Status value={mobileStatus} />
          ) : (
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
          )}
        </header>
        <main className={`workspace-main workspace-view-${view}`}>
          <Notice error>{error}</Notice>
          <RemoteFeedback remote={stats} />
          {children}
        </main>
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
export function RemoteFeedback({ remote, showLoading = true }) {
  const { t } = useApp();
  if (remote.loading && showLoading)
    return <output className="empty-state">{t('loading')}</output>;
  if (!remote.error) return null;
  return <Notice error>{remote.error} <button className="text-link" type="button" onClick={remote.reload}>{t('retry')}</button></Notice>;
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
export function ProjectProgress({ status }) {
  const { t } = useApp();
  const stages = ['contracting', 'in_progress', 'review', 'completed'];
  const index = stages.indexOf(
    status === 'active'
      ? 'in_progress'
      : status === 'submitted'
        ? 'review'
        : status,
  );
  if (index < 0) return null;
  return (
    <div className="project-progress">
      <div>
        <span>{t('projectStages')}</span>
        <Status value={status} />
      </div>
      <ol aria-label={t('projectStages')}>
        {stages.map((stage, i) => (
          <li
            key={stage}
            className={i <= index ? 'done' : ''}
            title={t(stage)}
            aria-current={i === index ? 'step' : undefined}
          >
            <span className="sr-only">{t(stage)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
export function Avatar({ profile, large = false }) {
  const name = profile?.full_name || '';
  return profile?.avatar ? (
    <Image
      width={large ? 94 : 48}
      height={large ? 94 : 48}
      unoptimized
      className={`t-avatar avatar ${large ? 'large avatar-large' : ''}`}
      src={profile.avatar}
      alt={name}
    />
  ) : (
    <span
      className={`t-avatar avatar ${large ? 'large avatar-large' : ''}`}
      aria-label={name}
    >
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
            <Clock3 size={14} />
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
            {money(project.budget_min, language)}
            {project.budget_min !== project.budget_max &&
              ` – ${money(project.budget_max, language)}`}
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
