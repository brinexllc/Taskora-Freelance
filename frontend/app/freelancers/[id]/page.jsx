'use client';
import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useApp } from '@/components/app-providers';
import {
  PageShell,
  Pager,
  Empty,
  ProfileSummary,
  RemoteState,
  useRemote,
} from '@/components/taskora-ui';
export default function FreelancerPage() {
  const { id } = useParams();
  const { t } = useApp();
  const [page, setPage] = useState(1);
  const reviews = useRemote(id ? `profiles/${id}/reviews` : null, {
    query: { page },
  });
  const remote = useRemote(id ? `profiles/${id}` : null);
  return (
    <PageShell>
      <Link className="back-link" href="/freelancers">
        ← {t('freelancers')}
      </Link>
      <RemoteState remote={remote}>
        {remote.data && (
          <>
            <ProfileSummary profile={remote.data} />
            <section className="t-card">
              <h2>{t('professionalExperience')}</h2>
              <p className="preserve-lines">
                {remote.data.professional_experience || '—'}
              </p>
              <strong className="rating">
                ★ {remote.data.rating?.toFixed(1) || '—'} ·{' '}
                {remote.data.review_count} {t('reviews')}
              </strong>
            </section>
            <section className="t-card">
              <h2>{t('reviews')}</h2>
              <RemoteState remote={reviews}>
                {reviews.data?.results.length ? (
                  reviews.data.results.map((r) => (
                    <article key={r.id} className="review-item">
                      <strong>
                        {r.author_name} · {'★'.repeat(r.rating)}
                      </strong>
                      <p>{r.text}</p>
                    </article>
                  ))
                ) : (
                  <Empty text={t('empty')} />
                )}
                <Pager data={reviews.data} page={page} onChange={setPage} />
              </RemoteState>
            </section>
            <div className="t-stat">
              <span>{t('completedOrders')}</span>
              <strong>{remote.data.completed_projects}</strong>
            </div>
          </>
        )}
      </RemoteState>
    </PageShell>
  );
}
