'use client';

import Link from 'next/link';
import { ArrowRight, BadgeCheck, Bot, BrainCircuit, LockKeyhole, ShieldCheck } from 'lucide-react';
import { useApp } from '@/components/app-providers';

const copy = {
  uz: {
    orders: 'Buyurtmalar', freelancers: 'Frilanserlar', login: 'Kirish', language: 'RU',
    heroA: 'Frilanser topish hech qachon', heroB: 'bu qadar', heroC: "oson bo‘lmagan",
    heroText: "ONEID orqali tasdiqlangan mutaxassislar. AI tavsiyasi.\nXavfsiz escrow to‘lov tizimi.",
    register: "Ro‘yxatdan o‘tish", about: 'Platforma haqida',
    statFreelancers: 'Frilanser', statProjects: 'Loyiha', statSuccess: 'Muvaffaqiyat',
    trust: "Ishonchli platforma.\nFrilanserlar va mijozlar uchun.\nO‘zbekiston bozori uchun yaratilgan.",
    secure: 'To‘liq xavfsiz va ishonchli', secureSub: 'Zamonaviy texnologiyalar bilan himoyalangan va AI bilan kuchaytirilgan tizim',
    features: [
      ['Xavfsiz Escrow', "To‘lovlar to‘liq xavfsizlikda saqlanadi va ish tugatilgach frilanserga o‘tkaziladi."],
      ['AI Tavsiyalar', 'Sun’iy intellekt sizning loyihangizga eng mos mutaxassislarni tavsiya qiladi.'],
      ['ONEID Tasdiqlash', 'Barcha foydalanuvchilar ONEID orqali tasdiqlangan, bu ishonchlilikni kafolatlaydi.'],
    ],
    stepsTitle: '3 qadamda boshlang', stepsSub: 'Taskorada ishlash jarayoni oddiy va tushunarli',
    steps: [
      ["Ro‘yxatdan o‘ting", 'Shaxsiy hisobingizni yarating va profilingizni to‘ldiring.'],
      ['Loyihani joylang', 'Talablaringizni yozing va AI sizga mos frilanserlarni topadi.'],
      ['Natijani oling', 'Ishni qabul qiling va to‘lovni tasdiqlang.'],
    ],
    top: 'TOP FRILANSERLAR', recommended: 'AI tomonidan tavsiya etilgan',
    cta: 'Bugun boshlang', ctaText: 'O‘zbekistondagi eng kuchli mutaxassislar bilan ishlashni hoziroq boshlang va o‘z g‘oyalaringizni rivojlantiring.',
    footerText: 'O‘zbekistondagi frilanserlar va mijozlarni birlashtiruvchi ishonchli platforma.', rights: 'Barcha huquqlar himoyalangan.',
  },
  ru: {
    orders: 'Заказы', freelancers: 'Фрилансеры', login: 'Войти', language: 'UZ',
    heroA: 'Найти фрилансера ещё никогда', heroB: 'не было', heroC: 'так просто',
    heroText: 'Специалисты, подтверждённые через ONEID. Рекомендации AI.\nБезопасная escrow-система оплаты.',
    register: 'Зарегистрироваться', about: 'О платформе',
    statFreelancers: 'Фрилансеров', statProjects: 'Проектов', statSuccess: 'Успешно',
    trust: 'Надёжная платформа.\nДля фрилансеров и заказчиков.\nСоздана для рынка Узбекистана.',
    secure: 'Полностью безопасно и надёжно', secureSub: 'Защищённая современными технологиями и усиленная искусственным интеллектом система',
    features: [
      ['Безопасный Escrow', 'Оплата хранится в безопасности и переводится фрилансеру после завершения работы.'],
      ['AI-рекомендации', 'Искусственный интеллект рекомендует лучших специалистов для вашего проекта.'],
      ['Подтверждение ONEID', 'Пользователи подтверждаются через ONEID, что гарантирует надёжность.'],
    ],
    stepsTitle: 'Начните за 3 шага', stepsSub: 'Работать в Taskora просто и понятно',
    steps: [
      ['Зарегистрируйтесь', 'Создайте личный аккаунт и заполните профиль.'],
      ['Разместите проект', 'Опишите требования, и AI найдёт подходящих фрилансеров.'],
      ['Получите результат', 'Примите работу и подтвердите оплату.'],
    ],
    top: 'ТОП ФРИЛАНСЕРЫ', recommended: 'Рекомендованы искусственным интеллектом',
    cta: 'Начните сегодня', ctaText: 'Начните работать с сильнейшими специалистами Узбекистана и развивайте свои идеи.',
    footerText: 'Надёжная платформа, объединяющая фрилансеров и заказчиков Узбекистана.', rights: 'Все права защищены.',
  },
};

