'use client';
import Link from 'next/link';
import { ArrowRight, Globe, ShieldCheck } from 'lucide-react';
import { useApp } from '@/components/app-providers';
import { LanguageSelect, Logo, useRemote } from '@/components/taskora-ui';
export default function LandingPage() {
  const { t, session } = useApp();
  const overview = useRemote('overview');
  const start = session?.user
    ? session.user.role
      ? '/dashboard'
      : '/role'
    : '/register';
  return (
    <div className="taskora-app elite-landing">
      <header className="elite-landing-header">
        <Logo />
        <nav>
          <Link href="/" aria-current="page">
            {t('home')}
          </Link>
          <Link href="/freelancers">{t('freelancers')}</Link>
          <Link href="/terms#how-it-works">{t('how')}</Link>
          <Link href="/terms#fees">{t('platformFee')}</Link>
        </nav>
        <Link className="elite-login" href={session?.user ? start : '/login'}>
          {t(session?.user ? 'dashboard' : 'login')}
        </Link>
      </header>
      <main>
        <section className="elite-hero">
          <span className="elite-hero-label">
            <ShieldCheck size={12} />
            {t('eliteHeroBadge')}
          </span>
          <h1>
            <span>{t('heroA')}</span>
            <span>{t('heroB')}</span>
            <em>{t('heroC')}</em>
          </h1>
          <p>{t('eliteHeroText')}</p>
          <div className="elite-hero-actions">
            <Link href={start}>
              {t(session?.user ? 'dashboard' : 'register')}{' '}
              <ArrowRight size={16} />
            </Link>
            <Link href="/projects">{t('explorePlatform')}</Link>
          </div>
          <div className="elite-hero-stats">
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
        </section>
      </main>
      <footer className="elite-landing-footer">
        <div className="elite-footer-grid">
          <div>
            <Logo />
            <p>{t('footer')}</p>
          </div>
          <nav>
            <b>{t('footerPlatform')}</b>
            <Link href="/projects">{t('orders')}</Link>
            <Link href="/freelancers">{t('freelancers')}</Link>
          </nav>
          <nav>
            <b>{t('documents')}</b>
            <Link href="/terms">{t('termsLink')}</Link>
            <Link href="/privacy">{t('privacyLink')}</Link>
          </nav>
          <nav>
            <b>{t('account')}</b>
            <Link href={start}>{t('profile')}</Link>
            <Link href="/reset-password">{t('forgot')}</Link>
          </nav>
        </div>
        <div className="elite-footer-bottom">
          <span>
            © {new Date().getFullYear()} Taskora. {t('rights')}
          </span>
          <div>
            <Globe size={16} />
            <LanguageSelect />
          </div>
        </div>
      </footer>
    </div>
  );
}
