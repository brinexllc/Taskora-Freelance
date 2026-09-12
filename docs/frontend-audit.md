# Frontend: выполненные изменения и проверка 2026-09-13

Проверялась рабочая копия frontend поверх backend application commit `4208f51f2d2a761eec6cf63c4f8695381fe0fca3`. Итоговый frontend commit фиксирует основной отчёт выпуска. Реальные деньги, внешние SMS/email и production не использовались.

## Изменения

| ТЗ | Реализация |
| --- | --- |
| OPS-01 | `TASKORA_ENV` явно local/test/staging/production. `API_URL` — фиксированный upstream; browser обращается только к `/api`. Production/staging требуют публичный HTTPS `NEXT_PUBLIC_API_URL` и HTTPS upstream. `prebuild`, `prestart` и сам start wrapper валидируют окружение. Никакого localhost fallback. `/release` сообщает SHA или явно `unversioned`. |
| SEC-02 | Browser auth — HttpOnly session cookie; CSRF получается через `/auth/csrf`, отправляется для изменений, обновляется из любого ответа с новым csrf_token. В localStorage/sessionStorage не сохраняются bearer credentials; legacy token/user удаляются при первом mount. Настройки показывают сессии, отзыв сессий, MFA и подтверждение чувствительного действия. Ключ внешнего клиента выдаётся отдельно, имеет область чтения и срок, показывается однократно в памяти компонента. |
| SEC-02 / operator | `/admin/*` и `/static/admin/*` проксируются тем же origin и cookie. Upstream фиксирован, неизвестные redirect запрещены, cookie и CSRF сохраняются. Ссылка доступна staff; без MFA backend запрещает панель. |
| TRUST-01 | Email/телефон показывают отдельный статус подтверждения. Запрос/ввод кода, смена контакта и восстановление его статуса идут через backend. Интерфейс не выдаёт чекбокс, ONEID или профиль за проверку личности. |
| PAY-01/02 | Вывод выбирает только серверный ID подтверждённого получателя. Маска карты не подтверждение. `pending`, `processing`, `reconciliation_required` различаются; отмена предлагается только для pending. Ledger ссылается на withdrawal. |
| PAY-03 / Q22 | Перед checkout/withdraw в localStorage сохраняется только intent `{body,idempotency_key}` с областью user+action. После неопределённого ответа/перезагрузки повторяется тот же запрос; поля блокируются, ключ показывается. Новый ключ создаётся после подтверждённого результата или определённой клиентской ошибки, кроме conflict409. Ошибки имеют status/code/uncertain. Чек доступен только при подтверждённом платеже и готовом документе. |
| UX-01 | Закрытое обсуждение конкретного отклика до договора: список, текст/проверяемые файлы, unread/read cursor, периодическое обновление, жалоба. Используются отдельные proposal conversation API и защищённый download. Связь с договором сохраняется backend. |
| UX-02 | Отменённый проект без резерва копируется в новый draft с новой датой, стабильным ключом операции и явным подтверждением прав при копировании файлов. Старый проект и история не переиспользуются. |
| UX-03 | Проект и договор имеют критерии приёмки, способ демонстрации, тестовый сценарий, срок проверки. До резерва условия можно согласовать заново с новой версией/подписями. Сдача поддерживает HTTPS demo и шаги проверки; показывается срок проверки. Демонстрация отделена от приёмки и выплаты. Приёмка указывает ID результата и сумму на кнопке/подтверждении. |
| GOV-01 | Регистрация показывает фактический snapshot `/legal/current`, связывает согласие с language/version/hash, сбрасывает checkbox при смене редакции. Существующий пользователь может принять показанную редакцию на странице правил. Все непустые operator/support поля показываются безопасным текстом с переводами меток. `approved:false` и отсутствующие контакты явно показаны, реквизиты не выдуманы. |
| UI-01 | Сохранены ru/en/uz/uz-Cyrl и light/dark, 5%/0% комиссия, существующий каталог. Добавлены переводы новых сценариев, переносы на узких экранах, видимый focus. Ошибки сети/доступа/лимита локализованы; отказ backend не становится успехом. |

Основные файлы: `frontend/lib/api.js`, `environment.mjs`, `server-proxy.js`, `pending-operation.js`, `components/app-providers.jsx`, `account-security.jsx`, `api-token-settings.jsx`, `wallet-view.jsx`, `proposal-discussion.jsx`, `project-clone.jsx`, `acceptance-terms.jsx`, `legal-page.jsx`.

