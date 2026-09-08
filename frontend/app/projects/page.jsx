'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Search, SlidersHorizontal } from 'lucide-react';
import { useApp } from '@/components/app-providers';
import { SkillPicker } from '@/components/project-editor';
import {
  Empty,
  Field,
  PageShell,
  Pager,
  ProjectCard,
  RemoteState,
  useRemote,
} from '@/components/taskora-ui';
export default function ProjectsPage() {
  const { t, session } = useApp();
  return (
    <PageShell>
      <div className="page-heading">
        <div>
          <span className="eyebrow">TASKORA</span>
          <h1>{t('orders')}</h1>
        </div>
        {session?.user?.role === 'client' && (
          <Link href="/projects/new" className="t-button">
            + {t('createOrder')}
          </Link>
        )}
      </div>
      <OrdersList />
    </PageShell>
  );
}
export function OrdersList({ mine = false }) {
  const { t, session } = useApp();
  const [filters, setFilters] = useState({
    search: '',
    category: '',
    skill_match: 'all',
    min_budget: '',
    max_budget: '',
    budget_type: '',
    deadline: '',
    status: '',
  });
  const [query, setQuery] = useState({});
  const [sort, setSort] = useState('-created_at');
  const [page, setPage] = useState(1);
  const [selectedSkills, setSelectedSkills] = useState([]);
  const directory = useRemote('catalog');
  useEffect(() => {
    void Promise.resolve().then(() => {
      const q = new URLSearchParams(window.location.search);
      const initial = {};
      if (q.get('category')) initial.category = q.get('category');
      if (q.get('status')) initial.status = q.get('status');
      if (q.get('search')) initial.search = q.get('search');
      if (Object.keys(initial).length) {
        setFilters((f) => ({ ...f, ...initial }));
        setQuery(initial);
      }
    });
  }, []);
  const remote = useRemote('projects', {
    token: session?.token,
    query: { ...query, mine: mine ? 1 : undefined, ordering: sort, page },
  });
  const change = (key) => (e) =>
    setFilters((f) => ({ ...f, [key]: e.target.value }));
  return (
    <div className="catalog-layout">
      <form
        className="catalog-filters t-card t-form"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery({ ...filters, skill_id: selectedSkills.map((s) => s.id) });
          setPage(1);
        }}
      >
        <h3>
          <SlidersHorizontal size={18} />
          {t('search')}
        </h3>
        <Field label={t('search')}>
          <input
            type="search"
            value={filters.search}
            onChange={change('search')}
          />
        </Field>
        <Field label={t('category')}>
          <select value={filters.category} onChange={change('category')}>
            <option value="">{t('all')}</option>
            {directory.data?.categories.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
        <SkillPicker
          key={filters.category}
          value={selectedSkills}
          onChange={setSelectedSkills}
          category={filters.category}
          hintKey={null}
        />
        <Field label={t('skillMatch')}>
          <select value={filters.skill_match} onChange={change('skill_match')}>
            <option value="all">{t('allSelectedSkills')}</option>
            <option value="any">{t('anySelectedSkill')}</option>
          </select>
        </Field>
        <Field label={t('budgetType')}>
          <select value={filters.budget_type} onChange={change('budget_type')}>
            <option value="">{t('all')}</option>
            {['fixed', 'hourly', 'daily'].map((k) => (
              <option key={k} value={k}>
                {t(k)}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-columns">
          <Field label={t('budgetMin')}>
            <input
              type="number"
              min="0"
              value={filters.min_budget}
              onChange={change('min_budget')}
            />
          </Field>
          <Field label={t('budgetMax')}>
            <input
              type="number"
              min="0"
              value={filters.max_budget}
              onChange={change('max_budget')}
            />
          </Field>
        </div>
        <Field label={t('deadline')}>
          <input
            type="date"
            value={filters.deadline}
            onChange={change('deadline')}
          />
        </Field>
        {mine && (
          <Field label={t('orders')}>
            <select value={filters.status} onChange={change('status')}>
              <option value="">{t('all')}</option>
              {[
                'draft',
                'published',
                'contracting',
                'in_progress',
                'review',
                'completed',
                'cancelled',
                'disputed',
              ].map((k) => (
                <option key={k} value={k}>
                  {t(k === 'review' ? 'inReview' : k)}
                </option>
              ))}
            </select>
          </Field>
        )}
        <button className="t-button">
          <Search size={17} />
          {t('search')}
        </button>
        <button
          type="button"
          className="text-link"
          onClick={() => {
            setFilters({
              search: '',
              category: '',
              skill_match: 'all',
              min_budget: '',
              max_budget: '',
              budget_type: '',
              deadline: '',
              status: '',
            });
            setQuery({});
            setSelectedSkills([]);
            setPage(1);
          }}
        >
          {t('all')}
        </button>
      </form>
      <section>
        <div className="row-between catalog-results-heading">
          <span>
            {t('resultCount')}: {remote.data?.count ?? '—'}
          </span>
          <select
            aria-label={t('sort')}
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setPage(1);
            }}
          >
            <option value="-created_at">{t('newest')}</option>
            <option value="-budget_max">{t('priceHigh')}</option>
            <option value="budget_min">{t('priceLow')}</option>
          </select>
        </div>
        <RemoteState remote={remote}>
          {remote.data?.results.length ? (
            remote.data.results.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))
          ) : (
            <Empty text={t('noOrders')} />
          )}
          <Pager data={remote.data} page={page} onChange={setPage} />
        </RemoteState>
      </section>
    </div>
  );
}
