'use client';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { AcceptanceFields } from '@/components/acceptance-terms';
import { apiRequest, apiErrorMessage } from '@/lib/api';
import {
  Field,
  Notice,
  Pager,
  RemoteState,
  useRemote,
} from '@/components/taskora-ui';

export function SkillPicker({
  value,
  onChange,
  category,
  hintKey = 'profileSkillHint',
  disabled = false,
}) {
  const { t, language } = useApp();
  const skillLabel = (skill) =>
    skill.labels?.[language] || skill.labels?.ru || skill.label || skill.name;
  const [search, setSearch] = useState('');
  const [all, setAll] = useState(false);
  const [page, setPage] = useState(1);
  const recommended = !!category && category !== 'other' && !all;
  const remote = useRemote('skills', {
    query: {
      search,
      category: recommended ? category : '',
      page,
      page_size: 20,
    },
  });
  const selected = new Set(value.map((s) => s.id));
  const choose = (skill) =>
    onChange(
      selected.has(skill.id)
        ? value.filter((s) => s.id !== skill.id)
        : [...value, skill],
    );
  return (
    <fieldset className="skill-picker" disabled={disabled}>
      <legend>{t('chooseSkills')}</legend>
      {hintKey && <p className="muted">{t(hintKey)}</p>}
      <p>
        {t('selectedSkills')}: {value.length} / 30
      </p>
      <div className="skill-tags selected-skill-tags">
        {value.map((skill) => (
          <button
            key={skill.id}
            type="button"
            className="selected-skill"
            onClick={() => choose(skill)}
            aria-label={`${t('removeSkill')}: ${skillLabel(skill)}`}
          >
            {skillLabel(skill)}
            {skill.active === false ? ` (${t('inactiveSkill')})` : ''} ×
          </button>
        ))}
      </div>
      {category && category !== 'other' && (
        <button
          type="button"
          className="text-link"
          onClick={() => {
            setAll(!all);
            setPage(1);
          }}
        >
          {t(all ? 'recommendedSkills' : 'allSkills')}
        </button>
      )}
      <input
        type="search"
        aria-label={t('search')}
        placeholder={t('search')}
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
      />
      <RemoteState remote={remote}>
        <div>
          {remote.data?.results.map((skill) => (
            <label
              className={selected.has(skill.id) ? 'selected' : ''}
              key={skill.id}
            >
              <input
                type="checkbox"
                checked={selected.has(skill.id)}
                disabled={!selected.has(skill.id) && value.length >= 30}
                onChange={() => choose(skill)}
              />
              {skill.label}
            </label>
          ))}
        </div>
        {remote.data?.count === 0 && <output>{t('noSkillsFound')}</output>}
        <Pager data={remote.data} page={page} onChange={setPage} />
      </RemoteState>
    </fieldset>
  );
}

export function ProjectEditor({ project, onSaved }) {
  const { t, session } = useApp();
  const remote = useRemote('catalog');
  const [form, setForm] = useState({
    title: project?.title || '',
    description: project?.description || '',
    category: project?.category || 'development',
    budget_type: project?.budget_type || 'fixed',
    budget_min: project?.budget_min || '',
    budget_max: project?.budget_max || '',
    skills: project?.skill_details || [],
    skills_unspecified: project?.skills_unspecified || false,
    client_company: project?.client_company || '',
    deadline: project?.deadline || '',
    acceptance_criteria: project?.acceptance_criteria || '',
    demonstration_method: project?.demonstration_method || '',
    test_scenario: project?.test_scenario || '',
    review_days: project?.review_days || 3,
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
          token: session.authenticated,
          body: {
            ...form,
            skills: undefined,
            skill_ids: form.skills.map((s) => s.id),
          },
        },
      );
      setSavedId(item.id);
      for (let i = uploaded; i < files.length; i++) {
        const body = new FormData();
        body.append('file', files[i]);
        await apiRequest(`projects/${item.id}/attachments`, {
          method: 'POST',
          token: session.authenticated,
          body,
        });
        setUploaded(i + 1);
      }
      if (publish && item.status === 'draft')
        await apiRequest(`projects/${item.id}/publish`, {
          method: 'POST',
          token: session.authenticated,
        });
      if (onSaved) onSaved();
      else window.location.assign(`/projects/${item.id}`);
    } catch (err) {
      setError(apiErrorMessage(err, t));
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
            {project &&
              !remote.data?.categories.some(
                (c) => c.slug === project.category,
              ) && (
                <option value={project.category}>
                  {project.category_label}
                </option>
              )}
            {remote.data?.categories.map((c) => (
              <option value={c.slug} key={c.slug}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {remote.loading && <output className="empty-state">{t('loading')}</output>}
      <Notice error>{remote.error && <>{remote.error} <button className="text-link" type="button" onClick={remote.reload}>{t('retry')}</button></>}</Notice>
      <label className="t-check">
        <input
          type="checkbox"
          checked={form.skills_unspecified}
          onChange={(e) => {
            const checked = e.target.checked;
            if (
              checked &&
              form.skills.length &&
              !window.confirm(t('confirmClearSkills'))
            )
              return;
            setForm((f) => ({
              ...f,
              skills_unspecified: checked,
              skills: checked ? [] : f.skills,
            }));
          }}
        />
        {t('technologiesByFreelancer')}
      </label>
      {!form.skills_unspecified && (
        <SkillPicker
          key={form.category}
          category={form.category}
          hintKey="projectSkillHint"
          value={form.skills}
          onChange={(skills) => setForm((f) => ({ ...f, skills }))}
        />
      )}
      <div className="form-columns">
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
      <AcceptanceFields
        value={form}
        required
        onChange={(key, value) =>
          setForm((current) => ({ ...current, [key]: value }))
        }
      />
      <div className="actions">
        <button
          className="t-button secondary"
          value="draft"
          disabled={
            busy || remote.loading || !!remote.error || files.length > 5
          }
        >
          {t(project ? 'save' : 'saveDraft')}
        </button>
        {(!project || project.status === 'draft') && (
          <button
            className="t-button"
            value="publish"
            disabled={
              busy ||
              remote.loading ||
              !!remote.error ||
              (!form.skills.length && !form.skills_unspecified) ||
              files.length > 5
            }
          >
            {t('publish')}
          </button>
        )}
      </div>
    </form>
  );
}
