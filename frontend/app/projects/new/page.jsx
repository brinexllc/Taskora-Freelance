'use client';

import Link from 'next/link';
import { ArrowLeft, BriefcaseBusiness, CheckCircle2 } from 'lucide-react';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { createProject } from '@/lib/api';

export default function NewProjectPage() {
  const { language, session } = useApp();
  const uz = language === 'uz';
  const [form, setForm] = useState({ title: '', description: '', category: 'development', budget_min: '', budget_max: '', skills: '', client_name: session?.user?.full_name || '', client_company: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  function change(key) { return (event) => setForm((value) => ({ ...value, [key]: event.target.value })); }
  async function submit(event) {
    event.preventDefault(); setLoading(true); setError('');
    try {
      const created = await createProject({ ...form, skills: form.skills.split(',').map((skill) => skill.trim()).filter(Boolean), budget_min: Number(form.budget_min), budget_max: Number(form.budget_max), status: 'active' }, session?.token);
      window.location.assign(`/projects/${created.id}`);
    } catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  }
  return <main className="new-project-page"><div className="new-project-shell"><Link className="project-back" href="/dashboard"><ArrowLeft />{uz ? 'Orqaga' : 'Назад'}</Link><form className="new-project-card" onSubmit={submit}><div className="new-project-icon"><BriefcaseBusiness /></div><h1>{uz ? 'Yangi buyurtma yarating' : 'Создайте новый заказ'}</h1><p>{uz ? 'Talablaringizni kiriting va mos ijrochini toping' : 'Опишите требования и найдите подходящего исполнителя'}</p><label>{uz ? 'Loyiha nomi' : 'Название проекта'}<input value={form.title} onChange={change('title')} required /></label><label>{uz ? 'Tavsif' : 'Описание'}<textarea value={form.description} onChange={change('description')} required /></label><div className="new-project-row"><label>{uz ? 'Kategoriya' : 'Категория'}<select value={form.category} onChange={change('category')}><option value="development">Development</option><option value="design">Design</option><option value="marketing">Marketing</option><option value="writing">Writing</option><option value="other">Other</option></select></label><label>{uz ? 'Ko‘nikmalar' : 'Навыки'}<input value={form.skills} onChange={change('skills')} placeholder="React, Django, Figma" /></label></div><div className="new-project-row"><label>{uz ? 'Minimal byudjet' : 'Бюджет от'}<input type="number" min="0" value={form.budget_min} onChange={change('budget_min')} required /></label><label>{uz ? 'Maksimal byudjet' : 'Бюджет до'}<input type="number" min="0" value={form.budget_max} onChange={change('budget_max')} required /></label></div><div className="new-project-row"><label>{uz ? 'Buyurtmachi' : 'Заказчик'}<input value={form.client_name} onChange={change('client_name')} required /></label><label>{uz ? 'Kompaniya' : 'Компания'}<input value={form.client_company} onChange={change('client_company')} /></label></div>{error && <p className="auth-error">{error}</p>}<button disabled={loading}>{loading ? '…' : <><CheckCircle2 />{uz ? 'Buyurtmani joylash' : 'Опубликовать заказ'}</>}</button></form></div></main>;
}
