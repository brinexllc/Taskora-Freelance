'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import {
  Avatar,
  Empty,
  Field,
  PageShell,
  Pager,
  RemoteState,
  useRemote,
} from '@/components/taskora-ui';
import { money } from '@/lib/i18n';
export default function FreelancersPage() {
  const { t, language } = useApp();
  const [search, setSearch] = useState(''),
    [query, setQuery] = useState(''),
    [page, setPage] = useState(1);
  const remote = useRemote('profiles', { query: { search: query, page } });
  return (
    <PageShell>
      <h1>{t('freelancers')}</h1>
      <form
        className="filters-row"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search);
          setPage(1);
        }}
      >
        <Field label={t('search')}>
          <div className="actions">
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                if (!e.target.value) {
                  setQuery('');
                  setPage(1);
                }
              }}
            />
            <button className="t-button">{t('search')}</button>
          </div>
        </Field>
      </form>
      <RemoteState remote={remote}>
        {remote.data?.results.length ? (
          <div className="t-grid">
            {remote.data.results.map((profile) => (
              <article className="t-card person-card" key={profile.id}>
                <Avatar profile={profile} />
                <h3>{profile.full_name}</h3>
                <p className="muted">@{profile.username}</p>
                <div className="skill-tags">
                  {profile.skills.map((skill) => (
                    <span key={skill}>{skill}</span>
                  ))}
                </div>
                <p>
                  {money(profile.rate, language)} / {t(profile.rate_unit)}
                </p>
                <p className="muted">
                  {t('completedOrders')}: {profile.completed_projects}
                </p>
                <Link className="text-link" href={`/freelancers/${profile.id}`}>
                  {t('publicProfile')} →
                </Link>
              </article>
            ))}
          </div>
        ) : (
          <Empty text={t('noFreelancers')} />
        )}
        <Pager data={remote.data} page={page} onChange={setPage} />
      </RemoteState>
    </PageShell>
  );
}
