/* Progressive enhancement for the server-owned admin workflows. */
(() => {
  'use strict';
  const csrf = () => document.querySelector('input[name=csrfmiddlewaretoken]')?.value || '';
  const errorText = value => typeof value === 'string' ? value : value?.detail ? errorText(value.detail) : Object.values(value || {}).map(errorText).join(' ');
  let confirmedUntil = 0;
  let pendingForm = null;
  document.addEventListener('close', event => {
    if (event.target.id === 'ta-security-dialog') pendingForm = null;
  }, true);
  // A followed POST redirect consumes Django's one-use messages in fetch.
  // Carry only escaped presentation text into the ensuing full navigation.
  try {
    const notices = JSON.parse(sessionStorage.getItem('ta-operation-notices') || '[]');
    sessionStorage.removeItem('ta-operation-notices');
    if (notices.length && !document.querySelector('.messagelist')) {
      const list = document.createElement('ul'); list.className='messagelist'; list.setAttribute('role','status');
      notices.forEach(text => {const item=document.createElement('li');item.className='success';item.textContent=text;list.appendChild(item);});
      document.querySelector('#content')?.prepend(list);
    }
  } catch { /* Storage is optional; server workflows continue without it. */ }
  async function api(path, body) {
    const response = await fetch('/api/' + path + '/', {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(body)});
    const data = await response.json();
    if (data.code === 'API_UNAVAILABLE') throw new Error('Сервер временно недоступен. Проверьте соединение и повторите подтверждение.');
    if (!response.ok) throw new Error(errorText(data) || 'Действие не выполнено.');
    if (data.csrf_token) document.querySelectorAll('input[name=csrfmiddlewaretoken]').forEach(input => { input.value=data.csrf_token; });
    return data;
  }
  document.addEventListener('click', event => {
    const target = event.target.closest('button,a');
    if (!target) return;
    if (target.id === 'ta-menu') {
      const open = document.getElementById('ta-sidebar')?.classList.toggle('open');
      target.setAttribute('aria-expanded', String(Boolean(open)));
    }
    if (target.id === 'ta-theme') {
      const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      if (window.setTheme) window.setTheme(theme); else {document.documentElement.dataset.theme=theme;localStorage.setItem('theme',theme);}
    }
    if (target.hasAttribute('data-security-dialog')) document.getElementById('ta-security-dialog')?.showModal();
    if (target.hasAttribute('data-close-dialog')) document.getElementById('ta-security-dialog')?.close();
  });
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '')) {event.preventDefault();document.querySelector('.ta-global-search input')?.focus();}
    if (event.key === 'Escape') {document.getElementById('ta-sidebar')?.classList.remove('open');document.getElementById('ta-menu')?.setAttribute('aria-expanded','false');}
  });
  document.addEventListener('click', event => {
    if (window.innerWidth <= 760 && !event.target.closest('.ta-sidebar,#ta-menu')) {document.getElementById('ta-sidebar')?.classList.remove('open');document.getElementById('ta-menu')?.setAttribute('aria-expanded','false');}
  });
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (form.matches('.ta-security-form')) {
      event.preventDefault();
      const status = form.querySelector('.ta-security-status');
      const button = form.querySelector('button[type=submit]');
      button.disabled=true;status.textContent='Проверяем…';
      try {
        const confirmation = await api('auth/confirm-sensitive',Object.fromEntries(new FormData(form)));
        confirmedUntil = Date.now() / 1000 + Number(confirmation.expires_in || 300);
        status.textContent='Безопасность подтверждена. Можно продолжить действие.';
        form.querySelector('[name=password]').value='';form.querySelector('[name=code]').value='';
        const resume = pendingForm;
        pendingForm = null;
        document.getElementById('ta-security-dialog')?.close();
        if (resume?.isConnected) resume.requestSubmit();
      } catch(error) {status.textContent=error.message || 'Не удалось подтвердить безопасность.';}
      finally {button.disabled=false;}
    }
    if (form.id === 'ta-admin-login') {
      event.preventDefault();
      const status = document.getElementById('ta-login-status');
      const button = form.querySelector('button[type=submit]');
      button.disabled=true;status.textContent='Проверяем доступ…';
      try {
        const data=await api('auth/login',Object.fromEntries(new FormData(form)));
        const user=data.user || data;
        if (!user.is_staff || !user.is_superuser) throw new Error('Доступ разрешён только администратору платформы.');
        if (user.mfa_enabled === false) {window.location.assign('/dashboard?view=settings');return;}
        window.location.assign('/admin/');
      } catch(error) {status.textContent=error.message || 'Не удалось войти. Проверьте соединение.';button.disabled=false;}
    }
    if (form.matches('.ta-operation-form[data-preserve-draft]')) {
      event.preventDefault();
      const until = Math.max(confirmedUntil, Number(form.dataset.confirmationUntil || 0));
      if (form.hasAttribute('data-confirmation-required') && Date.now() / 1000 >= until) {
        const dialog = document.getElementById('ta-security-dialog');
        if (dialog) { pendingForm = form; dialog.showModal(); return; }
      }
      const button = form.querySelector('button[type=submit]');
      const status = form.querySelector('.ta-submit-status');
      const body = new FormData(form);
      button.disabled=true;if(status){status.classList.remove('error');status.textContent='Проверяем и сохраняем действие…';}
      try {
        const response=await fetch(form.action || window.location.href,{method:'POST',body,credentials:'same-origin',headers:{'X-Request-ID':crypto.randomUUID()}});
        if (response.redirected) {
          try {const page=new DOMParser().parseFromString(await response.text(),'text/html');const notices=Array.from(page.querySelectorAll('.messagelist li')).map(item=>item.textContent.trim());if(notices.length)sessionStorage.setItem('ta-operation-notices',JSON.stringify(notices));} catch { /* Navigation remains available. */ }
          window.location.assign(response.url);return;
        }
        if (response.headers.get('content-disposition')?.includes('attachment')) {
          const blob=await response.blob();const link=document.createElement('a');link.href=URL.createObjectURL(blob);const name=response.headers.get('content-disposition')?.match(/filename="?([^";]+)/)?.[1];link.download=(name || 'taskora-download').replace(/[\\/]/g,'_');link.click();setTimeout(()=>URL.revokeObjectURL(link.href),30000);if(status)status.textContent='Файл получен.';
          return;
        }
        const html=await response.text();const parsed=new DOMParser().parseFromString(html,'text/html');
        const next=parsed.querySelector('#content');
        if (!next) throw new Error('Ответ сервера не распознан. Исход действия нужно проверить.');
        document.querySelector('#content').replaceWith(next);
        document.title=parsed.title;
        const alert=next.querySelector('.errorlist,.ta-notice.error');
        (alert || next).scrollIntoView({block:'start'});
      } catch(error) {
        if(status){status.classList.add('error');status.textContent='Не удалось получить подтверждение. Исход действия пока неизвестен. Проверьте карточку или повторите этот же запрос: ключ операции сохранён.';}
      } finally {button.disabled=false;}
    }
  });
})();
