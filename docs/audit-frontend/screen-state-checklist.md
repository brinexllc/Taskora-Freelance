# UI-01: проверки состояний по экранам

2026-09-13, RU/light390×900. Основное задание восстановило доступ к встроенному браузеру и продолжило UI QA. Прежняя недоступность browser runtime frontend-подзадачи больше не означает блокировку всех проверок. Первая матрица544 относится только к layout.

**Методика:** изолированный frontend3015 → локальный QAproxy8015 → backend8017/SQLite. Только перечисленные API-запросы получали simulated502/401/403, либо TCP-разрыв. Auth/cookie оставались настоящими, кроме явных тестов session gate. Delay позволял увидеть loading. После удаления правила нажималась настоящая кнопка Retry и загружался реальный backend ответ. Успешные денежные операции и provider callbacks не подменялись.

Доказательства: [root-state-checks.json](root-state-checks.json), [states.json](states.json), [legal-v3-browser.txt](legal-v3-browser.txt). Итоговый root-протокол содержит 66 записей, включая исходные неудачные попытки и повторные проверки; это не счётчик независимых PASS. Значок — означает, что в текущем файле нет отдельной проверки именно этого статуса; это не PASS.

| Экран | Loading | Simulated502 + Retry | TCP-разрыв + Retry | Отказ доступа + Retry | Keyboard focus | Empty |
| --- | --- | --- | --- | --- | --- | --- |
| Главная `/` | PASS | PASS | PASS | 401 | PASS: 2.4px | Не применимо к hero; empty профилей отдельно |
| Каталог заказов `/projects` | PASS | PASS | PASS | 403 | PASS: 2.4px | PASS: реальный пустой поиск, states.json |
| Заказ `/projects/1` | PASS | PASS | PASS | 403 | PASS: 2.4px | n/a single record;404 PASS |
| Отменённый заказ `/projects/2` | PASS | PASS | PASS | 401 | PASS: 2.4px | n/a single record; browser clone/date отдельно |
| Новый/редактируемый заказ `/projects/new` | PASS | PASS | PASS | 403 | PASS: 2.4px | n/a новая форма |
| Договор `/contracts/2` | PASS | PASS | PASS | 403 | PASS: 2.4px | n/a single record; чужой404 PASS |
| Каталог исполнителей `/freelancers` | PASS | PASS | PASS | 401 | PASS: 2.4px | PASS: реальный пустой поиск; copy исправлен и повторён |
| Профиль исполнителя `/freelancers/2` | PASS | PASS | PASS | 403 | PASS: 2.4px | PASS: пустые skills/portfolio/services/reviews |
| Свой профиль `/dashboard?view=profile` | PASS | PASS | PASS | — | PASS: 2.4px | n/a профиль из session |
| Сообщения `/dashboard?view=messages` | PASS | PASS | PASS | 403 | PASS: 2.4px | PASS: выбранный чат contract3 пуст, placeholder виден |
| Кошелёк `/dashboard?view=wallet` | PASS | PASS | PASS | 401 | PASS: 2.4px | PASS: новый аккаунт, balance0 и пустые списки |
| Настройки `/dashboard?view=settings` | PASS | PASS | PASS | 403 | PASS: 2.4px | n/a форма; минимум одна current session |
| Правила `/terms` | PASS | PASS | — | 403 | PASS: 1.6px | n/a manifest; unapproved warning PASS |
| Политика данных `/privacy` | PASS | — | PASS | — | PASS: 1.6px | n/a manifest |

## Формы входа и доступа

| Экран | Loading / API error | Network failure | Реальный повтор | Сохранность ввода | Empty |
| --- | --- | --- | --- | --- | --- |
| `/login` | PASS503 и настоящий отказ неверных credentials | PASS | PASS правильный вход → role | Readback после fill/CUA inconclusive, источник не сбрасывает поля | n/a форма |
| `/register` | PASS loading/502/403 зависимого legal snapshot, submit недоступен | PASS legal GET | PASS reload legal; это не полный POST регистрации | Не заявляется | n/a форма |
| `/reset-password` | PASS503 и loading | PASS | PASS → шаг кода для синтетического контакта | Readback не подтверждён; реальная отправкаOTP не тестировалась | n/a форма |
| `/role` | PASS503 | PASS | PASS → dashboard | PASS выбранный вариант сохранён при обеих ошибках | n/a обязательный выбор |

