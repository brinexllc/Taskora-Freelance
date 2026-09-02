'use client';

import Link from 'next/link';
import {
  Bell, BriefcaseBusiness, CheckCircle2, Clock3, Home, LogOut, Mail, Menu,
  MessageSquare, Search, Settings, ShieldCheck, SlidersHorizontal, Sparkles, Star,
  UserRound, Wallet, X,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useApp } from '@/components/app-providers';
import { fetchProjects, logout } from '@/lib/api';

const labels = {
  uz: {
    home: 'Bosh sahifa', profile: 'Profil', orders: 'Buyurtmalar', messages: 'Xabarlar', wallet: 'Hamyon', settings: 'Sozlamalar',
    welcome: 'Xush kelibsiz', subtitle: 'Bugun qanday ishlashni xohlaysiz?', find: 'Ijrochini topish', create: 'Buyurtma yaratish',
    active: 'Faol buyurtmalar', inProgress: 'Jarayondagi ishlar', completed: 'Yakunlangan', earned: 'Hamyon',
    recommended: 'Siz uchun tavsiya etilgan buyurtmalar', details: 'Batafsil', rating: 'Reyting', projects: 'Muvaffaqiyatli loyihalar',
    deadline: 'Muddatli loyihalar', activity: 'Platformadagi faoliyat', skills: 'Ko‘nikmalar', portfolio: 'Portfolio',
    write: 'Xabar yozish', order: 'Buyurtma berish', logout: 'Chiqish', filters: 'Filtrlar', all: 'Barchasi',
  },
  ru: {
    home: 'Главная', profile: 'Профиль', orders: 'Заказы', messages: 'Сообщения', wallet: 'Кошелёк', settings: 'Настройки',
    welcome: 'Добро пожаловать', subtitle: 'Как хотите поработать сегодня?', find: 'Найти исполнителя', create: 'Создать заказ',
    active: 'Активные заказы', inProgress: 'В работе', completed: 'Завершено', earned: 'Кошелёк',
    recommended: 'Рекомендованные для вас заказы', details: 'Подробнее', rating: 'Рейтинг', projects: 'Успешных проектов',
    deadline: 'Выполнено в срок', activity: 'На платформе', skills: 'Навыки', portfolio: 'Портфолио',
    write: 'Написать', order: 'Предложить заказ', logout: 'Выйти', filters: 'Фильтры', all: 'Все',
  },
};

export default function DashboardPage() {
  const { language, setLanguage, session, clearSession } = useApp();
  const t = labels[language];
  const [view, setView] = useState('home');
  const [projects, setProjects] = useState([]);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [mobile, setMobile] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      const searchParams = new URLSearchParams(window.location.search);
      const selectedCategory = searchParams.get('category');
      const selectedView = searchParams.get('view');
      const categories = ['development', 'design', 'marketing', 'writing', 'other', 'marketing', 'other', 'development'];
      if (selectedCategory !== null) {
        setCategory(categories[Number(selectedCategory)] || 'all');
        setView('orders');
      } else if (['home', 'profile', 'orders', 'messages', 'wallet', 'settings'].includes(selectedView)) {
        setView(selectedView);
      }
      fetchProjects({ signal: controller.signal })
        .then((items) => setProjects(items))
        .catch(() => {});
    });
    return () => controller.abort();
  }, []);

  const shownProjects = useMemo(() => projects.filter((project) => {
    const matchesQuery = `${project.title} ${project.description}`.toLowerCase().includes(query.toLowerCase());
    return matchesQuery && (category === 'all' || project.category === category);
  }), [projects, query, category]);
  const fullName = session?.user?.full_name || '';

  async function signOut() {
    try { if (session?.token) await logout(session.token); }
    finally { clearSession(); window.location.assign('/'); }
  }

  function notify(message) {
    setNotice(message);
    window.setTimeout(() => setNotice(''), 2200);
  }

  const nav = [
    [Home, 'home', t.home], [UserRound, 'profile', t.profile], [BriefcaseBusiness, 'orders', t.orders],
    [Mail, 'messages', t.messages], [Wallet, 'wallet', t.wallet], [Settings, 'settings', t.settings],
  ];

  return <div className="taskora-dashboard">
    <aside className={mobile ? 'open' : ''}>
      <div className="dash-logo"><LogoMark />Taskora<button aria-label="Yopish" onClick={() => setMobile(false)}><X /></button></div>
      <nav>{nav.map(([Icon, id, name]) => <button key={id} className={view === id ? 'active' : ''} onClick={() => { setView(id); setMobile(false); }}><Icon /><span>{name}</span></button>)}</nav>
      <div className="dash-account">
        {accountOpen && <div className="dash-account-menu"><div><button className={language === 'uz' ? 'active' : ''} onClick={() => setLanguage('uz')}>UZ</button><button className={language === 'ru' ? 'active' : ''} onClick={() => setLanguage('ru')}>RU</button></div><button className="dash-logout" onClick={signOut}><LogOut />{t.logout}</button></div>}
        <button className="dash-user" onClick={() => setAccountOpen(!accountOpen)} aria-expanded={accountOpen}><Avatar /><div><b>{fullName}</b></div></button>
      </div>
    </aside>
    <div className="dash-main">
      <header className="dash-mobile-header"><button className="dash-menu" onClick={() => setMobile(true)} aria-label="Menyu"><Menu /></button><div className="dash-mobile-logo"><LogoMark />Taskora</div><button className="dash-bell" onClick={() => notify(language === 'uz' ? 'Yangi xabarlar yo‘q' : 'Новых уведомлений нет')} aria-label="Bildirishnomalar"><Bell /><i /></button><Avatar /></header>
      <main>{view === 'home'
        ? <HomeView t={t} fullName={fullName} projects={shownProjects} setView={setView} />
        : view === 'profile'
          ? <ProfileView t={t} fullName={fullName} language={language} notify={notify} />
          : <SimpleView id={view} t={t} language={language} projects={shownProjects} query={query} setQuery={setQuery} category={category} setCategory={setCategory} notify={notify} />}
      </main>
    </div>
    {notice && <div className="dash-toast"><CheckCircle2 />{notice}</div>}
  </div>;
}

