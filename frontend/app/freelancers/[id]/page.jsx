'use client';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useApp } from '@/components/app-providers';
import {
  PageShell,
  ProfileSummary,
  RemoteState,
  useRemote,
} from '@/components/taskora-ui';
export default function FreelancerPage() {
  const { id } = useParams();
  const { t } = useApp();
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
