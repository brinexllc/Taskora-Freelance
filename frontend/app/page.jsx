'use client';
import Link from 'next/link';
import { ArrowRight, FileCheck2, LockKeyhole, ShieldCheck } from 'lucide-react';
import { useApp } from '@/components/app-providers';
import { Header, Logo, useRemote } from '@/components/taskora-ui';
export default function LandingPage() {
  const { t, session } = useApp();
  const overview = useRemote('overview');
  const start = session?.user
    ? session.user.role
      ? '/dashboard'
      : '/role'
    : '/register';
  return (
    <div className="taskora-app">
      <Header />
      <main className="t-container">
        <section className="hero-section">
          <span className="eyebrow">TASKORA FREELANCE / MVP 1.0</span>
          <h1>{t('hero')}</h1>
          <p>{t('heroText')}</p>
          <div className="actions">
            <Link className="t-button" href={start}>
              {t('start')}
              <ArrowRight size={18} />
            </Link>
            <Link className="t-button secondary" href="/projects">
              {t('orders')}
            </Link>
          </div>
        </section>
        {overview.data && (
          <div className="landing-metrics">
            {[
              ['freelancers', 'freelancers'],
              ['active_projects', 'activeOrders'],
              ['completed_projects', 'completedOrders'],
            ].map(([key, label]) => (
              <div key={key}>
                <strong>{overview.data[key]}</strong>
                <span>{t(label)}</span>
              </div>
            ))}
          </div>
        )}
        <section className="landing-section">
          <h2>{t('secureTitle')}</h2>
          <div className="t-grid">
            {[
              [FileCheck2, 'contractFeature', 'contractFeatureText'],
              [LockKeyhole, 'previewFeature', 'previewFeatureText'],
              [ShieldCheck, 'oneidFeature', 'oneidFeatureText'],
            ].map(([Icon, title, text]) => (
              <article className="t-card" key={title}>
                <Icon className="feature-icon" />
                <h3>{t(title)}</h3>
                <p className="muted">{t(text)}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="landing-section">
          <h2>{t('how')}</h2>
          <div className="steps-list">
            {[1, 2, 3].map((n) => (
              <article key={n}>
                <strong>0{n}</strong>
                <h3>{t(`step${n}`)}</h3>
              </article>
            ))}
          </div>
        </section>
      </main>
      <footer className="landing-footer">
        <div className="t-container">
          <div className="row-between">
            <Logo />
            <div className="actions">
              <Link href="/projects">{t('orders')}</Link>
              <Link href="/freelancers">{t('freelancers')}</Link>
              <Link href={start}>{t('start')}</Link>
            </div>
          </div>
          <p>{t('footer')}</p>
          <p>© 2026 Taskora. {t('rights')}</p>
        </div>
      </footer>
    </div>
  );
}
