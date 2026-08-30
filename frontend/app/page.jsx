'use client';

import Link from 'next/link';
import { ArrowRight, BarChart3, CheckCircle2, Code2, Languages, Megaphone, Moon, Palette, PenTool, ShieldCheck, Sparkles, Sun, Users, Video, WandSparkles } from 'lucide-react';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';

const text = {
  uz: {
    nav: ['Bosh sahifa', 'Qanday ishlaydi', 'Yo‘nalishlar', 'Biz haqimizda'], login: 'Kirish', start: 'Boshlash',
    eyebrow: 'O‘zbekistonning ishonchli freelance platformasi', hero1: 'Frilanser topish hech qachon', hero2: 'bu qadar oson bo‘lmagan',
    heroText: 'Ishonchli mutaxassislarni toping yoki o‘z mahoratingiz bilan daromad oling. Hammasi bir joyda — tez, xavfsiz va qulay.',
    findTalent: 'Mutaxassis topish', findWork: 'Ish topish', projects: 'muvaffaqiyatli loyiha', freelancers: 'malakali frilanser', satisfaction: 'mijozlar mamnunligi',
    trusted: 'Ishonchli platforma.', trusted2: 'Frilanserlar va mijozlar uchun O‘zbekiston bozori uchun yaratilgan.',
    secureTitle: 'To‘liq xavfsiz va ishonchli', secureText: 'Har bir bosqichda mablag‘ va ma’lumotlaringiz himoyalangan.',
    features: [['Xavfsiz to‘lov', 'To‘lov faqat ishni qabul qilganingizdan so‘ng ijrochiga o‘tadi.'], ['Tekshirilgan profillar', 'Reytinglar, portfolio va tasdiqlangan ma’lumotlar to‘g‘ri tanlovga yordam beradi.'], ['Doimiy yordam', 'Taskora jamoasi savollaringizga tezkor javob beradi.']],
    how: '3 qadamda boshlang', howSub: 'Loyihangizni amalga oshirish oson', steps: [['01', 'Vazifani joylang', 'Talab va byudjetni bir necha daqiqada kiriting.'], ['02', 'Takliflarni tanlang', 'Portfolio va reytingni solishtirib, mos ijrochini toping.'], ['03', 'Natijani oling', 'Xavfsiz to‘lov orqali ishni qabul qiling.']],
    categories: 'AI tomonidan tanlab olingan yo‘nalishlar', categoriesSub: 'Eng talabgir mutaxassisliklarni ko‘rib chiqing',
    categoryNames: ['Dasturlash', 'UI/UX dizayn', 'Marketing', 'Matn yozish', 'Video montaj', 'SMM', 'Biznes tahlil', 'AI xizmatlari'],
    cta: 'Bugun boshlang', ctaText: 'G‘oyangizni tajribali mutaxassislar bilan haqiqatga aylantiring.', footer: 'O‘zbekistondagi freelancerlar va mijozlarni birlashtiruvchi platforma.', rights: 'Barcha huquqlar himoyalangan.',
  },
  ru: {
    nav: ['Главная', 'Как это работает', 'Направления', 'О нас'], login: 'Войти', start: 'Начать',
    eyebrow: 'Надёжная фриланс-платформа Узбекистана', hero1: 'Найти фрилансера ещё никогда', hero2: 'не было так просто',
    heroText: 'Находите проверенных специалистов или зарабатывайте на своих навыках. Всё в одном месте — быстро, безопасно и удобно.',
    findTalent: 'Найти специалиста', findWork: 'Найти работу', projects: 'успешных проектов', freelancers: 'проверенных фрилансеров', satisfaction: 'довольных клиентов',
    trusted: 'Платформа доверия.', trusted2: 'Создана для фрилансеров и заказчиков с учётом рынка Узбекистана.',
    secureTitle: 'Безопасность и доверие', secureText: 'Ваши данные и оплата защищены на каждом этапе работы.',
    features: [['Безопасная оплата', 'Исполнитель получает оплату только после принятия результата.'], ['Проверенные профили', 'Рейтинги, портфолио и подтверждённые данные помогают сделать выбор.'], ['Поддержка рядом', 'Команда Taskora оперативно поможет с любым вопросом.']],
    how: 'Начните за 3 шага', howSub: 'Запустить проект действительно просто', steps: [['01', 'Опубликуйте задачу', 'Опишите требования и бюджет за несколько минут.'], ['02', 'Выберите предложение', 'Сравните портфолио и рейтинги исполнителей.'], ['03', 'Получите результат', 'Примите работу через безопасную оплату.']],
    categories: 'Направления, подобранные AI', categoriesSub: 'Откройте самые востребованные специальности',
    categoryNames: ['Разработка', 'UI/UX дизайн', 'Маркетинг', 'Копирайтинг', 'Видеомонтаж', 'SMM', 'Бизнес-анализ', 'AI-услуги'],
    cta: 'Начните сегодня', ctaText: 'Воплотите идею в жизнь вместе с опытными специалистами.', footer: 'Платформа, объединяющая фрилансеров и заказчиков Узбекистана.', rights: 'Все права защищены.',
  },
};

