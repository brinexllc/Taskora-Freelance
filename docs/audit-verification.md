# Проверка реализации ТЗ от 13.09.2026

Дата проверки: 13 сентября 2026, Asia/Tashkent. Время в машинных протоколах — UTC. Рабочая ветка: `codex/audit-stabilization-2026-09-13`. Изменения выполнены локально; push, deployment, операции с реальными деньгами и ротация инфраструктурных секретов не выполнялись.

Исходное ТЗ: `Taskora_Audit_DOWORK_TZ_RU_2026-09-13.md`, SHA256 `6ebe61b2f372d74bd41a72b7fce84887697f44b4c1dae6bf38054efe57b3634a`. Его разделы P0/P1 приняты как требования к реализации. Раздел P2 прямо обозначен как предложения вне обязательной стабилизации; автоматические выплаты, ONEID и новые направления бизнеса не внедрялись.

## Версии и доказательства

Перед началом получен `origin/main`, совпавший с исходным SHA аудита `556ed75f5146d29b2a71e10dfa3cfe4a86ce41aa`.

- Backend, миграции и основные инструкции: `4208f51f2d2a761eec6cf63c4f8695381fe0fca3`.
- Проверенный шаблон роли, расширенный тест повторного найма и актуализация README: `8901e049e797d2434fc19195090bd994ab79ad30`. Прикладной backend после полного suite не менялся.
- Итоговый backend: `57c6648dc2c85acac5ae1e9faa9fd50ed8344b8d`. Исправление окружения в `f10224a` требует явного `TASKORA_ENV` и исключает наследование production БД командой тестов. Следующий коммит добавил только данные владельца и сохранение реквизитов при обновлении legal manifest. `scripts/check_startup_guards.py` проверяет реальный запуск в отдельных процессах.
- Итоговый frontend: `6c131a23ee0ed243ab085ca86f9844beb3e4c775`. После основной реализации `cce97cf` добавлены проверенные в браузере loading/error/Retry, перевод ошибок API и пустые состояния.
- [Машинный паспорт](audit-evidence/release-passport.json) фиксирует эти две версии на восстановленной искусственной PostgreSQL, миграции и хеш приватного файла; это не паспорт работающего production.
- Паспорт и процедура выпуска: [audit-release.md](audit-release.md).
- Финансовые маршруты, сверка и операторские процедуры: [payments-audit.md](payments-audit.md).
- Контакты, сессии, MFA, лимиты и согласия: [security-audit.md](security-audit.md).
- Интерфейс и его фактическая браузерная приёмка: [frontend-audit.md](frontend-audit.md).
- Шрифты, источники и ограничения подтверждения прав: [design-assets.md](design-assets.md).

«Локально PASS» ниже означает успешные воспроизводимые проверки на искусственных данных. Этот статус не подтверждает production, банк, доставку SMS/email, юридическое согласование или соответствие недоступному живому Figma. Незавершённые внешние пункты перечислены явно.

## Автоматические проверки

