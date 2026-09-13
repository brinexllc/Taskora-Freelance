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
  const { t, session, theme, language } = useApp();
  const content = useRemote('legal/current', { query: { lang: language } });
  const copy = (key) =>
    content.data?.homepage?.[key] ?? (content.loading ? '…' : '—');
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
      {content.data?.maintenance && (
        <output className="startup-shell">
          <p>
            {{
              ru: 'Плановое обслуживание. Новые операции временно приостановлены.',
              en: 'Scheduled maintenance. New operations are temporarily paused.',
              uz: 'Rejali texnik xizmat. Yangi amallar vaqtincha to‘xtatilgan.',
              'uz-cyrl':
                'Режали техник хизмат. Янги амаллар вақтинча тўхтатилган.',
            }[language] || 'Плановое обслуживание.'}
          </p>
        </output>
      )}
      <main>
        <section className="startup-hero">
          <div className="startup-shell">
            <h1>
              <span>{copy('heroA')}</span>
              <span>{copy('heroB')}</span>
              <em>{copy('heroC')}</em>
            </h1>
            <p>{copy('designHeroText')}</p>
            <RemoteFeedback remote={content} />
            <div className="startup-hero-actions">
              <Link href={start}>
                {t(session?.user ? 'dashboard' : 'register')}
                <ArrowRight />
              </Link>
              <a href="#about">
                {copy('aboutPlatform')}
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
          <h2>{copy('trustText')}</h2>
        </section>
        <section className="startup-security">
          <div className="startup-shell">
            <div className="startup-section-title">
              <h2>{copy('designSecureTitle')}</h2>
              <p>{copy('designSecureText')}</p>
            </div>
            <div className="startup-feature-grid">
              {[
                [LockKeyhole, 'securePayment', 'designEscrowText'],
                [Lightbulb, 'designMatching', 'designMatchingText'],
                [ShieldCheck, 'oneidFeature', 'oneidFeatureText'],
              ].map(([Icon, title, bodyKey]) => (
                <article key={title}>
                  <span>
                    <Icon />
                  </span>
                  <h3>{copy(title)}</h3>
                  <p>{copy(bodyKey)}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="startup-steps" id="how-it-works">
          <div className="startup-shell">
            <div className="startup-section-title">
              <h2>{copy('designSteps')}</h2>
              <p>{copy('designStepsText')}</p>
            </div>
            <div className="startup-step-grid">
              {[1, 2, 3].map((n) => (
                <article key={n}>
                  <b>0{n}</b>
                  <h3>{copy(`designStep${n}`)}</h3>
                  <p>{copy(`designStep${n}Text`)}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="startup-freelancers" id="freelancers">
          <div className="startup-shell">
            <span>{copy('designTopFreelancers')}</span>
            <div className="page-heading">
              <h2>{copy('specialists')}</h2>
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
            <h2>{copy('today')}</h2>
            <p>{copy('designCtaText')}</p>
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
        {!!content.data?.faq?.length && (
          <section className="startup-security" aria-label="FAQ">
            <div className="startup-shell">
              <h2>FAQ</h2>
              {content.data.faq.map((item, index) => (
                <details key={index} className="t-card">
                  <summary>{item.question}</summary>
                  <p>{item.answer}</p>
                </details>
              ))}
            </div>
          </section>
        )}
      </main>
      <footer className="startup-footer">
        <div className="startup-shell startup-footer-content">
          <div>
            <Logo symbol />
            <p>{copy('trustText')}</p>
          </div>
          <nav aria-label={t('footerPlatform')}>
            <a href="#about">{copy('footerPlatform')}</a>
            <Link href="/terms">{copy('designCompany')}</Link>
            <a href={content.data?.support?.url || '/terms#support'}>
              {copy('designSupport')}
            </a>
          </nav>
        </div>
        <div className="startup-shell startup-copy">
          <span>
            © {new Date().getFullYear()} Taskora. {copy('designMadeIn')}
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
