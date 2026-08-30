'use client';

import Link from 'next/link';
import { ArrowLeft, CheckCircle2, Clock3, ShieldCheck, Sparkles, Star, UserRound } from 'lucide-react';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useApp } from '@/components/app-providers';
import { createProposal, fetchProject } from '@/lib/api';

const fallback = {
  id: 1,
  title: 'E-commerce sayt ishlab chiqish',
  description: "Bizning onlayn do‘konimiz uchun zamonaviy React asosidagi frontend kerak.",
  category: 'development', category_label: 'Web Frontend', budget_min: '500', budget_max: '800', skills: ['React', 'Middle'], client_name: 'Alisher Toshmatov', client_company: 'Do‘stona · Tasdiqlangan', proposal_count: 8,
};

function fallbackFor(id) {
  if (String(id) === '2') return { ...fallback, id: 2, title: 'Mobile app UI dizayn', description: 'Fintech mobil ilovasi uchun zamonaviy va foydalanuvchiga qulay UI dizayn kerak.', category: 'design', category_label: 'UI/UX', budget_min: '200', budget_max: '400', skills: ['Figma', 'Junior'], client_name: 'Malika Ahmedova', client_company: 'Do‘stona · Tasdiqlangan' };
  if (String(id) === '3') return { ...fallback, id: 3, title: 'Telegram bot yaratish', description: 'Buyurtmalarni qabul qiluvchi va boshqaruvchi tezkor Telegram bot kerak.', category_label: 'Backend', budget_min: '300', budget_max: '600', skills: ['Python', 'Middle'], client_name: 'Sardor Aripov', client_company: 'Do‘stona · Tasdiqlangan' };
  return { ...fallback, id };
}

export default function ProjectDetailsPage() {
  const params = useParams();
  const projectId = params?.id || '1';
  const { language, session } = useApp();
  const uz = language === 'uz';
  const [project, setProject] = useState(() => fallbackFor(projectId));
  const [formOpen, setFormOpen] = useState(false);
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    freelancer_name: session?.user?.full_name || '', freelancer_email: session?.user?.email || '',
    cover_letter: '', amount: '650', delivery_days: '14',
  });

  useEffect(() => {
    const controller = new AbortController();
    fetchProject(projectId, { signal: controller.signal }).then(setProject).catch(() => setProject(fallbackFor(projectId)));
    return () => controller.abort();
  }, [projectId]);

  useEffect(() => {
    const openFromHash = () => {
      if (window.location.hash === '#apply') setFormOpen(true);
    };
    const frame = window.requestAnimationFrame(openFromHash);
    window.addEventListener('hashchange', openFromHash);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('hashchange', openFromHash);
    };
  }, []);

  function change(key) { return (event) => setForm((value) => ({ ...value, [key]: event.target.value })); }
  async function submit(event) {
    event.preventDefault(); setLoading(true); setError('');
    try {
      await createProposal({ ...form, project: Number(project.id), delivery_days: Number(form.delivery_days) }, session?.token);
      setSent(true); setFormOpen(false);
    } catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  }

  return <main className="project-detail-page"><div className="project-detail-shell"><Link className="project-back" href="/dashboard?view=orders"><ArrowLeft />{uz ? 'Orqaga' : 'Назад'}</Link><div className="project-detail-layout"><article className="project-description-card"><div className="project-detail-tags"><span>{project.category_label || 'Web Frontend'}</span>{(project.skills || []).map((skill) => <span key={skill}>{skill}</span>)}</div><h1>{project.title}</h1><div className="project-detail-meta"><span><b>{uz ? 'Narx' : 'Бюджет'}</b>${Number(project.budget_min).toLocaleString()} – ${Number(project.budget_max).toLocaleString()}</span><span><b>{uz ? 'Muddat' : 'Срок'}</b><Clock3 />14 {uz ? 'kun' : 'дней'}</span></div><h2>{uz ? 'Loyiha tavsifi' : 'Описание проекта'}</h2><p>{project.description}</p><h2>{uz ? 'Talablar' : 'Требования'}</h2><ul><li>{uz ? 'Mahsulot katalogi' : 'Каталог товаров'}</li><li>{uz ? 'Savatcha funksiyasi' : 'Функция корзины'}</li><li>{uz ? 'To‘lov integratsiyasi' : 'Интеграция оплаты'}</li><li>{uz ? 'Mobil adaptiv dizayn' : 'Мобильный адаптивный дизайн'}</li></ul></article><aside className="project-client-column"><section className="project-client-card"><div className="project-client-head"><span>AT</span><div><h2>{project.client_name || 'Alisher Toshmatov'}<ShieldCheck /></h2><p>{project.client_company || 'Do‘stona · Tasdiqlangan'}</p></div></div><div className="client-rating"><Star />6.2/7 · 12 {uz ? 'ta yakunlangan' : 'завершено'}</div><div className="verified-line"><CheckCircle2 />{uz ? 'Shaxs tasdiqlangan' : 'Личность подтверждена'}</div></section><section className="project-ai-card"><Sparkles /><div><b>{uz ? 'AI Tavsiya' : 'Рекомендация AI'}</b><p>{uz ? 'Jasur K. — eng mos' : 'Jasur K. — лучший выбор'}</p><div className="ai-person"><span>JK</span><div><strong>Jasur Karimov</strong><small>★★★★★★★ · Senior</small></div></div></div></section>{sent ? <div className="proposal-success"><CheckCircle2 /><b>{uz ? 'Ariza yuborildi' : 'Заявка отправлена'}</b><span>{uz ? 'Buyurtmachi tez orada javob beradi.' : 'Заказчик скоро ответит.'}</span></div> : <button className="proposal-open" onClick={() => setFormOpen(true)}>{uz ? 'Ariza yuborish' : 'Отправить заявку'}</button>}</aside></div></div>{formOpen && <dialog open className="proposal-modal"><form onSubmit={submit}><button className="proposal-close" type="button" onClick={() => setFormOpen(false)} aria-label="Yopish">×</button><UserRound /><h2>{uz ? 'Ariza yuborish' : 'Отправить заявку'}</h2><label>{uz ? 'Ism' : 'Имя'}<input value={form.freelancer_name} onChange={change('freelancer_name')} required /></label><label>Email<input type="email" value={form.freelancer_email} onChange={change('freelancer_email')} required /></label><label>{uz ? 'Taklifingiz' : 'Ваше предложение'}<textarea value={form.cover_letter} onChange={change('cover_letter')} required /></label><div><label>{uz ? 'Narx' : 'Стоимость'}<input type="number" min="0" value={form.amount} onChange={change('amount')} required /></label><label>{uz ? 'Kun' : 'Дней'}<input type="number" min="1" value={form.delivery_days} onChange={change('delivery_days')} required /></label></div>{error && <p className="auth-error">{error}</p>}<button className="proposal-submit" disabled={loading}>{loading ? '…' : (uz ? 'Yuborish' : 'Отправить')}</button></form></dialog>}</main>;
}