| Проверка | Фактический результат | Протокол |
| --- | --- | --- |
| Полный Django suite на PostgreSQL 17.11 | 175 тестов, PASS, 0 пропусков, 278.397 сек | [postgresql-tests.txt](audit-evidence/postgresql-tests.txt) |
| Итоговый полный PostgreSQL suite на Python 3.14.7 после исправления окружения | 175 тестов, PASS, 0 пропусков, 158.979 сек | [postgresql-python314-tests.txt](audit-evidence/postgresql-python314-tests.txt) |
| Полный Django suite на изолированной SQLite | 175 обнаружено, 165 выполнено, PASS, 10 PostgreSQL-проверок пропущено, 207.956 сек | [sqlite-tests.txt](audit-evidence/sqlite-tests.txt) |
| Django system check / migration drift | PASS, нет новых незаписанных миграций | Из корня репозитория, `.venv/Scripts/python.exe backend/manage.py check` и `makemigrations --check --dry-run`, с `TASKORA_ENV=test`, `TASKORA_LOAD_DOTENV=false` |
| Совместный backup/restore PostgreSQL и приватного файла | PASS, независимая сверка денег без расхождений | [restore.json](audit-evidence/restore.json), [до](audit-evidence/restore-before.json), [после](audit-evidence/restore-after.json) |
| Уточнённый product suite, включая повторный найм после clone | 8 тестов PostgreSQL, PASS; расширен существующий тест, общий счёт не изменён | [product-final-tests.txt](audit-evidence/product-final-tests.txt) |
| Ограниченная роль БД и защита от неверного места применения | 7 проверок PostgreSQL, PASS; транзакции откатились, искусственные роли/БД удалены | [runtime-role-tests.txt](audit-evidence/runtime-role-tests.txt) |
| Старый код на новой схеме | Целостность схемы, всех таблиц и денег после SELECT-only запуска PASS; полный откат несовместим с новыми сессиями и статусами вывода | [rollback-code-check.json](audit-evidence/rollback-code-check.json) |
| Реквизиты и сроки владельца | 3 focused consent/gate tests PASS; действительный v3 manifest не открывает production деньги при `approved:false` | [legal-manifest-tests.txt](audit-evidence/legal-manifest-tests.txt) |
| Фактический запуск backend с ошибочной конфигурацией и изоляция тестов | 7 subprocess-проверок PASS: 6 ожидаемых отказов запуска и 1 выбор SQLite вместо унаследованной production БД; обращений к БД/сети/`.env` нет | [startup-guards.txt](audit-evidence/startup-guards.txt) |
| Frontend lint / typecheck / audit helper / build | PASS; helper — 11 assertions; production bundle собран с явным local upstream | [первый протокол](audit-frontend/frontend-checks.txt), [итоговый](audit-frontend/frontend-ui-state-fixes-checks.txt) |
| Браузерная раскладка | 544 уникальных сочетания; 4 переполнения исправлены и перепроверены; отдельные состояния проверены выборочно | [frontend-audit.md](frontend-audit.md), [matrix-summary.json](audit-frontend/matrix-summary.json) |
| Финансовый browser retry после commit | Резерв договора и заявка на вывод PASS; UUID заявки сохранён после reload; одна заявка и одна проводка | [до вывода](audit-evidence/q22-withdraw-before.json), [после повтора](audit-evidence/q22-withdraw-after.json), [разрыв ответа](audit-evidence/q22-proxy-events.jsonl) |

PostgreSQL suite включает реальные параллельные транзакции: резерв, приёмку, спор против приёмки, claim против cancel, повторные callbacks, финализацию вывода и лимит из двух процессов. Конкурентные проверки не засчитаны по SQLite. Десять пропусков SQLite полностью выполнены в PostgreSQL suite.

Среда первого полного набора: Windows, Python 3.12.14 (`.venv`), Node.js 24.19.0, pnpm 11.19.0. Итоговый полный набор повторён на Python 3.14.7 (`.venv-mvp`), который также указан в local launcher и Docker, и прошёл 175/175. Тестовый PostgreSQL слушал только loopback на порту 55442; runner создавал отдельную БД. Пароль создавался локально и не включён в отчёты. В ходе ранней проверки, до усиления изоляции, произошла одна неуспешная попытка соединения по окружению; соединение отклонено до выполнения SQL. Теперь при `TASKORA_ENV=test` и при команде `manage.py test` даже с унаследованным production-режимом используется только `TEST_DATABASE_URL` или тестовая SQLite; общая `.env` не загружается.

## Все обязательные задачи

