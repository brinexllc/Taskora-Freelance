'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useApp } from '@/components/app-providers';
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
        <h1>{t('orders')}</h1>
        {session?.user?.role === 'client' && (
          <Link href="/projects/new" className="t-button">
            {t('createOrder')}
          </Link>
        )}
      </div>
      <OrdersList />
    </PageShell>
  );
}
export function OrdersList({ mine = false }) {
  const { t, session } = useApp();
  const [search, setSearch] = useState(''),
    [query, setQuery] = useState(''),
    [category, setCategory] = useState(''),
    [sort, setSort] = useState('-created_at'),
    [page, setPage] = useState(1);
  const remote = useRemote('projects', {
    token: session?.token,
    query: {
      mine: mine ? 1 : undefined,
      search: query,
      category,
      ordering: sort,
      page,
    },
  });
  return (
    <>
      <form
        className="filters-row"
        onSubmit={(event) => {
          event.preventDefault();
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
            <button className="t-button" type="submit">
              {t('search')}
            </button>
          </div>
        </Field>
        <Field label={t('category')}>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(1);
            }}
          >
            <option value="">{t('all')}</option>
            {['development', 'design', 'marketing', 'writing', 'other'].map(
              (key) => (
                <option key={key} value={key}>
                  {t(key)}
                </option>
              ),
            )}
          </select>
        </Field>
        <Field label={t('sort')}>
          <select
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
        </Field>
      </form>
      <RemoteState remote={remote}>
        <p className="result-count">
          {t('resultCount')}: {remote.data?.count}
        </p>
        {remote.data?.results.length ? (
          remote.data.results.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))
        ) : (
          <Empty text={t('noOrders')} />
        )}
        <Pager data={remote.data} page={page} onChange={setPage} />
      </RemoteState>
    </>
  );
}
