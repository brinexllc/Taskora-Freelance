'use client';

import Link from 'next/link';
import {
  Bell, BriefcaseBusiness, CheckCircle2, Clock3, Home, LogOut, Mail, Menu,
  MessageSquare, Search, Settings, ShieldCheck, SlidersHorizontal, Star,
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

const fallbackProjects = [
  { id: 1, title: 'Landing Page dizayni', category: 'design', description: 'Fintech mahsuloti uchun zamonaviy va mobilga mos landing page.', budget_min: '1000000', budget_max: '3000000', skills: ['UI/UX', 'Figma'], proposal_count: 6 },
  { id: 2, title: 'Instagram uchun 10 ta post dizayni', category: 'marketing', description: 'Yangi brend uchun yagona uslubdagi ijtimoiy tarmoq postlari.', budget_min: '800000', budget_max: '1500000', skills: ['SMM', 'Design'], proposal_count: 4 },
  { id: 3, title: 'Ikki tilli korporativ sayt yaratish', category: 'development', description: 'Kompaniya uchun tezkor, ikki tilli korporativ web-sayt.', budget_min: '3000000', budget_max: '5000000', skills: ['React', 'Django'], proposal_count: 9 },
];

export default function DashboardPage() {
  const { language, setLanguage, session, clearSession } = useApp();
  const t = labels[language];
  const [view, setView] = useState('home');
  const [projects, setProjects] = useState(fallbackProjects);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [mobile, setMobile] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      const selectedCategory = new URLSearchParams(window.location.search).get('category');
    const categories = ['development', 'design', 'marketing', 'writing', 'other', 'marketing', 'other', 'development'];
      if (selectedCategory !== null) {
        setCategory(categories[Number(selectedCategory)] || 'all');
        setView('orders');
      }
      fetchProjects({ signal: controller.signal })
        .then((items) => { if (items.length) setProjects(items); })
        .catch(() => {});
    });
    return () => controller.abort();
  }, []);

  const shownProjects = useMemo(() => projects.filter((project) => {
    const matchesQuery = `${project.title} ${project.description}`.toLowerCase().includes(query.toLowerCase());
    return matchesQuery && (category === 'all' || project.category === category);
  }), [projects, query, category]);
  const fullName = session?.user?.full_name || 'Azizbek Karimov';

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
      <nav>{nav.map(([Icon, id, name]) => <button key={id} className={view === id ? 'active' : ''} onClick={() => { setView(id); setMobile(false); }}><Icon /><span>{name}</span>{id === 'messages' && <i>3</i>}</button>)}</nav>
      <div className="dash-account">
        {accountOpen && <div className="dash-account-menu"><div><button className={language === 'uz' ? 'active' : ''} onClick={() => setLanguage('uz')}>UZ</button><button className={language === 'ru' ? 'active' : ''} onClick={() => setLanguage('ru')}>RU</button></div><button className="dash-logout" onClick={signOut}><LogOut />{t.logout}</button></div>}
        <button className="dash-user" onClick={() => setAccountOpen(!accountOpen)} aria-expanded={accountOpen}><Avatar /><div><b>{fullName}</b><span>PREMIUM</span></div></button>
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
  return <><div className="dash-welcome"><div><h1>{t.welcome}, {fullName.split(' ')[0]} 👋</h1><p>{t.subtitle}</p></div><div><button onClick={() => setView('orders')}>{t.find}</button><Link href="/projects/new">{t.create}</Link></div></div><div className="dash-stat-grid"><Stat icon={BriefcaseBusiness} value="4" label={t.active} /><Stat icon={CheckCircle2} value="2" label={t.inProgress} /><Stat icon={Mail} value="18" label={t.completed} /><Stat icon={Wallet} value="2 450 000 so‘m" label={t.earned} /></div><section className="dash-projects"><div className="dash-section-title"><h2>{t.recommended}</h2></div><div className="dash-project-grid">{projects.slice(0, 3).map((project) => <ProjectCard key={project.id} project={project} t={t} />)}</div></section></>;
}

function ProfileView({ t, fullName, language, notify }) {
  const portfolio = ['SavdoFlow — E-commerce dizayni', 'MedCare — Tibbiyot ilovasi', 'EcoHush — Ta’lim platformasi', 'Finance AI Dashboard', 'Travel mobile app', 'SaaS landing page'];
  return <><section className="profile-hero"><Avatar large /><div><h1>{fullName}<ShieldCheck /></h1><p>@azizbekdesign · Toshkent, O‘zbekiston</p><b>UI/UX Designer & Tilda Developer</b><span>{language === 'uz' ? 'Zamonaviy va foydalanuvchilarga qulay dizayn yaratish — mening asosiy maqsadim. 2 yildan ortiq tajriba.' : 'Создаю современные и удобные интерфейсы. Более двух лет опыта.'}</span></div><div><button onClick={() => notify(language === 'uz' ? 'Xabar oynasi ochildi' : 'Открыты сообщения')}><MessageSquare />{t.write}</button><button onClick={() => notify(language === 'uz' ? 'Buyurtma formasi ochildi' : 'Форма заказа открыта')}><BriefcaseBusiness />{t.order}</button></div></section><div className="profile-stats"><Stat icon={Star} value="4.9" label={t.rating} /><Stat icon={BriefcaseBusiness} value="27 loyiha" label={t.projects} /><Stat icon={Clock3} value="98%" label={t.deadline} /><Stat icon={ShieldCheck} value="2 yil Taskorada" label={t.activity} /></div><section className="profile-skills"><h2>{t.skills}</h2><div>{['UI/UX Design', 'Figma', 'Tilda', 'Web Design', 'Graphic Design'].map((skill) => <span key={skill}>{skill}</span>)}</div></section><section><div className="dash-section-title"><h2>{t.portfolio}</h2></div><div className="portfolio-grid">{portfolio.map((name, i) => <button key={name} onClick={() => notify(name)}><div className={`portfolio-art art-${i % 3}`}><span /><span /><span /></div><b>{name}</b><small>{language === 'uz' ? 'Ko‘rish' : 'Открыть'} →</small></button>)}</div></section></>;
}