| ID | Реализация и основные файлы | Миграции / проверка | Итог и ограничение |
| --- | --- | --- | --- |
| SEC-01 | Протокол отзыва секрета и проверки журналов; ограниченная runtime-роль отдельно от migration owner: `ops/runtime-role.sql`, `audit-release.md` | 7 проверок шаблона на отдельной БД; он не запускается приложением или миграциями | **Не выполнен:** владелец прямо подтвердил, что опубликованный пароль не сменён; коммерческий допуск заблокирован |
| OPS-01 | `config/environment.py`, `settings.py`, `security_settings.py`, frontend environment/proxy; строгие bool, явная среда, обязательные production параметры | `test_environment_audit.py`; frontend проверка сборки/старта | Код и локальные отрицательные проверки выполнены; реальные переменные Railway не проверены |
| OPS-02 | `operations.py`, `release_passport`, `check_operations`, `process_operations`, `escalate_reviews`, workers/volume в compose и Procfile; изолированный restore runner | `test_operations.py`; backup/restore PASS | Локально выполнено; production redeploy/том, внешний монитор, доставка оповещений, backup policy и RPO/RTO требуют владельца |
| PAY-01 | `services.py`, `payout_views.py`, модели, admin: атомарный claim, снимок получателя, неизвестный исход, подтверждение paid/rejected, аудит override | `0015`, `0016`; `test_withdrawals.py` включая PostgreSQL races | Локально PASS; получателей и внешние evidence оператор подтверждает по согласованному банковскому процессу |
| PAY-02 | Защищённая связь ledger→withdrawal, уникальные события, opening evidence, read-only `reconcile_finances`, консервативный manifest backfill | `0015`, `0018`; `test_reconciliation_command.py`, `test_withdrawals.py`, migration tests | Локально PASS; исторические реальные открытия/выгрузки не выдуманы и не исправлялись |
| PAY-03 | Существующие CLICK/PAYME сохранены; тесты протоколов, повторов, отмен, чеков и worker; новые реальные операции закрыты по умолчанию | `test_click.py`, `test_payme.py`, callback concurrency tests | Локальный suite PASS. Внешний sandbox с ID операций **не выполнен**; рабочая касса не включена |
| GOV-01 | `legal_content.json`, `LegalConsent`, версии/хеши/языки/snapshot, регистрация отклоняет устаревшую редакцию; реквизиты владельца и сроки 48 часов внесены | `0015`; security consent tests; financial release gate test | Код PASS. Реквизиты и сроки предоставлены; юридическое/провайдерское согласование и доставка поддержки не выполнены, `approved:false` |
| TRUST-01 | Отдельные request/confirm, TTL/лимит/одноразовость, снимки подтверждённых контактов, сброс при изменении, серверный запрет вывода без подтверждения | `0015`, `0017`; security и withdrawal tests | Локально PASS; реальная доставка email/SMS не проверена; прежняя история пользователей сохранена |
| SEC-02 | HttpOnly server sessions через same-origin proxy, CSRF, срок/список/отзыв, password reset/change revocation, TOTP и повторное подтверждение для операторов, ограниченные отзываемые API tokens | `0015`, `0018`; `test_security.py`, `test_api_tokens.py`, proxy protocol | Локально PASS; legacy выключен по умолчанию. Согласованный переход production и enrollment операторов ещё не выполнены |
| SEC-03 | Общие атомарные PostgreSQL counters по аккаунту и IP, доверенные proxy только по CIDR, закрытие отправки при сбое лимита, одинаковые recovery ответы | `0015`; `SharedLimiterProcessTests`, negative recovery/proxy tests | Локально PASS на двух процессах; production ingress/IP topology проверяется при выпуске |
| DATA-01 | Принятая сдача + snapshot дедлайна/версии, отдельное исключение споров и неизвестных дат; `profile_metrics.py`, договорные amendments | `0015`; product, escrow и contract tests | Локально PASS; исторические даты не восстанавливаются приблизительно |
| UX-01 | `product_models.py`, `product_api.py`, proposal discussion UI: закрытый диалог, вложения, пагинация, unread/read, spam limit, жалоба; исключительный staff доступ с основанием и аудитом | `0015`; `test_conversation_private_paginated_immutable_and_unread` | Реализовано, API PASS; внешний WebSocket не требуется |
| UX-02 | Owner-only clone отменённого до резерва проекта, новый draft, origin link, новая валидация, UUID повтор, перенос вложений только с подтверждением прав | `0015`; clone API test и frontend-протокол | Локально PASS для создания/повтора/истории/баланса; фактические browser ограничения отмечены отдельно |
| UX-03 | Критерии, demo, сценарий, срок проверки, двусторонние изменения, конкретная принятая версия, отдельная демонстрация и выплата, уведомление без автоматической выплаты | `0015`; product / acceptance / operations tests | Локально PASS. Backend не исполняет загруженный код; доступ к внешнему staging обеспечивает владелец самого staging |
| PERF-01 | Агрегаты и prefetch категорий/навыков; лёгкий list без base64 portfolio; детальный профиль сохранён | `test_profile_queries_do_not_grow_with_page_size` | Локально PASS: 3 SQL для 12 и 48 профилей; замеры ниже; production SLO не заявляется |
| UI-01 | Четыре языка, две темы, cookie workflow, видимые суммы и статусы, обработка повторов, clone/chat/demo/security UI | 544 layout-сочетания, 66 дополнительных записей проверок состояний и действий, снимки; финансовый retry после commit/reload PASS | Основные состояния проверены. Остались неполная приёмка ввода некоторых форм/native date, browser clone, живой Figma и профессиональная языковая приёмка |
| DOC-01 | README и design-rebuild указывают на единый release/verification; API/workers/ENV/local launch и шрифты согласованы | Проверки старта/сборки, настоящий SHA, протоколы в репозитории | Выполнено для локального выпуска. Коммерческие лицензии шрифтов и production паспорт требуют внешних доказательств |

