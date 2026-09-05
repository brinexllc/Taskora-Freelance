'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { Field, Notice, PageShell } from '@/components/taskora-ui';
import { createProject } from '@/lib/api';
export default function NewProjectPage() {
  const { t, session, ready } = useApp();
  const [form, setForm] = useState({
    title: '',
    description: '',
    category: 'development',
    budget_min: '',
    budget_max: '',
    skills: '',
    client_company: '',
    deadline: '',
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const change = (key) => (e) =>
    setForm((current) => ({ ...current, [key]: e.target.value }));
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const project = await createProject(
        {
          ...form,
          deadline: form.deadline || null,
          skills: form.skills
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
        },
        session.token,
      );
      window.location.assign(`/projects/${project.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  if (!ready || !session?.user)
    return (
      <PageShell>
        <p>{t('loading')}</p>
      </PageShell>
    );
  if (session.user.role !== 'client')
    return (
      <PageShell>
        <Notice>{t('clientOnly')}</Notice>
        <Link href="/dashboard?view=settings" className="t-button">
          {t('goSettings')}
        </Link>
      </PageShell>
    );
  return (
    <PageShell>
      <Link className="back-link" href="/dashboard?view=orders">
        ← {t('myOrders')}
      </Link>
      <section className="t-card">
        <h1>{t('createOrder')}</h1>
        <form className="t-form" onSubmit={submit}>
          <Field label={t('title')}>
            <input
              value={form.title}
              onChange={change('title')}
              maxLength={180}
              required
            />
          </Field>
          <Field label={t('description')}>
            <textarea
              value={form.description}
              onChange={change('description')}
              required
            />
          </Field>
          <div className="form-columns">
            <Field label={t('category')}>
              <select value={form.category} onChange={change('category')}>
                {['development', 'design', 'marketing', 'writing', 'other'].map(
                  (key) => (
                    <option key={key} value={key}>
                      {t(key)}
                    </option>
                  ),
                )}
              </select>
            </Field>
            <Field label={t('skills')} hint={t('skillsHint')}>
              <input value={form.skills} onChange={change('skills')} />
            </Field>
            <Field label={t('budgetMin')}>
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.budget_min}
                onChange={change('budget_min')}
                required
              />
            </Field>
            <Field label={t('budgetMax')}>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={form.budget_max}
                onChange={change('budget_max')}
                required
              />
            </Field>
            <Field label={t('deadline')}>
              <input
                type="date"
                value={form.deadline}
                onChange={change('deadline')}
              />
            </Field>
            <Field label={t('company')}>
              <input
                value={form.client_company}
                maxLength={120}
                onChange={change('client_company')}
              />
            </Field>
          </div>
          <Notice error>{error}</Notice>
          <button className="t-button" disabled={busy}>
            {busy ? t('loading') : t('publish')}
          </button>
        </form>
      </section>
    </PageShell>
  );
}
