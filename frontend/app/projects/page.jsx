'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Search, SlidersHorizontal, FolderOpen } from 'lucide-react';
import { useApp } from '@/components/app-providers';
import { SkillPicker } from '@/components/project-editor';
import {
  Avatar,
  Field,
  PageShell,
  Pager,
  ProjectProgress,
  Status,
  RemoteState,
  RemoteFeedback,
  useRemote,
} from '@/components/taskora-ui';
import { date, money } from '@/lib/i18n';
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
export function OrdersList({ mine = false, assigned = false }) {
  const { t, language, session } = useApp();
  const [showFilters, setShowFilters] = useState(false);
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
    token: session?.authenticated,
    query: {
      ...query,
      mine: mine ? 1 : undefined,
      assigned: assigned ? 1 : undefined,
      ordering: sort,
      page,
    },
  });
  const change = (key) => (e) =>
    setFilters((f) => ({ ...f, [key]: e.target.value }));
  return (
    <div className="orders-catalog">
      <div className="orders-toolbar">
        {(mine || assigned) && (
          <nav className="order-status-tabs" aria-label={t('status')}>
            {[
              ['', 'all'],
              ['published', 'published'],
              ['in_progress', 'in_progress'],
              ['completed', 'completed'],
              ['cancelled', 'cancelled'],
            ].map(([value, label]) => (
              <button
                key={value}
                className={
                  query.status === value || (!query.status && !value)
                    ? 'active'
                    : ''
                }
                onClick={() => {
                  setFilters((f) => ({ ...f, status: value }));
                  setQuery((q) => ({ ...q, status: value }));
                  setPage(1);
                }}
              >
                {t(label)}
              </button>
            ))}
          </nav>
        )}
        <form
          className="orders-search"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery((q) => ({ ...q, search: filters.search }));
            setPage(1);
          }}
        >
          <Search size={16} />
          <input
            type="search"
            aria-label={t('search')}
            placeholder={t('search')}
            value={filters.search}
            onChange={change('search')}
          />
        </form>
        <button
          className="order-filter-button"
          onClick={() => setShowFilters(!showFilters)}
          aria-expanded={showFilters}
          aria-controls="order-advanced-filters"
        >
          <SlidersHorizontal size={16} />
          {t('filters')}
        </button>
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
      <form
        id="order-advanced-filters"
        hidden={!showFilters}
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
        <RemoteFeedback remote={directory} />
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
        <div className="row-between catalog-results-heading" hidden>
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
              <article className="managed-order" key={project.id}>
                <div className="row-between">
                  <h3>
                    <Link href={`/projects/${project.id}`}>
                      {project.title}
                    </Link>
                  </h3>
                  <Status value={project.status} />
                </div>
                <p className="managed-order-customer">
                  <Avatar
                    profile={{
                      full_name: project.client_name,
                      avatar: project.client_avatar,
                    }}
                  />
                  {project.client_name} ({t('client')})
                </p>
                <p className="managed-order-description">
                  {project.description}
                </p>
                <div className="skill-tags">
                  {project.skill_details?.map((skill) => (
                    <span key={skill.id}>{skill.label}</span>
                  ))}
                  {project.skills_unspecified && (
                    <span>{t('technologiesDiscussed')}</span>
                  )}
                </div>
                <ProjectProgress status={project.status} />
                <footer>
                  <div>
                    <small>{t('budget')}</small>
                    <strong>
                      {money(project.budget_min, language)}
                      {project.budget_min !== project.budget_max &&
                        ` – ${money(project.budget_max, language)}`}
                    </strong>
                  </div>
                  <div>
                    <small>{t('deadline')}</small>
                    <strong>{date(project.deadline, language)}</strong>
                  </div>
                  <Link
                    className="t-button secondary"
                    href={`/projects/${project.id}`}
                  >
                    {t('details')}
                  </Link>
                </footer>
              </article>
            ))
          ) : (
            <div className="orders-empty">
              <span className="orders-empty-icon">
                <FolderOpen size={44} />
              </span>
              <h2>{t('noOrders')}</h2>
              <p>
                {t(
                  mine
                    ? 'emptyOrdersHint'
                    : assigned
                      ? 'emptyAssignedHint'
                      : 'emptySearchHint',
                )}
              </p>
              {assigned && (
                <Link href="/projects" className="t-button">
                  {t('findWork')}
                </Link>
              )}
              {mine && (
                <Link href="/projects/new" className="t-button">
                  + {t('createOrder')}
                </Link>
              )}
            </div>
          )}
          <Pager data={remote.data} page={page} onChange={setPage} />
        </RemoteState>
      </section>
    </div>
  );
}