const categoryIcons = [Code2, Palette, Megaphone, PenTool, Video, Users, BarChart3, WandSparkles];

export default function LandingPage() {
  const { language, setLanguage } = useApp(); const t = text[language]; const [dark, setDark] = useState(false);
  return <div className={`figma-site ${dark ? 'figma-dark' : ''}`}>
    <header className="figma-header"><div className="figma-shell figma-header-inner"><Logo />
      <nav>{t.nav.map((item, i) => <a key={item} href={['#top', '#how', '#categories', '#about'][i]}>{item}</a>)}</nav>
      <div className="figma-header-actions"><button className="figma-icon-button" onClick={() => setLanguage(language === 'uz' ? 'ru' : 'uz')} aria-label="Til / Язык"><Languages /> <span>{language.toUpperCase()}</span></button><button className="figma-icon-button only-icon" onClick={() => setDark(!dark)} aria-label={dark ? 'Light theme' : 'Dark theme'}>{dark ? <Sun /> : <Moon />}</button><Link className="figma-login" href="/login">{t.login}</Link><Link className="figma-button small" href="/register">{t.start}</Link></div>
    </div></header>
    <main id="top">
      <section className="figma-hero"><div className="figma-shell"><div className="figma-kicker"><Sparkles />{t.eyebrow}</div><h1>{t.hero1}<br/><em>{t.hero2}</em></h1><p>{t.heroText}</p><div className="figma-hero-actions"><Link className="figma-button" href="/register">{t.findTalent}<ArrowRight /></Link><Link className="figma-button secondary" href="/register">{t.findWork}</Link></div><div className="figma-stats"><div><b>12 000+</b><span>{t.projects}</span></div><div><b>4 500+</b><span>{t.freelancers}</span></div><div><b>96%</b><span>{t.satisfaction}</span></div></div></div></section>
      <section className="figma-trust" id="about"><div className="figma-trust-mark"><ShieldCheck /></div><h2>{t.trusted}<br/>{t.trusted2}</h2></section>
      <section className="figma-section"><div className="figma-shell"><div className="figma-section-heading"><span>TASKORA PLATFORMASI</span><h2>{t.secureTitle}</h2><p>{t.secureText}</p></div><div className="figma-feature-grid">{t.features.map((feature, i) => <article key={feature[0]}><span>0{i + 1}</span><CheckCircle2 /><h3>{feature[0]}</h3><p>{feature[1]}</p></article>)}</div></div></section>
      <section className="figma-section figma-steps-section" id="how"><div className="figma-shell"><div className="figma-section-heading"><span>QANDAY ISHLAYDI</span><h2>{t.how}</h2><p>{t.howSub}</p></div><div className="figma-steps">{t.steps.map((step) => <article key={step[0]}><b>{step[0]}</b><h3>{step[1]}</h3><p>{step[2]}</p></article>)}</div></div></section>
      <section className="figma-section" id="categories"><div className="figma-shell"><div className="figma-section-heading"><span>TOP YO‘NALISHLAR</span><h2>{t.categories}</h2><p>{t.categoriesSub}</p></div><div className="figma-category-grid">{t.categoryNames.map((name, i) => { const Icon = categoryIcons[i]; return <Link key={name} href={`/dashboard?category=${i}`}><Icon/><h3>{name}</h3><span>120+ {language === 'uz' ? 'mutaxassis' : 'специалистов'}</span><ArrowRight/></Link>; })}</div></div></section>
      <section className="figma-shell figma-cta"><div><span>TASKORA BILAN</span><h2>{t.cta}</h2><p>{t.ctaText}</p></div><Link className="figma-button white" href="/register">{t.start}<ArrowRight/></Link></section>
    </main>
    <footer className="figma-footer"><div className="figma-shell"><div><Logo/><p>{t.footer}</p></div><div><b>Platforma</b><a href="#how">{t.nav[1]}</a><a href="#categories">{t.nav[2]}</a></div><div><b>Hisob / Аккаунт</b><Link href="/login">{t.login}</Link><Link href="/register">{t.start}</Link></div></div><p className="figma-copy">© 2026 Taskora. {t.rights}</p></footer>
  </div>;
}

function Logo() { return <Link className="figma-logo" href="/"><span><i/><i/><i/><i/><i/><i/><i/><i/></span>Taskora</Link>; }