function HomeView({ t, fullName, projects, setView }) {
  return <><div className="dash-welcome"><div><h1>{t.welcome}{fullName ? `, ${fullName.split(' ')[0]}` : ''} 👋</h1><p>{t.subtitle}</p></div><div><button onClick={() => setView('orders')}>{t.find}</button><Link href="/projects/new">{t.create}</Link></div></div><div className="dash-stat-grid"><Stat icon={BriefcaseBusiness} value="0" label={t.active} /><Stat icon={CheckCircle2} value="0" label={t.inProgress} /><Stat icon={Mail} value="0" label={t.completed} /><Stat icon={Wallet} value="0" label={t.earned} /></div><section className="dash-projects"><div className="dash-section-title"><h2>{t.recommended}</h2></div><div className="dash-project-grid">{projects.slice(0, 3).map((project) => <ProjectCard key={project.id} project={project} t={t} />)}</div></section></>;
}

function ProfileView({ t, fullName, language, notify }) {
  return <><section className="profile-hero"><Avatar large /><div><h1>{fullName}</h1></div><div><button onClick={() => notify(language === 'uz' ? 'Xabar oynasi ochildi' : 'Открыты сообщения')}><MessageSquare />{t.write}</button><button onClick={() => notify(language === 'uz' ? 'Buyurtma formasi ochildi' : 'Форма заказа открыта')}><BriefcaseBusiness />{t.order}</button></div></section><div className="profile-stats"><Stat icon={Star} value="0" label={t.rating} /><Stat icon={BriefcaseBusiness} value="0" label={t.projects} /><Stat icon={Clock3} value="0%" label={t.deadline} /><Stat icon={ShieldCheck} value="0" label={t.activity} /></div></>;
}

function SimpleView({ id, t, language, projects, query, setQuery, category, setCategory, notify }) {
  const title = { orders: t.orders, messages: t.messages, wallet: t.wallet, settings: t.settings }[id];
  if (id === 'orders') return <OrdersView t={t} language={language} projects={projects} query={query} setQuery={setQuery} category={category} setCategory={setCategory} />;
  return <section className="simple-view"><span>TASKORA</span><h1>{title}</h1><div className="simple-panel"><div className="simple-icon">{id === 'messages' ? <Mail /> : id === 'wallet' ? <Wallet /> : <Settings />}</div><h2>{language === 'uz' ? `${title} bo‘limi` : `Раздел «${title}»`}</h2><p>{language === 'uz' ? 'Barcha kerakli funksiyalar shu yerda mavjud.' : 'Все необходимые функции доступны здесь.'}</p><button onClick={() => notify(language === 'uz' ? 'Amal bajarildi' : 'Действие выполнено')}>{language === 'uz' ? 'Davom etish' : 'Продолжить'}</button></div></section>;
}

