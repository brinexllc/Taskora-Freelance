'use client';
import Link from 'next/link';
import { useApp } from '@/components/app-providers';
import { PageShell, Notice } from '@/components/taskora-ui';
import { ProjectEditor } from '@/components/project-editor';
export default function NewProjectPage() {
  const { t, session, ready } = useApp();
  return (
    <PageShell>
      <Link className="back-link" href="/dashboard?view=orders">
        ← {t('myOrders')}
      </Link>
      <section className="t-card">
        <h1>{t('createOrder')}</h1>
        {!ready || !session?.user ? (
          <p>{t('loading')}</p>
        ) : session.user.role === 'client' ? (
          <ProjectEditor />
        ) : (
          <>
            <Notice>{t('clientOnly')}</Notice>
            <Link href="/dashboard?view=settings" className="t-button">
              {t('goSettings')}
            </Link>
          </>
        )}
      </section>
    </PageShell>
  );
}
