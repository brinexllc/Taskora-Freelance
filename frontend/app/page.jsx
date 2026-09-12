'use client';
import Link from 'next/link';
import {
  ArrowRight,
  Lightbulb,
  LockKeyhole,
  ShieldCheck,
  CircleCheck,
} from 'lucide-react';
import { useApp } from '@/components/app-providers';
import {
  Avatar,
  Empty,
  Header,
  LanguageSelect,
  Logo,
  RemoteState,
  RemoteFeedback,
  useRemote,
} from '@/components/taskora-ui';
export default function LandingPage() {
  const { t, session, theme } = useApp();
  const overview = useRemote('overview');
  const people = useRemote('profiles', { query: { page_size: 8 } });
  const start = session?.user
    ? session.user.role
      ? '/dashboard'
      : '/role'
    : '/register';
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
            <p>{t('designHeroText')}</p>
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
            <RemoteFeedback remote={overview} />
          </div>
        </section>
        <section className="startup-trust" id="about">
          <CircleCheck />
          <h2>{t('trustText')}</h2>
        </section>
        <section className="startup-security">
          <div className="startup-shell">
            <div className="startup-section-title">
              <h2>{t('designSecureTitle')}</h2>
              <p>{t('designSecureText')}</p>
            </div>
            <div className="startup-feature-grid">
              {[
                [LockKeyhole, 'securePayment', 'designEscrowText'],
                [Lightbulb, 'designMatching', 'designMatchingText'],
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
        <section className="startup-steps" id="how-it-works">
          <div className="startup-shell">
            <div className="startup-section-title">
              <h2>{t('designSteps')}</h2>
              <p>{t('designStepsText')}</p>
            </div>
            <div className="startup-step-grid">
              {[1, 2, 3].map((n) => (
                <article key={n}>
                  <b>0{n}</b>
                  <h3>{t(`designStep${n}`)}</h3>
                  <p>{t(`designStep${n}Text`)}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="startup-freelancers" id="freelancers">
          <div className="startup-shell">
            <span>{t('designTopFreelancers')}</span>
            <div className="page-heading">
              <h2>{t('specialists')}</h2>
            </div>
            <RemoteState remote={people}>
              {people.data?.results.length ? (
                <div className="startup-people-grid">
                  {people.data.results.map((p) => (
                    <Link key={p.id} href={`/freelancers/${p.id}`}>
                      <span className="landing-person-avatar">
                        <Avatar profile={p} />
                        {p.available && (
                          <span
                            className="landing-available"
                            title={t('available')}
                          />
                        )}
                      </span>
                      <h3>{p.full_name}</h3>
                      <p>{p.professional_title || t('freelancer')}</p>
                      <div>
                        {p.skill_details?.slice(0, 2).map((skill) => (
                          <b key={skill.id}>{skill.label}</b>
                        ))}
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
            <h2>{t('today')}</h2>
            <p>{t('designCtaText')}</p>
            <div>
              <Link href={start}>
                {t(session?.user ? 'dashboard' : 'register')}
                <ArrowRight />
              </Link>
              <Link href={session?.user ? '/projects' : '/login'}>
                {t(session?.user ? 'orders' : 'login')}
              </Link>
            </div>
          </div>
        </section>
      </main>
      <footer className="startup-footer">
        <div className="startup-shell startup-footer-content">
          <div>
            <Logo symbol />
            <p>{t('trustText')}</p>
          </div>
          <nav aria-label={t('footerPlatform')}>
            <a href="#about">{t('footerPlatform')}</a>
            <Link href="/terms">{t('designCompany')}</Link>
            <Link href="/terms#support">{t('designSupport')}</Link>
          </nav>
        </div>
        <div className="startup-shell startup-copy">
          <span>
            © {new Date().getFullYear()} Taskora. {t('designMadeIn')}
          </span>
          <div>
            <LanguageSelect />
            <Link href="/privacy">{t('privacyLink')}</Link>
          </div>
        </div>
        <span className="footer-watermark" aria-hidden="true">
          Taskora
        </span>
      </footer>
    </div>
  );
}
