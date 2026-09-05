'use client';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiRequest } from '@/lib/api';
import { Field, Notice, RemoteState, useRemote } from '@/components/taskora-ui';

export function SkillPicker({ value, onChange }) {
  const { t } = useApp();
  const [search, setSearch] = useState('');
  const remote = useRemote('directory');
  return (
    <fieldset className="skill-picker">
      <legend>{t('chooseSkills')}</legend>
      <input
        type="search"
        aria-label={t('search')}
        placeholder={t('search')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <RemoteState remote={remote}>
        <div>
          {remote.data?.skills
            .filter((s) => s.toLowerCase().includes(search.toLowerCase()))
            .map((skill) => (
              <label
                className={value.includes(skill) ? 'selected' : ''}
                key={skill}
              >
                <input
                  type="checkbox"
                  checked={value.includes(skill)}
                  onChange={(e) =>
                    onChange(
                      e.target.checked
                        ? [...value, skill]
                        : value.filter((s) => s !== skill),
                    )
                  }
                />
                {skill}
              </label>
            ))}
        </div>
      </RemoteState>
    </fieldset>
  );
}

export function ProjectEditor({ project, onSaved }) {
  const { t, session } = useApp();
  const remote = useRemote('directory');
  const [form, setForm] = useState({
    title: project?.title || '',
    description: project?.description || '',
    category: project?.category || 'development',
    budget_type: project?.budget_type || 'fixed',
    budget_min: project?.budget_min || '',
    budget_max: project?.budget_max || '',
    skills: project?.skills || [],
    client_company: project?.client_company || '',
    deadline: project?.deadline || '',
  });
  const [files, setFiles] = useState([]);
  const [savedId, setSavedId] = useState(project?.id);
  const [uploaded, setUploaded] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const change = (key) => (e) => {
    const value = e.target.value;
    setForm((current) => ({ ...current, [key]: value }));
  };
  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    const publish = e.nativeEvent.submitter?.value === 'publish';
    try {
      const item = await apiRequest(
        savedId ? `projects/${savedId}` : 'projects',
        {
          method: savedId ? 'PATCH' : 'POST',
          token: session.token,
          body: form,
        },
      );
      setSavedId(item.id);
      for (let i = uploaded; i < files.length; i++) {
        const body = new FormData();
        body.append('file', files[i]);
        await apiRequest(`projects/${item.id}/attachments`, {
          method: 'POST',
          token: session.token,
          body,
        });
        setUploaded(i + 1);
      }
      if (publish && item.status === 'draft')
        await apiRequest(`projects/${item.id}/publish`, {
          method: 'POST',
          token: session.token,
        });
      if (onSaved) onSaved();
      else window.location.assign(`/projects/${item.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="t-form" onSubmit={save}>
      <Notice error>{error}</Notice>
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
          maxLength={20000}
        />
      </Field>
      <div className="form-columns">
        <Field label={t('category')}>
          <select value={form.category} onChange={change('category')}>
            {remote.data?.categories.map((c) => (
              <option value={c.slug} key={c.slug}>
                {t(c.slug) === c.slug ? c.name : t(c.slug)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('budgetType')}>
          <select value={form.budget_type} onChange={change('budget_type')}>
            {['fixed', 'hourly', 'daily'].map((type) => (
              <option key={type} value={type}>
                {t(type)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="form-columns">
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
            min={Math.max(0.01, Number(form.budget_min))}
            step="0.01"
            value={form.budget_max}
            onChange={change('budget_max')}
            required
          />
        </Field>
      </div>
      <SkillPicker
        value={form.skills}
        onChange={(skills) => setForm((f) => ({ ...f, skills }))}
      />
      <div className="form-columns">
        <Field label={t('deadline')}>
          <input
            type="date"
            value={form.deadline}
            onChange={change('deadline')}
            required
          />
        </Field>
        <Field label={t('company')}>
          <input
            maxLength={120}
            value={form.client_company}
            onChange={change('client_company')}
          />
        </Field>
      </div>
      {(!project || project.status === 'draft') && (
        <Field
          label={t('attachments')}
          hint="ZIP, PDF, PNG, JPG, WebP, DOCX, XLSX, PPTX, TXT, CSV, JSON, MD, FIG · 25 MB × 5"
        >
          <input
            type="file"
            multiple
            disabled={!!savedId && uploaded > 0}
            onChange={(e) => {
              setFiles(Array.from(e.target.files || []));
              setUploaded(0);
            }}
          />
        </Field>
      )}
      <div className="actions">
        <button
          className="t-button secondary"
          value="draft"
          disabled={busy || !form.skills.length || files.length > 5}
        >
          {t(project ? 'save' : 'saveDraft')}
        </button>
        {(!project || project.status === 'draft') && (
          <button
            className="t-button"
            value="publish"
            disabled={busy || !form.skills.length || files.length > 5}
          >
            {t('publish')}
          </button>
        )}
      </div>
    </form>
  );
}
