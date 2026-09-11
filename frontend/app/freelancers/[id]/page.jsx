'use client';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useApp } from '@/components/app-providers';
import { PageShell, RemoteState, useRemote } from '@/components/taskora-ui';
import { ProfileShowcase } from '@/components/profile-showcase';
export default function FreelancerPage() {
  const { id } = useParams();
  const { t, session } = useApp();
  const remote = useRemote(id ? `profiles/${id}` : null);
  return (
    <PageShell
      publicView={!session?.user?.role}
      mobileTitle={t('profile')}
      backHref="/freelancers"
    >
      <Link className="back-link" href="/freelancers">
        ← {t('freelancers')}
      </Link>
      <RemoteState remote={remote}>
        {remote.data && <ProfileShowcase profile={remote.data} />}
      </RemoteState>
    </PageShell>
  );
}
