'use client';

import Link from 'next/link';
import { KeyRound, LockKeyhole, Mail } from 'lucide-react';
import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AuthShell, AuthBack, copy, PasswordInput } from '@/components/auth-shell';
import { useApp } from '@/components/app-providers';
import { confirmPasswordReset, requestPasswordReset, verifyPasswordReset } from '@/lib/api';

export default function ResetPasswordPage() {
  const { language, setSession } = useApp(); const router = useRouter(); const uz = language === 'uz';
  const [step, setStep] = useState(1), [email, setEmail] = useState(''), [code, setCode] = useState(Array(6).fill(''));
  const [token, setToken] = useState(''), [password, setPassword] = useState(''), [confirm, setConfirm] = useState('');
  const [error, setError] = useState(''), [loading, setLoading] = useState(false); const refs = useRef([]);
  const labels = [uz ? 'Parolni tiklash' : 'Восстановление пароля', uz ? 'Tasdiqlash kodi' : 'Код подтверждения', uz ? 'Yangi parol' : 'Новый пароль'];
  async function send(e) { e.preventDefault(); setLoading(true); setError(''); try { await requestPasswordReset(email); setStep(2); } catch (err) { setError(err.message); } finally { setLoading(false); } }
  async function verify(e) { e.preventDefault(); setLoading(true); setError(''); try { const data = await verifyPasswordReset(email, code.join('')); setToken(data.reset_token); setStep(3); } catch (err) { setError(err.message); } finally { setLoading(false); } }
  async function change(e) { e.preventDefault(); setLoading(true); setError(''); try { const data = await confirmPasswordReset({ email, reset_token: token, password, password_confirm: confirm }); setSession(data); router.replace('/'); } catch (err) { setError(err.message); } finally { setLoading(false); } }
  function digit(i, value) { if (!/^\d?$/.test(value)) return; const next = [...code]; next[i] = value; setCode(next); if (value && i < 5) refs.current[i + 1]?.focus(); }
  const Icon = step === 1 ? Mail : step === 2 ? LockKeyhole : KeyRound;
  return <AuthShell><AuthBack /><div className="reset-steps">{[1, 2, 3].map((n) => <span key={n} className={n <= step ? 'done' : ''}>{n < step ? '✓' : n}</span>)}</div><div className="reset-icon"><Icon /></div><h1 className="auth-centered">{labels[step - 1]}</h1>
    <p className="auth-subtitle auth-centered">{step === 1 ? (uz ? 'Email manzilingizni kiriting, kod yuboramiz' : 'Введите email — отправим код') : step === 2 ? (uz ? 'Emailga yuborilgan 6 xonali kodni kiriting' : 'Введите 6-значный код из письма') : (uz ? 'Hisobingiz uchun yangi xavfsiz parol tanlang' : 'Выберите новый надёжный пароль')}</p>
    {step === 1 && <form onSubmit={send} className="auth-form"><label>{copy[language].email}<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="example@taskora.uz" required /></label><ResetError error={error} /><button className="auth-primary" disabled={loading}>{loading ? '…' : (uz ? 'Kod yuborish' : 'Отправить код')}</button></form>}
    {step === 2 && <form onSubmit={verify} className="auth-form"><div className="code-inputs">{code.map((value, i) => <input key={i} ref={(el) => { refs.current[i] = el; }} value={value} inputMode="numeric" maxLength="1" onChange={(e) => digit(i, e.target.value)} />)}</div><ResetError error={error} /><button className="auth-primary" disabled={loading}>{loading ? '…' : (uz ? 'Tasdiqlash' : 'Подтвердить')}</button></form>}
    {step === 3 && <form onSubmit={change} className="auth-form"><label>{uz ? 'Yangi parol' : 'Новый пароль'}<PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" /></label><label>{copy[language].passwordAgain}<PasswordInput value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" /></label><ResetError error={error} /><button className="auth-primary" disabled={loading}>{loading ? '…' : (uz ? 'Parolni yangilash' : 'Обновить пароль')}</button></form>}
    <p className="auth-footer"><Link href="/login">← {uz ? 'Kirishga qaytish' : 'Вернуться ко входу'}</Link></p>
  </AuthShell>;
}

function ResetError({ error }) { return error ? <p className="auth-error">{error}</p> : null; }
