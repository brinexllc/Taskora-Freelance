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

  useEffect(() => { localStorage.setItem('taskora-language', language); document.documentElement.lang = language; }, [language]);
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