export default function LandingPage() {
  const { language, setLanguage } = useApp();
  const t = copy[language];
  return <div className="figma-site startup-page">
    <header className="startup-header"><div className="startup-shell startup-header-inner"><Logo /><nav><Link href="/dashboard?view=orders">{t.orders}</Link><a href="#freelancers">{t.freelancers}</a><button onClick={() => setLanguage(language === 'uz' ? 'ru' : 'uz')}>{t.language}</button><Link className="startup-login" href="/login">{t.login}<ArrowRight /></Link></nav></div></header>
    <main>
      <section className="startup-hero"><div className="startup-shell"><h1><span>{t.heroA}</span><span>{t.heroB}</span><em>{t.heroC}</em></h1><p>{t.heroText}</p><div className="startup-hero-actions"><Link href="/register">{t.register}<ArrowRight /></Link><a href="#about">{t.about}<ArrowRight /></a></div><div className="startup-stats"><span><b>0</b> {t.statFreelancers}</span><span><b>0</b> {t.statProjects}</span><span><b>0%</b> {t.statSuccess}</span></div></div></section>
      <section className="startup-trust" id="about"><ShieldCheck /><h2>{t.trust}</h2></section>
      <section className="startup-security"><div className="startup-shell"><div className="startup-section-title"><h2>{t.secure}</h2><p>{t.secureSub}</p></div><div className="startup-feature-grid">{t.features.map(([title, description], index) => { const Icon = [LockKeyhole, BrainCircuit, BadgeCheck][index]; return <article key={title}><span><Icon /></span><h3>{title}</h3><p>{description}</p></article>; })}</div></div></section>
      <section className="startup-steps"><div className="startup-shell"><div className="startup-section-title"><h2>{t.stepsTitle}</h2><p>{t.stepsSub}</p></div><div className="startup-step-grid">{t.steps.map(([title, description], index) => <article key={title}><b>0{index + 1}</b><h3>{title}</h3><p>{description}</p></article>)}</div></div></section>
      <section className="startup-cta-section"><div className="startup-shell startup-cta"><Bot /><h2>{t.cta}</h2><p>{t.ctaText}</p><div><Link href="/register">{t.register}<ArrowRight /></Link><Link href="/login">{t.login}<ArrowRight /></Link></div></div></section>
    </main>
    <footer className="startup-footer"><div className="startup-shell"><div><Logo /><p>{t.footerText}</p></div><nav><b>Platforma</b><a href="#about">{t.about}</a><a href="#freelancers">{t.freelancers}</a></nav><nav><b>Hisob / Аккаунт</b><Link href="/login">{t.login}</Link><Link href="/register">{t.register}</Link></nav></div><p className="startup-copy">© 2026 Taskora. {t.rights}</p></footer>
  </div>;
}

function Logo() {
  return <Link className="startup-logo" href="/"><span className="startup-logo-mark">{Array.from({ length: 9 }, (_, index) => <i key={index} />)}</span><span><b>Taskora</b><small>Work with Confidence</small></span></Link>;
}