function OrdersView({ t, language, projects, query, setQuery, category, setCategory }) {
  const categories = [['development', 'Web'], ['other', 'Mobile'], ['design', 'Design']];
  const [sort, setSort] = useState('new');
  const [maxBudget, setMaxBudget] = useState(1000);
  const [levels, setLevels] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const visibleProjects = projects
    .filter((project) => category === 'all' || project.category === category)
    .filter((project) => Number(project.budget_min || 0) <= maxBudget)
    .filter((project) => !levels.length || levels.some((level) => (project.skills || []).some((skill) => skill.toLowerCase() === level.toLowerCase())))
    .toSorted((first, second) => {
      if (sort === 'budget') return Number(second.budget_max || 0) - Number(first.budget_max || 0);
      if (sort === 'rating') return String(first.title).localeCompare(String(second.title));
      return Number(second.id || 0) - Number(first.id || 0);
    });
  function toggleLevel(level) { setLevels((current) => current.includes(level) ? current.filter((item) => item !== level) : [...current, level]); }
  function toggleDeadline(value) { setDeadlines((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]); }
  function clearFilters() { setCategory('all'); setMaxBudget(1000); setLevels([]); setDeadlines([]); setQuery(''); }
  return <section className="orders-view"><div className="orders-heading"><div><span>TASKORA</span><h1>{t.orders}</h1></div><Link href="/projects/new">{t.create}</Link></div><div className="orders-search"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={language === 'uz' ? 'Buyurtmalarni qidiring' : 'Поиск заказов'} /></div><div className="orders-layout"><aside className="orders-filters"><h2><SlidersHorizontal />{t.filters}</h2><b>{language === 'uz' ? 'Kategoriya' : 'Категория'}</b>{categories.map(([value, name]) => <label key={value}><input type="checkbox" checked={category === value} onChange={() => setCategory(category === value ? 'all' : value)} />{name}</label>)}<b>{language === 'uz' ? 'Narx' : 'Цена'}</b><div className="orders-budget"><span>$100</span><span>${maxBudget}</span></div><input className="orders-range" type="range" min="100" max="1000" step="50" value={maxBudget} onChange={(event) => setMaxBudget(Number(event.target.value))} /><b>{language === 'uz' ? 'Muddat' : 'Срок'}</b>{[['week', language === 'uz' ? '1 hafta' : '1 неделя'], ['month', language === 'uz' ? '1 oy' : '1 месяц']].map(([value, name]) => <label key={value}><input type="checkbox" checked={deadlines.includes(value)} onChange={() => toggleDeadline(value)} />{name}</label>)}<b>{language === 'uz' ? 'Daraja' : 'Уровень'}</b>{['Junior', 'Middle', 'Senior'].map((level) => <label key={level}><input type="checkbox" checked={levels.includes(level)} onChange={() => toggleLevel(level)} />{level}</label>)}<button className="orders-clear" onClick={clearFilters}>{language === 'uz' ? 'Filterni tozalash' : 'Сбросить фильтры'}</button></aside><div className="orders-results"><div className="orders-results-head"><span>{visibleProjects.length} {language === 'uz' ? 'ta buyurtma' : 'заказа'}</span><div className="orders-sort"><button className={sort === 'new' ? 'active' : ''} onClick={() => setSort('new')}>{language === 'uz' ? 'Yangi' : 'Новые'}</button><button className={sort === 'budget' ? 'active' : ''} onClick={() => setSort('budget')}>{language === 'uz' ? 'Narx bo‘yicha' : 'По цене'}</button><button onClick={() => setSort('rating')}>{language === 'uz' ? 'Reyting bo‘yicha' : 'По рейтингу'}</button></div></div>{visibleProjects.length ? visibleProjects.map((project, index) => <OrderListCard key={project.id} project={project} language={language} featured={index === 0} />) : <p className="orders-empty">{language === 'uz' ? 'Mos buyurtmalar topilmadi' : 'Подходящих заказов не найдено'}</p>}</div></div></section>;
}

function OrderListCard({ project, language, featured }) { return <article className="order-list-card">{featured && <span className="order-ai"><Sparkles />{language === 'uz' ? 'AI Tavsiya etilgan' : 'Рекомендовано AI'}</span>}<Link href={`/projects/${project.id}`}><h3>{project.title}</h3></Link><div className="order-list-meta"><span>{project.category_label || project.category}</span><i>·</i><span>{(project.skills || []).find((skill) => ['Junior', 'Middle', 'Senior'].includes(skill)) || 'Middle'}</span><i>·</i><b>${Number(project.budget_min)}–${Number(project.budget_max)}</b></div><p>{project.description}</p><footer><div><span><Clock3 />{project.id === 2 ? '7' : '14'} {language === 'uz' ? 'kun' : 'дней'}</span><span>{language === 'uz' ? 'Buyurtmachi' : 'Заказчик'}: {project.client_name || 'Alisher T.'} ★★★★★</span></div><Link href={`/projects/${project.id}#apply`}>{language === 'uz' ? 'Ariza yuborish' : 'Отправить заявку'}</Link></footer></article>; }

function Stat({ icon: Icon, value, label }) { return <article className="dash-stat"><div><span>{label}</span><b>{value}</b></div><Icon /></article>; }
function ProjectCard({ project, t, list = false }) { return <article className={`dash-project-card ${list ? 'list' : ''}`}><div><span>{project.category_label || project.category || 'Design'}</span><small><Clock3 />3 kun</small></div><h3>{project.title}</h3><p>{project.description}</p><div className="project-skills">{(project.skills || []).slice(0, 3).map((skill) => <span key={skill}>{skill}</span>)}</div><footer><b>${Number(project.budget_min || 0).toLocaleString()} — ${Number(project.budget_max || 0).toLocaleString()}</b><Link href={`/projects/${project.id}`}>{t.details}</Link></footer></article>; }
function Avatar({ large = false }) { return <span className={`dash-avatar ${large ? 'large' : ''}`}>AK</span>; }
function LogoMark() { return <span className="dash-logo-mark">✣</span>; }
