'use client';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { apiRequest, getCurrentUser } from '@/lib/api';
import { languages, translate } from '@/lib/i18n';
const AppContext = createContext(null);
const validLanguage = (value) => languages.some(([key]) => key === value);

export function AppProviders({ children }) {
  const [language, setLanguageState] = useState('ru');
  const [theme, setThemeState] = useState('dark');
  const [session, setSessionState] = useState(null);
  const [ready, setReady] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const updateUser = useCallback((user) => {
    setSessionState((current) => (current ? { ...current, user } : current));
    if (validLanguage(user.language)) setLanguageState(user.language);
    if (['light', 'dark'].includes(user.theme)) setThemeState(user.theme);
  }, []);
  const clearSession = useCallback(() => {
    localStorage.removeItem('taskora-token');
    localStorage.removeItem('taskora-user');
    setSessionState(null);
  }, []);
  const refreshSession = useCallback(async () => {
    const token = localStorage.getItem('taskora-token');
    if (!token) {
      setReady(true);
      return;
    }
    setConnectionError('');
    try {
      const user = await getCurrentUser(token);
      setSessionState({ token, user });
      if (validLanguage(user.language)) setLanguageState(user.language);
      setThemeState(user.theme || 'dark');
    } catch (error) {
      if (error.status === 401) clearSession();
      else setConnectionError(error.message);
    } finally {
      setReady(true);
    }
  }, [clearSession]);
  useEffect(() => {
    void Promise.resolve().then(() => {
      const storedLanguage = localStorage.getItem('taskora-language');
      if (validLanguage(storedLanguage)) setLanguageState(storedLanguage);
      const storedTheme = localStorage.getItem('taskora-theme');
      if (['light', 'dark'].includes(storedTheme)) setThemeState(storedTheme);
      void refreshSession();
    });
  }, [refreshSession]);
  useEffect(() => {
    if (ready) {
      localStorage.setItem('taskora-language', language);
      document.documentElement.lang =
        language === 'uz-cyrl' ? 'uz-Cyrl' : language;
    }
  }, [language, ready]);
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    if (ready) localStorage.setItem('taskora-theme', theme);
  }, [theme, ready]);
  useEffect(() => {
    if (!ready || connectionError) return;
    const path = window.location.pathname;
    const protectedPath =
      path === '/role' ||
      path === '/dashboard' ||
      path === '/projects/new' ||
      path.startsWith('/contracts/');
    if (!session?.token && protectedPath) {
      window.location.replace('/login');
      return;
    }
    if (!session?.token) return;
    if (!session.user?.role && protectedPath && path !== '/role') {
      window.location.replace('/role');
      return;
    }
    if (
      path === '/login' ||
      path === '/register' ||
      path === '/reset-password' ||
      (path === '/role' && session.user?.role)
    )
      window.location.replace(session.user?.role ? '/dashboard' : '/role');
  }, [ready, session, connectionError]);
  // Full navigation is used by the existing Vinext project for stable dynamic routes.
  useEffect(() => {
    function navigate(event) {
      if (
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey ||
        !(event.target instanceof Element)
      )
        return;
      const anchor = event.target.closest('a[href]');
      if (
        !anchor ||
        anchor.target === '_blank' ||
        anchor.hasAttribute('download')
      )
        return;
      const href = anchor.getAttribute('href');
      if (!href || href.startsWith('#')) return;
      const url = new URL(href, window.location.href);
      if (
        url.origin !== window.location.origin ||
        !['http:', 'https:'].includes(url.protocol)
      )
        return;
      event.preventDefault();
      window.location.assign(url.href);
    }
    document.addEventListener('click', navigate, true);
    return () => document.removeEventListener('click', navigate, true);
  }, []);
  const setSession = useCallback(({ token, user }) => {
    localStorage.setItem('taskora-token', token);
    localStorage.removeItem('taskora-user');
    setSessionState({ token, user });
    if (validLanguage(user.language)) setLanguageState(user.language);
    setThemeState(user.theme || 'light');
  }, []);
  function preference(key, value) {
    if (key === 'language') setLanguageState(value);
    else setThemeState(value);
    if (session?.token)
      apiRequest('auth/me', {
        method: 'PATCH',
        token: session.token,
        body: { [key]: value },
      })
        .then(updateUser)
        .catch((error) => setConnectionError(error.message));
  }
  const value = {
    language,
    theme,
    setLanguage: (v) => preference('language', v),
    setTheme: (v) => preference('theme', v),
    session,
    ready,
    setSession,
    updateUser,
    clearSession,
    refreshSession,
    t: (key) => translate(language, key),
  };
  return (
    <AppContext.Provider value={value}>
      {connectionError && (
        <div className="connection-error" role="alert">
          {translate(language, 'error')}: {connectionError}{' '}
          <button onClick={refreshSession}>
            {translate(language, 'retry')}
          </button>
        </div>
      )}
      {children}
    </AppContext.Provider>
  );
}
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error('AppProviders required');
  return value;
}