function SimpleView({ id, t, language, projects, query, setQuery, category, setCategory, notify }) {
  const title = { orders: t.orders, messages: t.messages, wallet: t.wallet, settings: t.settings }[id];
  if (id === 'orders') return <OrdersView t={t} language={language} projects={projects} query={query} setQuery={setQuery} category={category} setCategory={setCategory} />;
  return <section className="simple-view"><span>TASKORA</span><h1>{title}</h1><div className="simple-panel"><div className="simple-icon">{id === 'messages' ? <Mail /> : id === 'wallet' ? <Wallet /> : <Settings />}</div><h2>{language === 'uz' ? `${title} bo‘limi` : `Раздел «${title}»`}</h2><p>{language === 'uz' ? 'Barcha kerakli funksiyalar shu yerda mavjud.' : 'Все необходимые функции доступны здесь.'}</p><button onClick={() => notify(language === 'uz' ? 'Amal bajarildi' : 'Действие выполнено')}>{language === 'uz' ? 'Davom etish' : 'Продолжить'}</button></div></section>;
}

function OrdersView({ t, language, projects, query, setQuery, category, setCategory }) {
  const categories = [['all', t.all], ['development', language === 'uz' ? 'Web dasturlash' : 'Веб-разработка'], ['design', 'UI/UX Design'], ['marketing', 'Marketing'], ['writing', language === 'uz' ? 'Matnlar' : 'Тексты']];
  const [sort, setSort] = useState('new');
  const [maxBudget, setMaxBudget] = useState(10000000);
  const [levels, setLevels] = useState([]);
  const visibleProjects = projects
    .filter((project) => Number(project.budget_min || 0) <= maxBudget)
    .filter((project) => !levels.length || levels.some((level) => (project.skills || []).some((skill) => skill.toLowerCase() === level.toLowerCase())))
    .toSorted((first, second) => sort === 'budget' ? Number(second.budget_max || 0) - Number(first.budget_max || 0) : Number(second.id || 0) - Number(first.id || 0));
  function toggleLevel(level) { setLevels((current) => current.includes(level) ? current.filter((item) => item !== level) : [...current, level]); }
  return <section className="orders-view"><div className="orders-heading"><div><span>TASKORA</span><h1>{t.orders}</h1></div><Link href="/projects/new">{t.create}</Link></div><div className="orders-search"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={language === 'uz' ? 'Buyurtmalarni qidiring' : 'Поиск заказов'} /></div><div className="orders-layout"><aside className="orders-filters"><h2><SlidersHorizontal />{t.filters}</h2><b>{language === 'uz' ? 'Kategoriya' : 'Категория'}</b>{categories.map(([value, name]) => <label key={value}><input type="radio" name="category" checked={category === value} onChange={() => setCategory(value)} />{name}</label>)}<b>{language === 'uz' ? 'Byudjet' : 'Бюджет'}</b><div className="orders-budget"><span>100 000</span><span>{maxBudget.toLocaleString()}</span></div><input className="orders-range" type="range" min="100000" max="10000000" step="100000" value={maxBudget} onChange={(event) => setMaxBudget(Number(event.target.value))} /><b>{language === 'uz' ? 'Daraja' : 'Уровень'}</b>{['Junior', 'Middle', 'Senior'].map((level) => <label key={level}><input type="checkbox" checked={levels.includes(level)} onChange={() => toggleLevel(level)} />{level}</label>)}</aside><div className="orders-results"><div className="orders-results-head"><span>{visibleProjects.length} {language === 'uz' ? 'ta buyurtma' : 'заказа'}</span><select value={sort} onChange={(event) => setSort(event.target.value)} aria-label={language === 'uz' ? 'Saralash' : 'Сортировка'}><option value="new">{language === 'uz' ? 'Eng yangilari' : 'Сначала новые'}</option><option value="budget">{language === 'uz' ? 'Yuqori byudjet' : 'Высокий бюджет'}</option></select></div>{visibleProjects.length ? visibleProjects.map((project) => <ProjectCard key={project.id} project={project} t={t} list />) : <p className="orders-empty">{language === 'uz' ? 'Mos buyurtmalar topilmadi' : 'Подходящих заказов не найдено'}</p>}</div></div></section>;
}

function Stat({ icon: Icon, value, label }) { return <article className="dash-stat"><div><span>{label}</span><b>{value}</b></div><Icon /></article>; }
function ProjectCard({ project, t, list = false }) { return <article className={`dash-project-card ${list ? 'list' : ''}`}><div><span>{project.category_label || project.category || 'Design'}</span><small><Clock3 />3 kun</small></div><h3>{project.title}</h3><p>{project.description}</p><div className="project-skills">{(project.skills || []).slice(0, 3).map((skill) => <span key={skill}>{skill}</span>)}</div><footer><b>{Number(project.budget_min || 0).toLocaleString()} — {Number(project.budget_max || 0).toLocaleString()} so‘m</b><Link href={`/projects/${project.id}`}>{t.details}</Link></footer></article>; }
function Avatar({ large = false }) { return <span className={`dash-avatar ${large ? 'large' : ''}`}>AK</span>; }
function LogoMark() { return <span className="dash-logo-mark">✣</span>; }