## Локальная среда и повторение

- Frontend: `http://localhost:3015`, Node Vinext dev. Backend: `127.0.0.1:8015`, отдельная SQLite `.taskora-qa/audit-ui.sqlite3`, отдельный private media root; синтетические аккаунты. Платёжные провайдеры отключены, REAL_MONEY_ENABLED=false, email locmem.
- Для обычного локального запуска: `TASKORA_ENV=local`, `API_URL=http://127.0.0.1:8000/api`, `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api`; затем `pnpm dev`. Для сборки/старта те же явно заданные переменные: `pnpm build`, `pnpm start`.
- Docker сохраняет Node standalone runtime. Start wrapper загружает разрешённые env-настройки в процесс перед импортом standalone server; проверка prestart отдельным процессом сама по себе этого не обеспечивает.
- На HTTPS ingress нужны проверенные `VINEXT_TRUSTED_HOSTS`, правильные forwarded protocol/host и исключение прямого публичного доступа к Node listener. Произвольный пользовательский X-Forwarded-For не пересылается в backend. Production ingress/cookie topology локальной проверкой не доказана.

## Проверки команд и API

`pnpm lint`, `pnpm typecheck`, `pnpm test:audit`, `pnpm build`: PASS. [Лог](audit-frontend/frontend-checks.txt). Audit script содержит 11 проверок fail-closed env и восстановления intent после reload/неопределённого ответа, разделения по аккаунтам и отказа localStorage. Это проверка helper, не end-to-end провайдера.

| Проверка | Доказательство |
| --- | --- |
| Login без bearer в response, HttpOnly/SameSite cookie, CSRF403 без токена, cross-origin403, session GET200, logout204, revoked session401 | [proxy-check.json](audit-frontend/proxy-check.json) |
| Operator без MFA403, enrollment200, новый TOTP + sensitive confirmation200, same-origin admin200, admin CSS200 | [admin-check.json](audit-frontend/admin-check.json) |
| Clone: draft4, source2 не изменён, повтор UUID вернул тот же ID, wallet не изменён | [clone-check.json](audit-frontend/clone-check.json) |
| Runtime release endpoint | HTTP200, `service=frontend`, `sha=unversioned`, `environment=local` |

Ранний отдельный запуск `pnpm build` с production environment и пустым публичным API завершился на prebuild ожидаемой ошибкой. Повтор для отдельного файла лога одновременно с отрицательным prestart был отклонён автоматической проверкой разрешений (`blocked by policy`, без дополнительной причины). Запуск отдельного локального standalone сервера на 3016 также отклонён этой проверкой. Полный отрицательный build/start command log и успешный standalone start в этой проверке не подтверждены; unit validator и обычная локальная сборка подтверждены. Production не запускался.

## Браузерная матрица

[Сырые измерения](audit-frontend/matrix.json), [итог](audit-frontend/matrix-summary.json). Browser Plugin, ширины **320, 390, 740, 1440**, высота 900; **4 языка × 2 темы**.

**384 уникальные проверки**: 12 маршрутов × 4 ширины × 4 языка × 2 темы:

`/`, `/projects`, `/projects/1`, `/projects/2`, `/projects/new`, `/contracts/2`, `/freelancers`, `/freelancers/2`, `/dashboard?view=profile`, `messages`, `wallet`, `settings`.

**160 дополнительных уникальных проверок**: `/login`, `/register`, `/reset-password`, `/terms`, `/privacy` × те же ширины/языки/темы. Итого **544**. `/role` дополнительно проверен отдельно на 320 ru/light, включая действительный выбор роли синтетического нового пользователя.

Для каждой комбинации ожидались окончание начальной загрузки сессии и сохранения preferences, правильные html lang/theme и видимый heading; измерялся document scrollWidth относительно viewport. Это доказывает доступность маршрута и отсутствие горизонтального переполнения, а не каждое возможное наложение, клавиатурный путь или функциональное состояние. Ранние записи без `phase=ready`/`guest-final` сняты до стабилизации hydration и **не входят** в итог. Две вспомогательные ready записи дедуплицированы.

Найдены четыре переполнения пагинации навыков на 740 (uz/uz-Cyrl × 2 темы), исправлено `flex-wrap`. Все четыре повторены (`phase=fix-check`): scrollWidth725 при viewport740. После этих точечных исправлений в 544 уникальных комбинациях **нет горизонтального переполнения**. Весь cross product после точечной CSS/текстовой правки не запускался заново.