## Матрица Q01–Q24

Все ссылки на тесты ниже относятся к `backend/marketplace/`. Успех теста с искусственными входными данными не приравнивается к успешной банковской операции.

| ID | Проверка и доказательство | Статус |
| --- | --- | --- |
| Q01 | `test_contract_concurrency.py`: параллельные fund через browser session/CSRF; ровно один hold | PostgreSQL PASS |
| Q02 | Там же: два accept, один release и fee; сохранён также `test_commission_concurrency.py` | PostgreSQL PASS |
| Q03 | Там же: dispute против accept, только разрешённый итоговый переход | PostgreSQL PASS |
| Q04 | `test_commission_catalog.py`, `test_reconciliation_command.py`, restore fixture: gross 400 000 / fee 20 000 / net 380 000 / refund 600 000 | PASS |
| Q05 | `test_escrow.py` и commission tests: нулевая выплата, полный однократный возврат | PASS |
| Q06 | `ProviderCallbackConcurrencyTests`: повторные CLICK/PAYME callbacks, один topup | PostgreSQL PASS; sandbox отдельно не выполнен |
| Q07 | `test_click.py`: `test_receipts_and_status_are_private_and_redirect_cannot_credit` | PASS для backend status lookup без callback; настоящий возврат из кабинета провайдера не выполнялся |
| Q08 | CLICK/PAYME protocol tests: подпись/сумма/transaction reuse, приватность payment; withdrawal API ownership | Локально PASS; внешние отрицательные ответы банка не получены |
| Q09 | `PaymeTests.test_cancellation_does_not_spend_held_funds`: −31007 после использования средств, paid сохраняется, баланс неотрицателен; `test_paid_cancellation_reverses_once` | Локально PASS для PAYME; внешняя отмена не выполнялась |
| Q10 | `WithdrawalConcurrencyTests`: два claim и claim против cancel | PostgreSQL PASS |
| Q11 | `WithdrawalStateTests`: processing cancel conflict, unknown→reconciliation_required без возврата/повторного перевода | PASS |
| Q12 | Повтор paid/rejected, уникальное внешнее подтверждение, одна проводка debit/refund | PostgreSQL и service tests PASS |
| Q13 | Contract/proposal chat/file/payment participant tests, scoped API tokens и audited staff access | PASS |
| Q14 | `test_security.py`, `test_withdrawals.py`, `test_contract_concurrency.py`: старый/чужой контакт, отозванная cookie, отсутствие CSRF | PASS |
| Q15 | Изолированный restore: файл сохранился, участник 200, посторонний 404, публичный URL 404 | Restore PASS; production redeploy **не выполнен** |
| Q16 | `test_timeliness_uses_accepted_submission_and_excludes_ambiguous`, immutable deadline/version amendment test | PASS |
| Q17 | `test_clone_preserves_history_finances_and_revalidates_deadline`: draft→publish→новый отклик→новый договор, старые snapshots и деньги неизменны; clone proxy evidence | Полный API-сценарий PostgreSQL PASS; отдельный браузерный сценарий отмечен в frontend-протоколе |
| Q18 | Закрытый proposal conversation: unread/report/ownership; отсутствие договора и ledger изменений | PASS |
| Q19 | 12/48 профилей, 3/3 SQL, timings/payload/EXPLAIN в полном PostgreSQL логе | PASS на локальном наборе |
| Q20 | Unit tests валидаторов backend/frontend; 7 фактических backend startup subprocess checks | Backend PASS. Повтор отрицательного frontend build/start заблокирован автоматической проверкой разрешений; Railway ENV не проверены |
| Q21 | RU/UZ/ЎЗ/EN × light/dark × 390/740/1440 плюс 320; 384 core + 160 guest сочетаний | Layout PASS по измеренной ширине; полная матрица состояний и Figma не подтверждены |
| Q22 | Стабильный ключ операции до известного результата; backend запрещает повтор с изменёнными параметрами; реальный browser→backend commit→разрыв ответа→reload→повтор | Локально PASS: прежний UUID, одна заявка и один дебет; отдельно fund повторён по ID договора без второго hold. Провайдерские переводы не выполнялись |
| Q23 | `SharedLimiterProcessTests.test_two_processes_share_one_atomic_counter`; spoofed forwarded IP и limiter failure tests | PostgreSQL PASS на двух процессах |
| Q24 | Backup/restore JSON, identical money/file evidence, текущие миграции и release passport с backend/frontend SHA | Изолированная проверка PASS; production SHA/restore и owner RPO/RTO **не подтверждены** |

