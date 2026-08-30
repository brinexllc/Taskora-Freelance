'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { getCurrentUser } from '@/lib/api';

const AppContext = createContext(null);

export function AppProviders({ children }) {
  const [language, setLanguage] = useState('uz');
  const [session, setSessionState] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => { void Promise.resolve().then(() => {
    const storedLanguage = localStorage.getItem('taskora-language');
    if (storedLanguage === 'ru' || storedLanguage === 'uz') setLanguage(storedLanguage);
    const token = localStorage.getItem('taskora-token');
    const storedUser = localStorage.getItem('taskora-user');
    if (!token) { setReady(true); return; }
    setSessionState({ token, user: storedUser ? JSON.parse(storedUser) : null });
    getCurrentUser(token).then((user) => setSessionState({ token, user })).catch(() => {
      localStorage.removeItem('taskora-token'); localStorage.removeItem('taskora-user'); setSessionState(null);
    }).finally(() => setReady(true));
  }); }, []);

  useEffect(() => { if (!ready) return; localStorage.setItem('taskora-language', language); document.documentElement.lang = language; }, [language, ready]);

  useEffect(() => {
    function navigateInternalLink(event) {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (!(event.target instanceof Element)) return;
      const anchor = event.target.closest('a[href]');
      if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
      const href = anchor.getAttribute('href');
      if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return;
      const destination = new URL(href, window.location.href);
      if (destination.origin !== window.location.origin) return;
      event.preventDefault();
      window.location.assign(destination.href);
    }

    document.addEventListener('click', navigateInternalLink, true);
    return () => document.removeEventListener('click', navigateInternalLink, true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const path = window.location.pathname;
    if (!session?.token && path === '/role') {
      window.location.replace('/login');
      return;
    }
    if (!session?.token) return;
    if (path === '/login' || path === '/register') {
      window.location.replace(session.user?.role ? '/dashboard' : '/role');
      return;
    }
    if (path === '/reset-password' || (path === '/role' && session.user?.role)) {
      window.location.replace('/dashboard');
    }
  }, [ready, session]);

  const setSession = ({ token, user }) => {
    localStorage.setItem('taskora-token', token); localStorage.setItem('taskora-user', JSON.stringify(user)); setSessionState({ token, user });
  };
  const updateUser = (user) => { setSessionState((value) => ({ ...value, user })); localStorage.setItem('taskora-user', JSON.stringify(user)); };
  const clearSession = () => { localStorage.removeItem('taskora-token'); localStorage.removeItem('taskora-user'); setSessionState(null); };
  const value = { language, setLanguage, session, ready, setSession, updateUser, clearSession };
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error('useApp must be used inside AppProviders');
  return context;
}
