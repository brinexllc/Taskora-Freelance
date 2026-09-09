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
    professional_title: profile.professional_title || '',
    location: profile.location || '',
    portfolio: profile.portfolio || [],
    services: profile.services || [],
    spoken_languages: (profile.spoken_languages || []).join('\n'),
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
          spoken_languages: form.spoken_languages
            .split('\n')
            .map((value) => value.trim())
            .filter(Boolean),
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
                <Field label={t('professionalTitle')}>
                  <input
                    maxLength={160}
                    value={form.professional_title}
                    onChange={change('professional_title')}
                  />
                </Field>
                <Field label={t('location')}>
                  <input
                    maxLength={160}
                    value={form.location}
                    onChange={change('location')}
                  />
                </Field>
                <SkillPicker
                  value={form.skills}
                  onChange={(skills) => setForm((f) => ({ ...f, skills }))}
                />
                <Field label={t('spokenLanguages')}>
                  <textarea
                    value={form.spoken_languages}
                    onChange={change('spoken_languages')}
                    maxLength={800}
                    placeholder={t('languagesHint')}
                  />
                </Field>
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
                <fieldset id="portfolio" className="showcase-editor">
                  <legend>{t('portfolio')}</legend>
                  {form.portfolio.map((item, index) => (
                    <div className="showcase-editor-item" key={index}>
                      <Field label={t('itemTitle')}>
                        <input
                          required
                          maxLength={160}
                          value={item.title}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              portfolio: f.portfolio.map((p, i) =>
                                i === index
                                  ? { ...p, title: e.target.value }
                                  : p,
                              ),
                            }))
                          }
                        />
                      </Field>
                      <Field label={t('category')}>
                        <input
                          maxLength={80}
                          value={item.category}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              portfolio: f.portfolio.map((p, i) =>
                                i === index
                                  ? { ...p, category: e.target.value }
                                  : p,
                              ),
                            }))
                          }
                        />
                      </Field>
                      <Field label={t('description')}>
                        <textarea
                          maxLength={1000}
                          value={item.description}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              portfolio: f.portfolio.map((p, i) =>
                                i === index
                                  ? { ...p, description: e.target.value }
                                  : p,
                              ),
                            }))
                          }
                        />
                      </Field>
                      <Field label={t('projectLink')}>
                        <input
                          type="url"
                          value={item.url}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              portfolio: f.portfolio.map((p, i) =>
                                i === index ? { ...p, url: e.target.value } : p,
                              ),
                            }))
                          }
                        />
                      </Field>
                      <Field label={t('coverImage')}>
                        <input
                          type="file"
                          accept="image/png,image/jpeg,image/webp"
                          onChange={async (e) => {
                            try {
                              const image = await readImage(
                                e.target.files?.[0],
                              );
                              setForm((f) => ({
                                ...f,
                                portfolio: f.portfolio.map((p, i) =>
                                  i === index ? { ...p, image } : p,
                                ),
                              }));
                            } catch (err) {
                              setError(err.message);
                            }
                          }}
                        />
                      </Field>
                      {item.image && (
                        <Avatar
                          profile={{
                            avatar: item.image,
                            full_name: item.title,
                          }}
                        />
                      )}
                      <button
                        type="button"
                        className="text-link danger"
                        onClick={() =>
                          setForm((f) => ({
                            ...f,
                            portfolio: f.portfolio.filter(
                              (_, i) => i !== index,
                            ),
                          }))
                        }
                      >
                        {t('removeItem')}
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="t-button secondary"
                    disabled={form.portfolio.length >= 9}
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        portfolio: [
                          ...f.portfolio,
                          {
                            title: '',
                            category: '',
                            description: '',
                            image: '',
                            url: '',
                          },
                        ],
                      }))
                    }
                  >
                    + {t('addPortfolio')}
                  </button>
                </fieldset>
                <fieldset id="services" className="showcase-editor">
                  <legend>{t('services')}</legend>
                  {form.services.map((item, index) => (
                    <div className="showcase-editor-item" key={index}>
                      <Field label={t('itemTitle')}>
                        <input
                          required
                          maxLength={160}
                          value={item.title}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              services: f.services.map((s, i) =>
                                i === index
                                  ? { ...s, title: e.target.value }
                                  : s,
                              ),
                            }))
                          }
                        />
                      </Field>
                      <Field label={t('description')}>
                        <textarea
                          maxLength={1000}
                          value={item.description}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              services: f.services.map((s, i) =>
                                i === index
                                  ? { ...s, description: e.target.value }
                                  : s,
                              ),
                            }))
                          }
                        />
                      </Field>
                      <Field label={`${t('servicePrice')} (UZS)`}>
                        <input
                          type="number"
                          required
                          min="0"
                          step="0.01"
                          value={item.price}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              services: f.services.map((s, i) =>
                                i === index
                                  ? { ...s, price: e.target.value }
                                  : s,
                              ),
                            }))
                          }
                        />
                      </Field>
                      <Field label={t('deliveryDays')}>
                        <input
                          type="number"
                          required
                          min="1"
                          max="365"
                          value={item.delivery_days}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              services: f.services.map((s, i) =>
                                i === index
                                  ? { ...s, delivery_days: e.target.value }
                                  : s,
                              ),
                            }))
                          }
                        />
                      </Field>
                      <button
                        type="button"
                        className="text-link danger"
                        onClick={() =>
                          setForm((f) => ({
                            ...f,
                            services: f.services.filter((_, i) => i !== index),
                          }))
                        }
                      >
                        {t('removeItem')}
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="t-button secondary"
                    disabled={form.services.length >= 6}
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        services: [
                          ...f.services,
                          {
                            title: '',
                            description: '',
                            price: '',
                            delivery_days: 7,
                          },
                        ],
                      }))
                    }
                  >
                    + {t('addService')}
                  </button>
                </fieldset>
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