Историческая совместимость проверена отдельно: тарифы 0/5/8% сохраняются как снимки; текущая политика не меняет старую комиссию. `test_payment_migrations.py` проводит искусственные исторические paid/rejected/pending и ledger через миграции, сохраняет идентификаторы, суммы, даты и связи; pending становится `reconciliation_required`, обратный шаг inventory не делает его отменяемым.

Старый код `556ed75` запущен на отдельной копии искусственной PostgreSQL с SELECT-only ролью и read-only транзакциями. Схема, все таблицы, история миграций и денежные хеши до/после совпали. Вместе с тем старая версия отклоняет новую сессию (401 вместо 200) и показывает резерв вывода 0 вместо 22 000 при новых статусах. Полный откат на неё **несовместим**. Новая схема и приватные файлы сохраняются; для восстановления нужен совместимый исправленный backend. Старые денежные/auth/admin/workers/callback записи не разрешаются. Это зафиксировано в [release-инструкции](audit-release.md); проверка production-копии не выполнялась.

Payout references, подтверждения получателей и банковские evidence в Q10–Q12 синтетические. Сервис проверяет их наличие, целостность, область уникальности и полномочия оператора; подлинность реального перевода требует внешней сверки, выполненной оператором.

## Производительность и восстановление

| Профилей | SQL | p50 | p95 | Размер сериализованного ответа |
| --- | --- | --- | --- | --- |
| 12 | 3 | 10.15 мс | 14.77 мс | 8 411 байт |
| 48 | 3 | 21.33 мс | 31.62 мс | 34 891 байт |

