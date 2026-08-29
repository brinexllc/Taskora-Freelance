'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ArrowUpRight,
  Bell,
  Bookmark,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Code2,
  Layers3,
  Menu,
  MessageCircle,
  Palette,
  Search,
  SlidersHorizontal,
  Sparkles,
  Star,
  Target,
  TrendingUp,
  Users,
  X,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const categoryLabels = {
  development: 'Разработка',
  design: 'Дизайн',
  marketing: 'Маркетинг',
  writing: 'Тексты',
  other: 'Другое',
};

const demoProjects = [
  {
    id: 'demo-1',
    title: 'Лендинг для нового финтех-продукта',
    description:
      'Ищем разработчика, который соберёт быстрый адаптивный лендинг по готовому дизайну и подключит форму заявки.',
    category: 'development',
    budget_min: '1200.00',
    budget_max: '1800.00',
    skills: ['React', 'Next.js', 'Tailwind'],
    client_name: 'Алексей Морозов',
    client_company: 'NorthPay',
    proposal_count: 8,
    created_at: new Date(Date.now() - 1000 * 60 * 34).toISOString(),
    featured: true,
  },
  {
    id: 'demo-2',
    title: 'Айдентика для кофейного бренда',
    description:
      'Нужны логотип, базовая система упаковки и компактный брендбук для сети кофеен нового формата.',
    category: 'design',
    budget_min: '850.00',
    budget_max: '1200.00',
    skills: ['Figma', 'Branding', 'Illustrator'],
    client_name: 'Дарья Волкова',
    client_company: 'Soma Coffee',
    proposal_count: 14,
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
  },
  {
    id: 'demo-3',
    title: 'SEO-стратегия для SaaS-сервиса',
    description:
      'Провести аудит, собрать семантическое ядро и подготовить дорожную карту роста на ближайшие шесть месяцев.',
    category: 'marketing',
    budget_min: '700.00',
    budget_max: '950.00',
    skills: ['SEO', 'Analytics', 'Strategy'],
    client_name: 'Михаил Ким',
    client_company: 'Flowdesk',
    proposal_count: 5,
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
  },
];

const categories = [
  { value: 'all', label: 'Все проекты', icon: Layers3 },
  { value: 'development', label: 'Разработка', icon: Code2 },
  { value: 'design', label: 'Дизайн', icon: Palette },
  { value: 'marketing', label: 'Маркетинг', icon: TrendingUp },
];

function formatBudget(project) {
  const minimum = Number(project.budget_min).toLocaleString('ru-RU');
  const maximum = Number(project.budget_max).toLocaleString('ru-RU');
  return `$${minimum} – $${maximum}`;
}

