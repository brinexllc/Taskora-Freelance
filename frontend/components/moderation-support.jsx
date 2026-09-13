'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import {
  Field,
  Notice,
  Pager,
  RemoteState,
  useRemote,
} from '@/components/taskora-ui';
import { apiRequest, apiErrorMessage, downloadFile } from '@/lib/api';
import { dateTime } from '@/lib/i18n';

const stages = {
  new: 'Новое',
  open: 'Открыто',
  submitted: 'Подано',
  in_review: 'Рассматривается',
  needs_information: 'Нужны сведения',
  waiting_user: 'Ожидает вашего ответа',
  resolved: 'Решено',
  approved: 'Подтверждено',
  rejected: 'Отклонено',
  revoked: 'Отозвано',
};

export function ReportButton({ objectType, objectId }) {
  const { session, t } = useApp();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  if (!session?.user) return null;
  return (
    <details className="moderation-report">
      <summary>Пожаловаться</summary>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError('');
          setNotice('');
          try {
            const report = await apiRequest('reports', {
              method: 'POST',
              body: { object_type: objectType, object_id: objectId, reason },
            });
            setNotice(
              `Жалоба №${report.id} передана администрации. Решение появится в уведомлениях.`,
            );
            setReason('');
          } catch (error) {
            setError(apiErrorMessage(error, t));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Причина жалобы">
          <textarea
            required
            minLength={10}
            maxLength={3000}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Опишите нарушение и обстоятельства"
          />
        </Field>
        <Notice error>{error}</Notice>
        <Notice>{notice}</Notice>
        <button className="t-button secondary" disabled={busy}>
          {busy ? 'Отправка…' : 'Отправить жалобу'}
        </button>
      </form>
    </details>
  );
}

export function SkillVerificationPanel() {
  const { session, t, language } = useApp();
  const [page, setPage] = useState(1);
  const applications = useRemote('skill-verifications', { query: { page } });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const skills = session.user.profile.skill_details || [];
  return (
    <section className="panel moderation-panel">
      <h2>Подтверждение навыков</h2>
      <p className="muted">
        Добавьте доказательства опыта. Решение и срок подтверждения появятся
        здесь после проверки администрацией.
      </p>
      {skills.length ? (
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const body = new FormData(form);
            if (!body.get('evidence_file')?.size) body.delete('evidence_file');
            setBusy(true);
            setError('');
            setNotice('');
            try {
              await apiRequest('skill-verifications', { method: 'POST', body });
              form.reset();
              applications.reload();
              setNotice(
                'Заявка принята. Доказательства доступны только вам и администрации.',
              );
            } catch (error) {
              setError(apiErrorMessage(error, t));
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="form-grid">
            <Field label="Навык">
              <select name="skill" required>
                {skills.map((skill) => (
                  <option key={skill.id} value={skill.id}>
                    {skill.label || skill.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Вид доказательства">
              <select name="evidence_type">
                <option value="portfolio">Портфолио</option>
                <option value="certificate">Сертификат</option>
                <option value="assessment">Проверка работы</option>
              </select>
            </Field>
            <Field label="Ссылка HTTPS">
              <input name="evidence_url" type="url" placeholder="https://…" />
            </Field>
            <Field label="Или защищённый файл, до 25 МБ">
              <input
                name="evidence_file"
                type="file"
                accept=".pdf,.zip,.png,.jpg,.jpeg,.webp,.txt,.docx"
              />
            </Field>
          </div>
          <Field label="Описание опыта">
            <textarea name="description" maxLength={3000} />
          </Field>
          <button className="t-button" disabled={busy}>
            {busy ? 'Отправка…' : 'Отправить на проверку'}
          </button>
        </form>
      ) : (
        <p>Сначала добавьте и сохраните навыки в профиле.</p>
      )}
      <Notice error>{error}</Notice>
      <Notice>{notice}</Notice>
      <RemoteState remote={applications}>
        {applications.data?.results.length ? (
          applications.data.results.map((item) => (
            <article className="moderation-record" key={item.id}>
              <strong>{item.skill_name}</strong>
              <span>{stages[item.status] || item.status}</span>
              <small>
                {dateTime(item.created_at, language)}
                {item.expires_at &&
                  ` · Действует до ${dateTime(item.expires_at, language)}`}
              </small>
              {item.decision && <p>{item.decision}</p>}
              {item.download_url && (
                <button
                  type="button"
                  className="t-button secondary"
                  onClick={async () => {
                    try {
                      await downloadFile(
                        `skill-verifications/${item.id}/download`,
                      );
                    } catch (error) {
                      setError(apiErrorMessage(error, t));
                    }
                  }}
                >
                  Скачать доказательство
                </button>
              )}
            </article>
          ))
        ) : (
          <p className="muted">Заявок пока нет.</p>
        )}
      </RemoteState>
      <Pager data={applications.data} page={page} onChange={setPage} />
    </section>
  );
}

export function SupportView() {
  const { t, language } = useApp();
  const search = useSearchParams();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(search.get('ticket') || '');
  const [messagePage, setMessagePage] = useState(1);
  const [reportPage, setReportPage] = useState(1);
  const tickets = useRemote('support-tickets', { query: { page } });
  const messages = useRemote(
    selected ? `support-tickets/${selected}/messages` : null,
    { query: { page: messagePage, page_size: 25 } },
  );
  const reports = useRemote('reports', {
    query: { page: reportPage, page_size: 25 },
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Поддержка Taskora</h1>
          <p className="dashboard-subtitle">
            Обращения, ответы администрации и статус ваших жалоб
          </p>
        </div>
        <button
          className="t-button secondary"
          onClick={() => {
            tickets.reload();
            messages.reload();
            reports.reload();
          }}
        >
          Обновить
        </button>
      </div>
      <Notice error>{error}</Notice>
      <div className="moderation-support-grid">
        <section className="panel moderation-panel">
          <h2>Новое обращение</h2>
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const values = new FormData(form);
              const contract = values.get('contract');
              setBusy(true);
              setError('');
              try {
                const ticket = await apiRequest('support-tickets', {
                  method: 'POST',
                  body: {
                    subject: values.get('subject'),
                    text: values.get('text'),
                    ...(contract ? { contract: Number(contract) } : {}),
                  },
                });
                form.reset();
                setSelected(String(ticket.id));
                setMessagePage(1);
                tickets.reload();
              } catch (error) {
                setError(apiErrorMessage(error, t));
              } finally {
                setBusy(false);
              }
            }}
          >
            <Field label="Тема">
              <input name="subject" required maxLength={180} />
            </Field>
            <Field label="Номер договора, если обращение связано со сделкой">
              <input
                name="contract"
                type="number"
                min="1"
                defaultValue={search.get('contract') || ''}
              />
            </Field>
            <Field label="Опишите вопрос">
              <textarea
                name="text"
                required
                minLength={10}
                maxLength={5000}
                rows={5}
              />
            </Field>
            <button className="t-button" disabled={busy}>
              {busy ? 'Отправка…' : 'Создать обращение'}
            </button>
          </form>
          <h2>Мои обращения</h2>
          <RemoteState remote={tickets}>
            {tickets.data?.results.length ? (
              tickets.data.results.map((ticket) => (
                <button
                  type="button"
                  className={`moderation-ticket ${String(ticket.id) === selected ? 'selected' : ''}`}
                  onClick={() => {
                    setSelected(String(ticket.id));
                    setMessagePage(1);
                  }}
                  key={ticket.id}
                >
                  <strong>
                    №{ticket.id} · {ticket.subject}
                  </strong>
                  <span>{stages[ticket.status]}</span>
                  <small>{dateTime(ticket.updated_at, language)}</small>
                </button>
              ))
            ) : (
              <p className="muted">Обращений пока нет.</p>
            )}
          </RemoteState>
          <Pager data={tickets.data} page={page} onChange={setPage} />
        </section>
        <section className="panel moderation-panel">
          <h2>
            {selected ? `Обращение №${selected}` : 'Переписка с поддержкой'}
          </h2>
          {selected ? (
            <>
              <RemoteState remote={messages}>
                {messages.data?.results.map((message) => (
                  <article
                    className={`moderation-record ${message.administration ? 'administration-reply' : ''}`}
                    key={message.id}
                  >
                    <strong>{message.author_label}</strong>
                    <small>{dateTime(message.created_at, language)}</small>
                    <p className="preserve-lines">{message.text}</p>
                  </article>
                ))}
              </RemoteState>
              <Pager
                data={messages.data}
                page={messagePage}
                onChange={setMessagePage}
              />
              <form
                onSubmit={async (event) => {
                  event.preventDefault();
                  const form = event.currentTarget;
                  const body = { text: new FormData(form).get('text') };
                  setBusy(true);
                  setError('');
                  try {
                    await apiRequest(`support-tickets/${selected}/messages`, {
                      method: 'POST',
                      body,
                    });
                    form.reset();
                    messages.reload();
                    tickets.reload();
                  } catch (error) {
                    setError(apiErrorMessage(error, t));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <Field label="Ваш ответ">
                  <textarea name="text" required maxLength={5000} />
                </Field>
                <button className="t-button" disabled={busy}>
                  Отправить ответ
                </button>
              </form>
            </>
          ) : (
            <p className="muted">
              Выберите обращение или создайте новое. Ответы администрации также
              появятся во внутренних уведомлениях.
            </p>
          )}
          <h2>Мои жалобы</h2>
          <RemoteState remote={reports}>
            {reports.data?.results.length ? (
              reports.data.results.map((report) => (
                <article className="moderation-record" key={report.id}>
                  <strong>Жалоба №{report.id}</strong>
                  <span>{stages[report.status]}</span>
                  <p>{report.reason}</p>
                  {report.decision && <p>Решение: {report.decision}</p>}
                </article>
              ))
            ) : (
              <p className="muted">
                Жалоб пока нет. Отправить жалобу можно из карточки заказа,
                профиля, отзыва или сообщения.
              </p>
            )}
          </RemoteState>
          <Pager
            data={reports.data}
            page={reportPage}
            onChange={setReportPage}
          />
        </section>
      </div>
      <p>
        <Link href="/dashboard?view=settings">
          Настройки и безопасность аккаунта
        </Link>
      </p>
    </>
  );
}