Это шесть локальных замеров PostgreSQL queryset+serializer для каждого размера, с навыками/категориями. p95 взят методом ближайшего ранга (максимум при шести наблюдениях). HTTP, TLS, сеть и production нагрузка сюда не входят. SQL plan сохранён в протоколе; целевой SLO владельцем не утверждён.

В повторном целевом product suite после уточнения Q17 число запросов осталось 3/3, но p50/p95 для 12 профилей составили 15.00/114.12 мс, для 48 — 21.63/27.70 мс. Полный повторный результат также сохранён. Разброс на маленькой выборке при параллельной браузерной проверке/сборке не позволяет заявлять устойчивую задержку production.

В итоговом полном наборе Python 3.14.7 запросов также 3/3: для 12 профилей p50/p95 10.44/14.94 мс, 8 405 байт; для 48 — 18.80/25.42 мс, 34 891 байт.

Совместное восстановление изолированной искусственной БД и одного приватного файла: backup 0.688 сек, restore 1.948 сек. Сверка `opening + ledger`, reserve/gross/net/fee/refund прошла независимо от сравнения snapshots. Денежный SHA256 до/после: `60fffe8cd21b63447dd230beaa89b95cc2c6948fe835ce3621becde98051bf95`. Сами dump, архив и тестовые секреты в отчёт не включены. Эти длительности не являются согласованными RPO/RTO и не оценивают объём действующей базы.

## Приёмка интерфейса и её пределы

Layout-протокол проверял завершённую загрузку сессии/preferences, язык, тему, заголовок и scrollWidth на 544 сочетаниях. Выборочные функциональные проверки подтвердили cookie/CSRF/logout, MFA/admin proxy, согласие существующего пользователя, loading/empty каталога, пустой кошелёк, длинный текст/сумму, guest redirect, 404, видимый focus, сохранение textarea при потере связи и успешный повтор.

Основные loading/empty/error/network/отказ доступа/retry состояния проверены отдельно от layout, в том числе формы входа, регистрации (загрузка условий), восстановления и выбора роли. Сохранность некоторых полей и полный POST регистрации через браузер не подтверждены. Native date в browser clone драйвер не смог достоверно заполнить; полный API-сценарий clone→новый найм прошёл. Сохранение невалидного email через DOM также не подтверждено. Полный keyboard-only/assistive technology аудит не заявляется. Эти ограничения не скрыты за числом layout-проверок; подробности и снимки находятся в frontend-протоколе.

Финансовый Q22 выполнен на отдельной синтетической SQLite через настоящий браузер и backend. QAproxy получил успешный ответ после commit и намеренно закрыл соединение, не передав ответ UI. Повтор fund оставил один hold на 250 000 UZS. При создании заявки на вывод 1 000 UZS браузер показал UUID `ba181b3d-f761-4ba9-96bf-8754c05d48a2`; после reload сохранил тот же ключ и заблокированные параметры. Повтор дал прежнюю заявку №4 в pending: одна проводка −1 000 UZS, баланс 749 000 = opening 1 000 000 + ledger −251 000. Ранняя проверка БД во время искусственной задержки ещё видела 0 заявок; итоговые проверки выполнялись после получения ошибки и после повтора. Ни claim, ни внешний перевод не выполнялись. Конкурентность отдельно подтверждена PostgreSQL suite; локальный браузерный сценарий не заменяет sandbox CLICK/PAYME.

Автоматическая проверка разрешений отклонила повтор негативного frontend build/start и запуск отдельного standalone сервера, сообщив только `blocked by policy`. Обычная сборка и unit validator прошли; повтор отклонённых действий обходным способом не выполнялся. Успешный standalone start данным протоколом не подтверждается.