function timeAgo(date) {
  const hours = Math.max(1, Math.floor((Date.now() - new Date(date)) / 3600000));
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.floor(hours / 24)} дн назад`;
}

function ProjectCard({ project, saved, onSave }) {
  return (
    <article className="project-card group">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge className="category-badge" variant="secondary">
              {categoryLabels[project.category] || 'Проект'}
            </Badge>
            {project.featured && (
              <span className="featured-label">
                <Sparkles aria-hidden="true" /> Рекомендуем
              </span>
            )}
          </div>
          <h3 className="project-title">{project.title}</h3>
        </div>
        <Button
          aria-label={saved ? 'Удалить из сохранённых' : 'Сохранить проект'}
          className={saved ? 'save-button is-saved' : 'save-button'}
          onClick={() => onSave(project.id)}
          size="icon"
          variant="ghost"
        >
          <Bookmark fill={saved ? 'currentColor' : 'none'} />
        </Button>
      </div>

      <p className="project-description">{project.description}</p>

      <div className="mb-6 flex flex-wrap gap-2">
        {project.skills.map((skill) => (
          <span className="skill-chip" key={skill}>{skill}</span>
        ))}
      </div>

      <div className="project-footer">
        <div>
          <p className="budget-label">Бюджет проекта</p>
          <p className="budget-value">{formatBudget(project)}</p>
        </div>
        <div className="project-meta">
          <span><Clock3 /> {timeAgo(project.created_at)}</span>
          <span><Users /> {project.proposal_count} откликов</span>
        </div>
        <Button className="details-button" size="lg">
          Подробнее <ArrowUpRight aria-hidden="true" />
        </Button>
      </div>
    </article>
  );
}

export default function Home() {
  const [projects, setProjects] = useState(demoProjects);
  const [category, setCategory] = useState('all');
  const [query, setQuery] = useState('');
  const [saved, setSaved] = useState(new Set());
  const [mobileOpen, setMobileOpen] = useState(false);
  const [apiState, setApiState] = useState('loading');

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';
    fetch(`${apiUrl}/projects/`)
      .then((response) => {
        if (!response.ok) throw new Error('API unavailable');
        return response.json();
      })
      .then((data) => {
        const results = Array.isArray(data) ? data : data.results;
        if (results?.length) setProjects(results);
        setApiState('connected');
      })
      .catch(() => setApiState('demo'));
  }, []);

  const filteredProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return projects.filter((project) => {
      const matchesCategory = category === 'all' || project.category === category;
      const searchable = `${project.title} ${project.description} ${project.skills.join(' ')}`.toLowerCase();
      return matchesCategory && searchable.includes(normalizedQuery);
    });
  }, [category, projects, query]);

  const toggleSaved = (projectId) => {
    setSaved((current) => {
      const next = new Set(current);
      if (next.has(projectId)) next.delete(projectId);
      else next.add(projectId);
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="site-header">
        <div className="shell flex h-full items-center justify-between gap-5">
          <a aria-label="Taskora — главная" className="brand" href="#">
            <span className="brand-mark"><span /><span /></span>
            <span>taskora</span>
          </a>

          <nav aria-label="Главная навигация" className="desktop-nav">
            <a className="active" href="#projects">Найти проект</a>
            <a href="#how-it-works">Как это работает</a>
            <a href="#talents">Специалисты</a>
          </nav>

          <div className="header-actions">
            <Button aria-label="Уведомления" className="notification-button" size="icon" variant="ghost">
              <Bell /><span className="notification-dot" />
            </Button>
            <Button className="outline-action hidden sm:inline-flex" variant="outline">Войти</Button>
            <Button className="primary-action hidden sm:inline-flex">Разместить проект</Button>
            <Button
              aria-label="Открыть меню"
              className="mobile-menu-button md:hidden"
              onClick={() => setMobileOpen((open) => !open)}
              size="icon"
              variant="ghost"
            >
              {mobileOpen ? <X /> : <Menu />}
            </Button>
          </div>
        </div>
        {mobileOpen && (
          <nav aria-label="Мобильная навигация" className="mobile-nav">
            <a href="#projects">Найти проект</a>
            <a href="#how-it-works">Как это работает</a>
            <a href="#talents">Специалисты</a>
            <Button className="primary-action">Разместить проект</Button>
          </nav>
        )}
      </header>

      <main>
        <section className="welcome-section">
          <div className="shell welcome-grid">
            <div className="welcome-copy">
              <span className="eyebrow"><Sparkles /> Возможности рядом</span>
              <h1>Найдите проект,<br />который <em>вдохновляет.</em></h1>
              <p>Свежие задачи от проверенных заказчиков — под ваш опыт, темп и амбиции.</p>
              <div className="hero-search" role="search">
                <Search aria-hidden="true" />
                <Input
                  aria-label="Поиск проектов"
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Навык, должность или ключевое слово"
                  value={query}
                />
                <Button className="primary-action" onClick={() => document.querySelector('#projects')?.scrollIntoView({ behavior: 'smooth' })}>
                  Найти
                </Button>
              </div>
              <p className="popular-searches"><span>Популярное:</span> React · Web design · Копирайтинг</p>
            </div>

            <div aria-label="Статистика платформы" className="hero-visual">
              <div className="visual-orbit orbit-one" />
              <div className="visual-orbit orbit-two" />
              <div className="hero-card hero-card-main">
                <div className="hero-icon-wrap"><Target /></div>
                <span>Подобрано для вас</span>
                <strong>24 проекта</strong>
                <div className="match-row">
                  <div className="avatar-stack" aria-hidden="true"><i>AK</i><i>MS</i><i>+</i></div>
                  <small>Совпадение от 86%</small>
                </div>
              </div>
              <div className="hero-card floating-card top-card"><Star fill="currentColor" /><span><strong>4.9</strong> рейтинг</span></div>
              <div className="hero-card floating-card bottom-card"><div className="pulse-dot" /><span><strong>128</strong> новых сегодня</span></div>
            </div>
          </div>
        </section>

        <section className="project-section" id="projects">
          <div className="shell content-grid">
            <div className="projects-column">
              <div className="section-heading">
                <div>
                  <span className="status-line">
                    <span className={apiState === 'connected' ? 'status-dot online' : 'status-dot'} />
                    {apiState === 'connected' ? 'Данные из PostgreSQL' : 'Актуальные проекты'}
                  </span>
                  <h2>Проекты для вас</h2>
                  <p>Подборка обновляется по мере появления новых задач</p>
                </div>
                <Button className="filter-button" variant="outline"><SlidersHorizontal /> Фильтры</Button>
              </div>

              <div className="category-tabs" role="tablist" aria-label="Категории проектов">
                {categories.map(({ value, label, icon: Icon }) => (
                  <button
                    aria-selected={category === value}
                    className={category === value ? 'category-tab active' : 'category-tab'}
                    key={value}
                    onClick={() => setCategory(value)}
                    role="tab"
                    type="button"
                  >
                    <Icon /> {label}
                  </button>
                ))}
              </div>

              <div className="project-list">
                {filteredProjects.map((project) => (
                  <ProjectCard key={project.id} onSave={toggleSaved} project={project} saved={saved.has(project.id)} />
                ))}
                {!filteredProjects.length && (
                  <div className="empty-state">
                    <Search /><h3>Ничего не найдено</h3>
                    <p>Попробуйте изменить запрос или выбрать другую категорию.</p>
                    <Button onClick={() => { setQuery(''); setCategory('all'); }} variant="outline">Сбросить фильтры</Button>
                  </div>
                )}
              </div>

              <Button className="load-more" variant="outline">Показать больше проектов <ChevronRight /></Button>
            </div>

            <aside className="dashboard-sidebar">
              <div className="side-card profile-card">
                <div className="profile-topline">
                  <div className="profile-avatar">АЗ</div>
                  <div><strong>Азиза Юлдашева</strong><span>Frontend-разработчик</span></div>
                  <Button aria-label="Открыть профиль" size="icon" variant="ghost"><ArrowUpRight /></Button>
                </div>
                <div className="progress-heading"><span>Профиль заполнен</span><strong>78%</strong></div>
                <div className="progress-track"><span /></div>
                <p>Добавьте 2 проекта в портфолио, чтобы получать больше приглашений.</p>
                <Button className="w-full" variant="outline">Улучшить профиль</Button>
              </div>

              <div className="side-card activity-card">
                <div className="side-title">
                  <div><span>На этой неделе</span><h3>Ваша активность</h3></div><TrendingUp />
                </div>
                <div className="activity-grid">
                  <div><BriefcaseBusiness /><strong>12</strong><span>Просмотров</span></div>
                  <div><MessageCircle /><strong>4</strong><span>Отклика</span></div>
                  <div><CircleDollarSign /><strong>$640</strong><span>Заработано</span></div>
                </div>
              </div>

              <div className="tip-card">
                <div className="tip-icon"><Sparkles /></div>
                <div><strong>Совет дня</strong><p>Персональный отклик получает ответ в 2,4 раза чаще.</p></div>
                <Check />
              </div>
            </aside>
          </div>
        </section>
      </main>
    </div>
  );
}
