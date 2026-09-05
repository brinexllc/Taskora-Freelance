'use client';
import Link from 'next/link';
import {
  ArrowRight,
  FileCheck2,
  LockKeyhole,
  ShieldCheck,
  Rocket,
  Code2,
  Palette,
  Megaphone,
  PenLine,
  Boxes,
} from 'lucide-react';
import { useApp } from '@/components/app-providers';
import {
  Avatar,
  Empty,
  Header,
  LanguageSelect,
  Logo,
  ProjectCard,
  RemoteState,
  useRemote,
} from '@/components/taskora-ui';
import { money } from '@/lib/i18n';
export default function LandingPage() {
  const { t, session, theme, language } = useApp();
  const overview = useRemote('overview');
  const people = useRemote('profiles', { query: { page_size: 8 } });
  const projects = useRemote('projects', { query: { page_size: 3 } });
  const directory = useRemote('directory');
  const start = session?.user
    ? session.user.role
      ? '/dashboard'
      : '/role'
    : '/register';
  const icons = {
    development: Code2,
    design: Palette,
    marketing: Megaphone,
    writing: PenLine,
    other: Boxes,
  };
  return (
    <div
      className={`taskora-app startup-page ${theme === 'dark' ? 'startup-dark' : ''}`}
    >
      <Header landing />
      <main>
        <section className="startup-hero">
          <div className="startup-shell">
            <h1>
              <span>{t('heroA')}</span>
              <span>{t('heroB')}</span>
              <em>{t('heroC')}</em>
            </h1>
            <p>{t('heroText')}</p>
            <div className="startup-hero-actions">
              <Link href={start}>
                {t(session?.user ? 'dashboard' : 'register')}
                <ArrowRight />
              </Link>
              <a href="#about">
                {t('aboutPlatform')}
                <ArrowRight />
              </a>
            </div>
            <div className="startup-stats">
              {[
                ['freelancers', 'freelancers'],
                ['active_projects', 'activeOrders'],
                ['completed_projects', 'completedOrders'],
              ].map(([key, label]) => (
                <span key={key}>
                  <b>{overview.data?.[key] ?? '—'}</b> {t(label)}
                </span>
              ))}
            </div>
          </div>
        </section>
        <section className="startup-trust" id="about">
          <ShieldCheck />
          <h2>{t('trustText')}</h2>
        </section>
        <section className="startup-security">
          <div className="startup-shell">
            <div className="startup-section-title">
              <h2>{t('secureTitle')}</h2>
              <p>{t('escrowHint')}</p>
            </div>
            <div className="startup-feature-grid">
              {[
                [LockKeyhole, 'securePayment', 'escrowHint'],
                [FileCheck2, 'contractFeature', 'contractFeatureText'],
                [ShieldCheck, 'oneidFeature', 'oneidFeatureText'],
              ].map(([Icon, title, copy]) => (
                <article key={title}>
                  <span>
                    <Icon />
                  </span>
                  <h3>{t(title)}</h3>
                  <p>{t(copy)}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="startup-steps">
          <div className="startup-shell">
            <div className="startup-section-title">
              <h2>{t('how')}</h2>
            </div>
            <div className="startup-step-grid">
              {[1, 2, 3].map((n) => (
                <article key={n}>
                  <b>0{n}</b>
                  <h3>{t(`step${n}`)}</h3>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="startup-catalog">
          <div className="startup-shell">
            <div className="page-heading">
              <h2>{t('categories')}</h2>
              <Link className="text-link" href="/projects">
                {t('explore')} →
              </Link>
            </div>
            <RemoteState remote={directory}>
              <div className="category-cards">
                {directory.data?.categories.map((c) => {
                  const Icon = icons[c.slug] || Boxes;
                  return (
                    <Link key={c.slug} href={`/projects?category=${c.slug}`}>
                      <Icon />
                      <strong>
                        {t(c.slug) === c.slug ? c.name : t(c.slug)}
                      </strong>
                      <ArrowRight size={18} />
                    </Link>
                  );
                })}
              </div>
            </RemoteState>
          </div>
        </section>
        <section className="startup-catalog">
          <div className="startup-shell">
            <div className="page-heading">
              <h2>{t('latestOrders')}</h2>
              <Link className="text-link" href="/projects">
                {t('explore')} →
              </Link>
            </div>
            <RemoteState remote={projects}>
              {projects.data?.results.length ? (
                <div className="t-grid">
                  {projects.data.results.map((project) => (
                    <ProjectCard key={project.id} project={project} />
                  ))}
                </div>
              ) : (
                <Empty text={t('noOrders')} />
              )}
            </RemoteState>
          </div>
        </section>
        <section className="startup-freelancers" id="freelancers">
          <div className="startup-shell">
            <span>TASKORA</span>
            <div className="page-heading">
              <h2>{t('specialists')}</h2>
              <Link className="text-link" href="/freelancers">
                {t('explore')} →
              </Link>
            </div>
            <RemoteState remote={people}>
              {people.data?.results.length ? (
                <div className="startup-people-grid">
                  {people.data.results.map((p) => (
                    <Link key={p.id} href={`/freelancers/${p.id}`}>
                      <Avatar profile={p} />
                      <h3>{p.full_name}</h3>
                      <p>
                        {p.skills.slice(0, 2).join(' · ') || t('freelancer')}
                      </p>
                      <div>
                        <b>★ {p.rating?.toFixed(1) || '—'}</b>
                        <b>
                          {money(p.rate, language)} / {t(p.rate_unit)}
                        </b>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <Empty text={t('noFreelancers')} />
              )}
            </RemoteState>
          </div>
        </section>
        <section className="startup-cta-section">
          <div className="startup-shell startup-cta">
            <Rocket />
            <h2>{t('today')}</h2>
            <p>{t('heroText')}</p>
            <div>
              <Link href={start}>
                {t('start')}
                <ArrowRight />
              </Link>
              <Link href="/projects">
                {t('orders')}
                <ArrowRight />
              </Link>
            </div>
          </div>
        </section>
      </main>
      <footer className="startup-footer">
        <div className="startup-shell">
          <div>
            <Logo />
            <p>{t('footer')}</p>
            <LanguageSelect />
          </div>
          <nav>
            <b>{t('footerPlatform')}</b>
            <a href="#about">{t('aboutPlatform')}</a>
            <Link href="/projects">{t('orders')}</Link>
            <Link href="/freelancers">{t('freelancers')}</Link>
          </nav>
          <nav>
            <b>{t('documents')}</b>
            <Link href="/terms">{t('termsLink')}</Link>
            <Link href="/privacy">{t('privacyLink')}</Link>
            <Link href={start}>{t('profile')}</Link>
          </nav>
        </div>
        <p className="startup-copy">© 2026 Taskora. {t('rights')}</p>
      </footer>
    </div>
  );
}