После ответа владельца доступ к встроенному браузеру восстановлен в основном задании. Выполнена дополнительная серия реальных UI-проверок через локальный fault proxy: loading, 502/503, 401/403, разрыв TCP, ручной повтор и видимый focus на основных экранах. Формы входа, регистрации, восстановления и выбора роли также проверены с ошибками; роль сохраняет выбор, повтор восстановления доходит до ввода кода. Реальные пустые результаты каталога, разделы профиля и чат проверены отдельно. Методика, исходные неудачные попытки и успешные повторные проверки сохранены в [root-state-checks.json](audit-frontend/root-state-checks.json) и [таблице по экранам](audit-frontend/screen-state-checklist.md). Отказы создавались только на изолированном backend с искусственными данными.

## Реквизиты и сроки, предоставленные владельцем

Владелец сообщил: юридическое название `"Brinex" MCHJ`, ИНН `313183897`, адрес `BIY 1/23`, email поддержки `brinexmchj@gmail.com`. На вопрос о сроках ответа поддержки, споров, возврата и вывода ответил «48 часов»; это значение внесено для каждого перечисленного срока. Точность адреса сохранена как предоставлена; дополнительные сведения не выдуманы.

Текущая редакция: `mvp-operator-48h-2026-09-13-v3`. Новые согласия связаны с обновлёнными данными и хешем; старые snapshots не переписаны. Предоставление реквизитов и сроков не подменяет юридическое согласование текста и проверку платёжной схемы, поэтому `approved:false` сохранён. Владелец отдельно подтвердил: пароль БД **не сменён**.

## Внешние пункты, которые остаются открытыми

1. **SEC-01:** владелец подтвердил отсутствие смены пароля. Нужно отозвать опубликованный секрет, обновить app/workers, проверить старый доступ, журналы и отдельную ограниченную runtime-роль. Значения секретов в чат не нужны.
2. **OPS-02 / Q15 / Q24:** владелец подтверждает согласованный deployment обеих частей, применённые миграции, persistent storage после redeploy, offsite backup и restore действующей выборки, мониторинг и доставку alerts; утверждает RPO/RTO. Указанные Railway URL не удалось проверить инструментом; это не означает, что сервисы недоступны.
3. **PAY-03:** нужен разрешённый sandbox CLICK/PAYME и протокол с тестовыми operation ID, включая чеки, callback delays/cancel и worker recovery. Локальные protocol tests сохранены, но не заменяют кабинет провайдера.
4. **GOV-01:** реквизиты и сроки уже внесены. Остаются утверждённые тексты, проверка местным юристом/провайдером, включая пользователей 16–17 лет и схему денег, и фактическая доставка обращения на предоставленный email. Возрастная политика не менялась. Письмо в поддержку без отдельного разрешения не отправлялось.
5. **TRUST-01 / SEC-02 / SEC-03:** проверить реальные каналы доставки, production cookies/HTTPS, operator MFA enrollment, отзыв legacy и доверенный ingress. Прокси удаляет неподтверждённый X-Forwarded-For: это предотвращает подмену, но без согласованной ingress-конфигурации общий IP может ограничивать несколько пользователей вместе.
6. **UI-01 / DOC-01:** доступ к живому Figma `yNkx3NWsQEradXkliwP4jZ` не получен: коннектор вернул отсутствие edit access. Нужны визуальное сопоставление с исходным макетом, финальная языковая/дизайнерская приёмка и подтверждение прав на используемые коммерческие шрифты. Локальные экспорты и font copyright сами по себе этих прав не подтверждают.

Новые реальные финансовые операции по умолчанию отключены (`REAL_MONEY_ENABLED=false`). Даже включение одного флага не обходит неутверждённый legal manifest. Обработка подтверждённых callbacks ранее созданных платежей сохраняется. Внешние пункты не помечены выполненными и не дают автоматического разрешения на коммерческий запуск.
