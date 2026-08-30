'use client';

import { BriefcaseBusiness, ClipboardList, LockKeyhole } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { AuthShell, copy } from '@/components/auth-shell';
import { useApp } from '@/components/app-providers';
import { setRole } from '@/lib/api';

export default function RolePage() {
  const { language, session, updateUser } = useApp();
  const router = useRouter();
  const [role, setChosen] = useState(session?.user?.role || 'freelancer');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const uz = language === 'uz';
  async function submit() {
    if (!session?.token) { router.replace('/login'); return; }
    setLoading(true); setError('');
    try { const user = await setRole(role, session.token); updateUser(user); router.replace('/'); }
    catch (err) { setError(err.message); } finally { setLoading(false); }
  }
  return <AuthShell wide>
    <h1 className="auth-centered">{uz ? 'Siz kim sifatida kiryapsiz?' : 'Как вы будете пользоваться платформой?'}</h1>
    <p className="auth-subtitle auth-centered">{uz ? "Keyinchalik ham o'zgartirish mumkin" : 'Роль можно изменить позже'}</p>
    <div className="role-grid">
      <button type="button" onClick={() => setChosen('freelancer')} className={`role-card ${role === 'freelancer' ? 'selected' : ''}`}><BriefcaseBusiness /><strong>{uz ? 'Frilanser' : 'Фрилансер'}</strong><small>JUNIOR　MIDDLE　SENIOR</small></button>
      <button type="button" onClick={() => setChosen('client')} className={`role-card ${role === 'client' ? 'selected' : ''}`}><ClipboardList /><strong>{uz ? 'Buyurtmachi' : 'Заказчик'}</strong><small>{uz ? 'Verifikatsiya bepul' : 'Бесплатная верификация'}</small></button>
    </div>
    {error && <p className="auth-error">{error}</p>}
    <button className="auth-primary" onClick={submit} disabled={loading}>{loading ? '…' : `${copy[language].next} →`}</button>
    <p className="role-safe"><LockKeyhole size={14} />{uz ? "Ma'lumotlaringiz himoyalangan" : 'Ваши данные защищены'}</p>
  </AuthShell>;
}
