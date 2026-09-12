# Frontend: выполненные изменения и проверка 2026-09-13

Исходная проверка выполнялась поверх backend application commit `4208f51f2d2a761eec6cf63c4f8695381fe0fca3`; frontend с последними исправлениями состояний зафиксирован commit `6c131a23ee0ed243ab085ca86f9844beb3e4c775`. Полные SHA выпуска и backend-проверки фиксирует основной отчёт. Реальные деньги, внешние SMS/email и production не использовались.

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

`pnpm lint`, `pnpm typecheck`, `pnpm test:audit`, `pnpm build`: PASS. [Финальный лог](audit-frontend/frontend-ui-state-fixes-checks.txt). Audit script содержит 11 проверок fail-closed env и восстановления intent после reload/неопределённого ответа, разделения по аккаунтам и отказа localStorage. Это проверка helper, не end-to-end провайдера.

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

## Состояния и действия после матрицы раскладки

[Per-screen checklist](audit-frontend/screen-state-checklist.md), [протокол основного задания](audit-frontend/root-state-checks.json), [первоначальные состояния](audit-frontend/states.json).

После временной недоступности браузера встроенная вкладка была восстановлена в основном задании. Дополнительная серия выполнена в RU/light390×900 через изолированный frontend3015 → QAproxy8015 → backend8017. Прокси задерживал выбранные запросы, возвращал simulated502/401/403 или закрывал TCP-соединение. Затем правило снималось и нажималась настоящая кнопка Retry. Эта серия не имитировала успешные денежные ответы или provider callbacks. Итоговый root-протокол содержит 66 записей, включая исходные неудачные попытки и последующие проверки; число записей не означает 66 независимых PASS. После проверки fault-правило очищено.

- Для основных страниц и зависимых данных подтверждены loading, явная ошибка, реальный Retry после снятия инъекции и видимый focus. Точные статусы каждого маршрута перечислены в checklist; общий PASS не переносится на непроверенную ветку.
- Исправлены найденные ошибки: молчаливый отказ overview/catalog/lookup договора/counters/direct conversation, отсутствие ручного Retry чата, clone при неизвестном состоянии договора, raw API errors и initial CSRF failures, отсутствие текста пустого выбранного чата и неправильная подпись пустого поиска исполнителей.
- Пустой поиск заказов и исполнителей сохранил введённый запрос. Пустые portfolio/skills/services/reviews профиля и выбранный чат подтверждены отдельно. Новый кошелёк показал balance0, пустые списки и disabled withdrawal без verified recipient.
- Profile textarea сохранил `Synthetic offline retry verification` при остановленном backend. После восстановления Retry Save дал настоящий серверный успех. Невалидный email получил400; достоверная проверка сохранности email через driver не получена.
- Гость перенаправлялся с wallet на login, чужой договор и отсутствующий project не раскрывались. Ошибки401/403 локализованы. После настоящих неверных login credentials правильный повтор вошёл в аккаунт. Login/reset дополнительно показали503 и network failure; роль сохранила выбранный вариант после503/offline и применилась после реального повтора.
- Регистрация при недоступном legal snapshot запрещала согласие и давала Retry; после восстановления загрузила настоящий документ. Reset дошёл до шага кода после восстановления связи; это generic response для синтетического контакта, не доказательство внешней доставки OTP.
- Длинный project title186 символов (стресс-данные сверх ограничения формы180), description более3000 и бюджет999999999UZS проверены на320 без горизонтального переполнения. Денежная кнопка приёмки показывает сумму; исходный review fixture escrow0 не использовался для реальной выплаты.
- Все8operator/support полей manifestv3 отображены в браузере: [snapshot](audit-frontend/legal-v3-browser.txt). Новое согласие с v3 действительно сохранено через UI. Fault-ветка consent осталась inconclusive и не выдана за успешную проверку. `approved:false` остаётся явным предупреждением до юридического утверждения.

Свежие viewport-only изображения: [кошелёк320](audit-frontend/shots/wallet-cyrl-dark-320.png), [договор1440](audit-frontend/shots/contract-ru-light-1440.png), [длинный проект320](audit-frontend/shots/project-long-ru-light-320.png), [выбор роли320](audit-frontend/shots/role-ru-light-320.png). Они просмотрены визуально. Ранние full-page screenshots могут содержать артефакты склейки и не используются как финальное доказательство отсутствия повторов. В фактическом DOM wallet разделы и contract preview не дублируются.