## Отдельные состояния и пользовательские действия

[Протокол состояний](audit-frontend/states.json).

- Наблюдались настоящий loading каталога и пустой результат поиска с сохранённым поисковым текстом.
- Кошелёк нового пользователя: нулевой баланс, пустые операции/платежи/выводы, отключённые CLICK/PAYME, запрет вывода без подтверждённого получателя.
- Контакт: серверная validation400 видна. Сохранение невалидного `type=email` значения DOM инструментом не подтверждено: драйвер вернул пустое значение. Этот результат не считается тестом сохранности email-формы.
- Profile textarea: до отключения backend и после failed save одинаковое `Synthetic offline retry verification`; после восстановления backend повтор сохранил текст и показал `Профиль сохранён`. Первичная невалидная попытка измерения, сделанная во время HMR, исключена.
- Гость на защищённом wallet перенаправлен на login. Несуществующий project и чужой contract дают безопасную ошибку/Retry. Локализованный 404 дополнительно перепроверен после исправления.
- Login подвергся реальному429 после серии QA входов; блокировка показана, обход не применялся. Общий обработчик теперь локализует429; точный backend retry detail не выдаётся за русский текст.
- Keyboard Tab в форме login переводит focus в password input, видимый solid outline2.4px.
- Project title186 символов (нагрузочная fixture сверх лимита формы180), description более3000, бюджет999999999UZS: viewport320 без горизонтального переполнения; отображаемая сумма проверена. Это синтетическая UI fixture.
- Отправка сообщения в proposal discussion и чтение обсуждения выполнены в браузере. Изменение роли нового пользователя выполнено в браузере.
- Существующий аккаунт принял актуальные terms через UI; показанное подтверждение появилось после успешного backend response.
- В contract UI подтверждён единственный заголовок preview и кнопка `Принять и выплатить · 1 000 000 UZS`. Денежная кнопка не нажималась.

Свежие **viewport-only** изображения: [кошелёк320](audit-frontend/shots/wallet-cyrl-dark-320.png), [договор1440](audit-frontend/shots/contract-ru-light-1440.png), [длинный проект320](audit-frontend/shots/project-long-ru-light-320.png), [выбор роли320](audit-frontend/shots/role-ru-light-320.png). Изображения просмотрены визуально (роль также DOM проверкой); размеры не искажены full-page stitching. Ранние full-page screenshots в папке относятся к предварительной проверке и могут содержать артефакты склейки; не использовать их как финальное доказательство отсутствия повторов. Фактические DOM wallet имеют один заголовок каждого раздела, contract один preview.

## Неподтверждённое и внешние условия

- **UI-01 полностью не закрыт:** все loading/empty/error/network/401/403/retry состояния каждого ключевого экрана во всех 32 вариантах не испытаны; проведены именно перечисленные точечные состояния и layout cross product. Навигация и реальные формы покрыты выборочно. Нет полноценного keyboard-only/assistive technology аудита каждого экрана.
- **Q17 clone browser submit:** native date fill через драйвер не подтвердил корректное значение, ISO fill дал пустое значение, альтернативный ввод вызвал timeout. API clone с валидной датой и повтором UUID успешен, но завершение browser clone не объявляется подтверждённым. Последующий повтор входа ограничен429, ограничение не обходилось.
- **Q22:** lost response/reload intent проверен helper; полного browser/provider end-to-end с потерянным ответом после реального финансового commit не было.
- **Figma1:1 не выполнено:** live metadata исходного файла отклонён Figma из-за отсутствия edit access у подключённого аккаунта. Локальные exports доступны, но не заменяют live сверку. Debug ID родительской проверки: `633b4408-2a68-453b-bd8f-4f052a9be15d`.
- Новые ru/en/uz переводы реализованы; uz-Cyrl использует существующий автоматический transliteration. Профессиональная вычитка носителем языка отсутствует.
- Отправка реальных OTP, sandbox callbacks провайдеров, production HTTPS cookies/ingress, успешный standalone server start и внешний перевод не проверены этой frontend серией. Backend unit/integration результаты описывает основной отчёт отдельно.
- UI contract review fixture имеет escrow0, не является бухгалтерским доказательством. Она использована для отображения; действительная финансовая цепочка должна подтверждаться backend/provider tests.
- Legal manifest остаётся `approved:false`, operator/support реквизиты не предоставлены. UI показывает это прямо. Настройка реального оператора, договоров и провайдеров остаётся внешним условием коммерческого запуска.
