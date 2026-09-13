(() => {
  if (window.taskoraAdminEditorReady) return;
  window.taskoraAdminEditorReady = true;
  const schemas = {
    portfolio: [['title', 'Название работы'], ['category', 'Категория'], ['description', 'Описание'], ['url', 'Ссылка на работу'], ['image', 'Обложка работы']],
    services: [['title', 'Название услуги'], ['description', 'Описание'], ['price', 'Цена, UZS'], ['delivery_days', 'Срок, дней']],
  };
  function initialize() {
    document.querySelectorAll('[data-collection-kind]').forEach(editor => {
      if (editor.dataset.initialized) return;
      editor.dataset.initialized = 'true';
      const input = editor.querySelector('input[type=hidden]');
      let entries;
      try { entries = JSON.parse(input.value || '[]'); } catch { entries = []; }
      if (!Array.isArray(entries)) entries = [];
      const kind = editor.dataset.collectionKind;
      const list = editor.querySelector('[data-collection-items]');
      const sync = () => { input.value = JSON.stringify(entries); input.dispatchEvent(new Event('change', { bubbles: true })); };
      const draw = () => {
        list.replaceChildren();
        entries.forEach((entry, index) => {
          const group = document.createElement('fieldset'); group.style.cssText = 'padding:16px;margin:12px 0;border:1px solid #dce5df;border-radius:10px';
          const legend = document.createElement('legend'); legend.textContent = `Запись ${index + 1}`; group.append(legend);
          schemas[kind].forEach(([key, title]) => {
            const label = document.createElement('label'); label.textContent = title; label.style.cssText = 'display:grid;gap:5px;margin:10px 0';
            if (key === 'image') {
              const image = document.createElement('input'); image.type = 'file'; image.accept = 'image/png,image/jpeg,image/webp';
              const note = document.createElement('small'); note.textContent = entry.image ? 'Изображение сохранено' : 'Изображение не задано';
              image.addEventListener('change', () => { const file = image.files[0]; if (!file) return; if (file.size > 2 * 1024 * 1024) { note.textContent = 'Выберите изображение до 2 МБ'; return; } const reader = new FileReader(); reader.onload = () => { entry.image = reader.result; note.textContent = `Выбрано: ${file.name}`; sync(); }; reader.readAsDataURL(file); });
              const clear = document.createElement('button'); clear.type = 'button'; clear.className = 'ta-button secondary'; clear.textContent = 'Удалить обложку'; clear.addEventListener('click', () => { entry.image = ''; note.textContent = 'Обложка будет удалена'; sync(); });
              label.append(image,note,clear); group.append(label); return;
            }
            const field = document.createElement(key === 'description' ? 'textarea' : 'input');
            field.value = entry[key] ?? ''; field.setAttribute('aria-label', `${title}, запись ${index + 1}`);
            if (['price', 'delivery_days'].includes(key)) { field.type = 'number'; field.min = key === 'price' ? '0' : '1'; field.step = key === 'price' ? '.01' : '1'; }
            field.addEventListener('input', () => { entry[key] = key === 'delivery_days' ? Number(field.value) : field.value; sync(); });
            label.append(field); group.append(label);
          });
          const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'ta-button secondary'; remove.textContent = 'Удалить запись';
          remove.addEventListener('click', () => { entries.splice(index, 1); sync(); draw(); }); group.append(remove); list.append(group);
        });
      };
      editor.querySelector('[data-collection-add]').addEventListener('click', () => {
        if (entries.length >= (kind === 'portfolio' ? 9 : 6)) return;
        entries.push(kind === 'services' ? {title:'',description:'',price:'0',delivery_days:1} : {title:'',description:'',category:'',url:'',image:''}); sync(); draw();
      });
      draw();
    });
    document.querySelectorAll('.ta-avatar-editor').forEach(editor => {
      if (editor.dataset.initialized) return; editor.dataset.initialized = 'true';
      const value = editor.querySelector('input[type=hidden]'); const status = editor.querySelector('small');
      status.textContent = value.value ? 'Текущий аватар сохранён' : 'Аватар не задан';
      editor.querySelector('input[type=file]').addEventListener('change', event => {
        const file = event.target.files[0]; if (!file) return;
        if (file.size > 2 * 1024 * 1024) { status.textContent = 'Выберите изображение до 2 МБ'; return; }
        const reader = new FileReader(); reader.onload = () => { value.value = reader.result; status.textContent = `Выбрано: ${file.name}`; value.dispatchEvent(new Event('change', {bubbles:true})); }; reader.readAsDataURL(file);
      });
      editor.querySelector('[data-avatar-clear]').addEventListener('click', () => { value.value = ''; status.textContent = 'Аватар будет удалён'; value.dispatchEvent(new Event('change', {bubbles:true})); });
    });
  }
  const start = () => { initialize(); new MutationObserver(initialize).observe(document.body, {childList:true,subtree:true}); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
