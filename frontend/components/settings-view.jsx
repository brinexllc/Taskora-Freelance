'use client';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { apiRequest, setRole } from '@/lib/api';
import { Avatar, Field, Notice, readImage } from '@/components/taskora-ui';
import { SkillPicker } from '@/components/project-editor';
import { PasswordChange } from '@/components/password-change';
import { languages } from '@/lib/i18n';
export function SettingsView() {
  const { t, session, updateUser, language, setLanguage, theme, setTheme } =
    useApp();
  const profile = session.user.profile;
  const [form, setForm] = useState({
    about: profile.about,
    avatar: profile.avatar,
    skills: profile.skill_details || [],
    professional_experience: profile.professional_experience || '',
    available: profile.available,
    rate: profile.rate,
    rate_unit: profile.rate_unit,
  });
  const [role, setChosenRole] = useState(session.user.role);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const change = (key) => (e) => {
    const value = e.target.value;
    setForm((current) => ({ ...current, [key]: value }));
  };
  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const user = await apiRequest('auth/me', {
        method: 'PATCH',
        token: session.token,
        body: {
          ...form,
          skills: undefined,
          skill_ids: form.skills.map((s) => s.id),
        },
      });
      updateUser(user);
      setNotice(t('profileSaved'));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function changeRole(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      updateUser(await setRole(role, session.token));
      setNotice(t('roleSaved'));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>{t('settings')}</h1>
      <Notice error>{error}</Notice>
      <Notice>{notice}</Notice>
      <div className="two-columns">
        <section className="t-card">
          <h2>{t('profile')}</h2>
          <form className="t-form" onSubmit={save}>
            <Avatar profile={{ ...profile, avatar: form.avatar }} large />
            <Field label={t('uploadAvatar')}>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={async (e) => {
                  try {
                    const avatar = await readImage(e.target.files?.[0]);
                    setForm((current) => ({ ...current, avatar }));
                    setError('');
                  } catch (err) {
                    setError(err.message);
                    e.target.value = '';
                  }
                }}
              />
            </Field>
            {form.avatar && (
              <button
                className="text-link"
                type="button"
                onClick={() =>
                  setForm((current) => ({ ...current, avatar: '' }))
                }
              >
                {t('removeAvatar')}
              </button>
            )}
            <Field label={t('about')}>
              <textarea
                value={form.about}
                onChange={change('about')}
                maxLength={3000}
              />
            </Field>
            {session.user.role === 'freelancer' && (
              <>
                <SkillPicker
                  value={form.skills}
                  onChange={(skills) => setForm((f) => ({ ...f, skills }))}
                />
                <Field label={t('professionalExperience')}>
                  <textarea
                    maxLength={3000}
                    value={form.professional_experience}
                    onChange={change('professional_experience')}
                  />
                </Field>
                <label className="t-check">
                  <input
                    type="checkbox"
                    checked={form.available}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, available: e.target.checked }))
                    }
                  />
                  {t('available')}
                </label>
                <div className="form-columns">
                  <Field label={`${t('rate')} (UZS)`}>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.rate}
                      onChange={change('rate')}
                      required
                    />
                  </Field>
                  <Field label={t('rateUnit')}>
                    <select
                      value={form.rate_unit}
                      onChange={change('rate_unit')}
                    >
                      <option value="hour">{t('hour')}</option>
                      <option value="day">{t('day')}</option>
                    </select>
                  </Field>
                </div>
              </>
            )}
            <button className="t-button" disabled={busy}>
              {busy ? t('loading') : t('save')}
            </button>
          </form>
        </section>
        <div className="list-stack">
          <PasswordChange />
          <section className="t-card">
            <h2>{t('role')}</h2>
            <form className="t-form" onSubmit={changeRole}>
              <Field label={t('chooseRole')}>
                <select
                  value={role}
                  onChange={(e) => setChosenRole(e.target.value)}
                >
                  <option value="freelancer">{t('freelancer')}</option>
                  <option value="client">{t('client')}</option>
                </select>
              </Field>
              <button
                className="t-button secondary"
                disabled={busy || role === session.user.role}
              >
                {t('save')}
              </button>
            </form>
          </section>
          <section className="t-card t-form">
            <Field label={t('language')}>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                {languages.map(([key, label]) => (
                  <option value={key} key={key}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t('theme')}>
              <select value={theme} onChange={(e) => setTheme(e.target.value)}>
                <option value="light">{t('light')}</option>
                <option value="dark">{t('dark')}</option>
              </select>
            </Field>
          </section>
        </div>
      </div>
    </>
  );
}