Login keyboard focus подтверждён первоначальной серией; register focus INPUT solid2.4px измерен в root-протоколе. Для reset/role отдельное числовое измерение outline в протоколе отсутствует; клики и выбор не приравниваются к полному keyboard-only аудиту. У формы регистрации в этой серии проверено восстановление legal dependency; полный POST нового аккаунта не выдан за проверенный результат.

## Зависимые данные и исправления

Отдельно проверялись overview, category catalog внутри раскрытых фильтров, contracts lookup профиля, прямой выбранный диалог, chat messages, dashboard counters. Для них добавлены явные loading/error/Retry; clone скрыт при unknown/error состоянии связанного договора. Первый catalog check до раскрытия фильтров завершился timeout; повтор после раскрытия фильтров успешен и вернул реальные категории. Исходная неудачная запись сохранена в JSON.

Первичный global session502 показывал raw server detail. После проверки исправлен AppProviders: Error хранится как объект, локализуется при рендеринге, refresh callback не зависит от языка. Initial CSRF failure и download errors сохраняют HTTPstatus/code/uncertain. Остальные API action errors, включая роль, пароль, сообщения и финансовые действия, направлены в общий переводчик.

## Формы и фактические действия

- Profile textarea: сохранность текста при настоящей остановке backend и успешный повтор Save после восстановления — PASS (`states.json`).
- Новый пользователь выбрал роль и перешёл в dashboard — PASS (`states.json`). Дополнительные error/retention проверки форм основного задания зафиксированы в `root-state-checks.json`.
- Поиск сохранил запрос и показал явное пустое состояние — PASS.
- Отправка/чтение proposal discussion — PASS в первоначальной серии.
- Wallet нового аккаунта: пустые списки, balance0, отсутствие verified recipient и disabled withdrawal/payment — PASS.
- Manifestv3: отображены все8operator/support полей, approvedfalse; действительное новое consent сохранено через UI — PASS. Fault-сценарий consent не считается доказанным, в JSON помечен faultInconclusive.
- Q17 clone: UI показал стабильный idempotency key при simulated502, но native date input не дал принятую дату; browser clone success не заявляется. Backend/API clone с валидной датой, повтором UUID и неизменённым source/wallet — PASS (`clone-check.json`).
- Q22 fund: backend commit200 → намеренно потерянный ответ → успешный реальный browser retry подтверждён для contract3 с естественным ключом contract:3. [Сверка БД](../audit-evidence/q22-fund-after.json): один escrow hold на 250 000 UZS, резерв договора и баланс сходятся.
- Q22 withdrawal: backend commit201 → потерянный ответ → reload с тем же UUID и заблокированными полями → успешный настоящий повтор — PASS. После повтора intent очищен; [БД](../audit-evidence/q22-withdraw-after.json) содержит ровно одну pending-заявку на 1 000 UZS и одно списание −1 000 UZS; баланс 749 000 UZS сходится с opening + ledger. [До reload](q22-withdraw-lost-response.txt), [после reload](q22-withdraw-reloaded.txt), [после retry](q22-withdraw-retried.txt). Совпадение UUID подтверждают DOM и БД; [trace](../audit-evidence/q22-proxy-events.jsonl) доказывает только ответ upstream до обрыва, поскольку UUID находился в JSON body, а trace проверял HTTP-заголовок.
- Обе Q22 операции локальные и синтетические, внешнего перевода не было. Helper11 дополнительно подтверждает reload-safe intent. Provider end-to-end не выполнялся. После QA правило fault-прокси очищено.

## Пределы проверки

Native date и некоторые form inputs в Browser Plugin не дали надёжного DOMvalue подтверждения. Пустое DOMvalue после driver.fill само по себе не объявляется дефектом продукта; источник состояния не сбрасывает эти поля на ошибке. Основное задание дополнительно проверило CUA typing и фактические ответы; где это не сняло неопределённость, сохранён статус inconclusive.

Это базовая проверка состояний в одном RU/light390 и layout544; не полный assistive technology/keyboard-only аудит всех пользовательских путей. Figma live сверка недоступна из-за прав исходного файла. Исторические ранние browser-unavailable и initial failed attempts не удаляются из объяснения, но заменены актуальными PASS там, где основной браузер выполнил проверку.