## Неопределённый результат денежной операции

Q22 fund выполнен в браузере на отдельной синтетической fixture: backend принял резервирование договора 3 и вернул 200, QAproxy намеренно отбросил этот ответ. UI показал ошибку связи без ложного успеха. Настоящий повтор завершился успешно; операция использует естественный ключ `contract:3`. [Snapshot после потери ответа](audit-frontend/q22-fund-lost-response.txt), подтверждение повторного результата — в root-state-checks.json. [Сверка БД](audit-evidence/q22-fund-after.json) показала ровно один escrow hold на 250 000 UZS, договор active с резервом 250 000 UZS и сходящийся баланс.

Q22 withdrawal с UUID также выполнен в браузере: запрос на 1 000 UZS создал pending-заявку, backend вернул 201, затем QAproxy оборвал ответ. UI показал неопределённый результат и ключ `ba181b3d-f761-4ba9-96bf-8754c05d48a2`. После перезагрузки сохранились тот же ключ, сумма, получатель и подтверждение; поля были заблокированы. Настоящий повтор сохранил одну pending-заявку и очистил завершённый intent. Доказательства: [потерянный ответ](audit-frontend/q22-withdraw-lost-response.txt), [после перезагрузки](audit-frontend/q22-withdraw-reloaded.txt), [после повтора](audit-frontend/q22-withdraw-retried.txt), [просмотренный screenshot](audit-frontend/shots/q22-withdraw-pending-390.png).

[БД до](audit-evidence/q22-withdraw-before.json) и [БД после](audit-evidence/q22-withdraw-after.json): ровно одна заявка №4 pending на 1 000 UZS и одно списание −1 000 UZS. Баланс 749 000 UZS = opening 1 000 000 UZS + ledger −251 000 UZS. UUID в БД совпал с показанным до и после reload. [Trace прокси](audit-evidence/q22-proxy-events.jsonl) подтверждает получение upstream 200/201 перед обрывом; его поле `idempotency_key_sha256:null` относится только к HTTP-заголовку, тогда как UUID передавался в JSON body, поэтому trace не используется как доказательство совпадения ключа.

Оба сценария использовали только синтетическую локальную БД. Внешний перевод и provider callback не выполнялись. Audit helper11 отдельно подтверждает сохранение `{body,idempotency_key}` после reload/lost response, разделение по аккаунтам и отказ при недоступном хранилище.

## Остаточные ограничения и внешние условия

- Q17 browser clone: native date через Browser Plugin не дал принятую backend дату; сохранённый ключ виден при502, но успешное создание клона в браузере не подтверждено. API clone с корректной датой, повтором UUID и неизменённым source/wallet — PASS. Неопределённость ввода не исправлялась подменой DOM или вымышленным UI успехом.
- Некоторые form-value readbacks после Browser fill/CUA typing неоднозначны. Это явно отмечено в checklist; исходники не сбрасывают login/reset поля на ошибке, и успешные реальные повторы проверены отдельно. Проверка всех keyboard-only/assistive technology путей не заявляется.
- Figma1:1 не выполнено: live metadata исходного файла отклонён из-за отсутствия edit access. Локальные exports не заменяют live сверку. Debug ID: `633b4408-2a68-453b-bd8f-4f052a9be15d`.
- Новые ru/en/uz переводы реализованы, uz-Cyrl использует существующее преобразование алфавита. Профессиональная вычитка носителем языка не проводилась.
- Реальные OTP, sandbox callbacks провайдеров, production HTTPS/ingress и внешний перевод этой frontend серией не подтверждены. Негативный повтор build/start и отдельный standalone start отклонены автоматической проверкой разрешений, как описано выше; обход не предпринимался.
- Владелец предоставил реквизиты и сроки48часов; API и UIv3 проверены. Юридическое утверждение и настройка реальных провайдеров остаются внешними условиями коммерческого запуска. Последующие изменения текста manifest версионируются основным заданием и требуют нового consent.

Финальные lint, TypeScript, audit11 и build после всех frontend source исправлений — PASS: [лог](audit-frontend/frontend-ui-state-fixes-checks.txt).
