'use client';

import Link from 'next/link';
import { Eye, EyeOff, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';

export const copy = {
  uz: {
    back: 'Orqaga', email: 'Email', password: 'Parol', passwordAgain: 'Parolni tasdiqlang',
    next: 'Davom etish', login: 'Kirish', register: "Ro'yxatdan o'tish", or: 'yoki',
    oneid: 'OneID — keyingi yangilanishlarda', coming: 'Tez kunda', noAccount: "Hisob yo'qmi?", hasAccount: 'Hisobingiz bormi?',
    fullName: 'Ism Familya', terms: 'Foydalanish shartlariga roziman', show: 'Parolni ko‘rsatish', hide: 'Parolni yashirish',
  },
  ru: {
    back: 'Назад', email: 'Email', password: 'Пароль', passwordAgain: 'Подтвердите пароль',
    next: 'Продолжить', login: 'Войти', register: 'Зарегистрироваться', or: 'или', oneid: 'OneID — в следующих обновлениях',
    coming: 'Скоро', noAccount: 'Нет аккаунта?', hasAccount: 'Уже есть аккаунт?', fullName: 'Имя и фамилия',
    terms: 'Согласен с условиями использования', show: 'Показать пароль', hide: 'Скрыть пароль',
  },
};

export function AuthShell({ children, wide = false }) {
  const { language, setLanguage } = useApp();
  return <main className="auth-page"><fieldset className="auth-language" aria-label="Language">
    {['uz', 'ru'].map((item) => <button key={item} className={language === item ? 'active' : ''} onClick={() => setLanguage(item)}>{item.toUpperCase()}</button>)}
  </fieldset><section className={`auth-card ${wide ? 'auth-card-wide' : ''}`}>{children}</section></main>;
}

export function PasswordInput({ value, onChange, placeholder, autoComplete = 'current-password' }) {
  const { language } = useApp(); const t = copy[language]; const [visible, setVisible] = useState(false);
  return <div className="password-input"><input type={visible ? 'text' : 'password'} value={value} onChange={onChange} placeholder={placeholder} autoComplete={autoComplete} required />
    <button type="button" onClick={() => setVisible(!visible)} aria-label={visible ? t.hide : t.show}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>;
}

export function OneIdDisabled() {
  const { language } = useApp(); const t = copy[language];
  return <button type="button" className="oneid-disabled" disabled title={t.coming}><ShieldCheck size={18} /> {t.oneid}<span>{t.coming}</span></button>;
}

export function AuthBack() { const { language } = useApp(); return <Link className="auth-back" href="/login">← {copy[language].back}</Link>; }
