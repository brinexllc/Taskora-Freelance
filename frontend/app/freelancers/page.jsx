'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { SkillPicker } from '@/components/project-editor';
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
  const [filters, setFilters] = useState({
    min_rate: '',
    max_rate: '',
    rating: '',
    available: '',
  });
  const [applied, setApplied] = useState({});
  const [selectedSkills, setSelectedSkills] = useState([]);
  const hasFilters = query.trim() || Object.values(applied).some((value) => Array.isArray(value) ? value.length > 0 : value !== '' && value != null);
  const remote = useRemote('profiles', {
    query: { search: query, page, ...applied },
  });
  return (
    <PageShell>
      <h1>{t('freelancers')}</h1>
      <form
        className="filters-row"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search);
          setApplied({ ...filters, skill_id: selectedSkills.map((s) => s.id) });
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
        <SkillPicker
          value={selectedSkills}
          onChange={setSelectedSkills}
          hintKey={null}
        />
        <Field label={t('rating')}>
          <select
            value={filters.rating}
            onChange={(e) =>
              setFilters((f) => ({ ...f, rating: e.target.value }))
            }
          >
            <option value="">{t('all')}</option>
            {[5, 4, 3, 2, 1].map((n) => (
              <option value={n} key={n}>
                {n} ★ +
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('budgetMin')}>
          <input
            type="number"
            min="0"
            value={filters.min_rate}
            onChange={(e) =>
              setFilters((f) => ({ ...f, min_rate: e.target.value }))
            }
          />
        </Field>
        <Field label={t('budgetMax')}>
          <input
            type="number"
            min="0"
            value={filters.max_rate}
            onChange={(e) =>
              setFilters((f) => ({ ...f, max_rate: e.target.value }))
            }
          />
        </Field>
        <label className="t-check">
          <input
            type="checkbox"
            checked={filters.available === 'true'}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                available: e.target.checked ? 'true' : '',
              }))
            }
          />
          {t('available')}
        </label>
      </form>
      <RemoteState remote={remote}>
        {remote.data?.results.length ? (
          <div className="t-grid">
            {remote.data.results.map((profile) => (
              <article className="t-card person-card" key={profile.id}>
                <Avatar profile={profile} />
                <h3>{profile.full_name}</h3>
                <p className="muted">@{profile.username}</p>
                <p className="rating">
                  ★ {profile.rating?.toFixed(1) || '—'} · {profile.review_count}{' '}
                  {t('reviews')}
                </p>
                <div className="skill-tags">
                  {profile.skill_details.map((skill) => (
                    <span key={skill.id}>{skill.label}</span>
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
          <Empty text={t(hasFilters ? 'noResults' : 'noFreelancers')} />
        )}
        <Pager data={remote.data} page={page} onChange={setPage} />
      </RemoteState>
    </PageShell>
  );
}
