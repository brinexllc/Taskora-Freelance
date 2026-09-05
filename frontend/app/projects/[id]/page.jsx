'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { ProjectEditor } from '@/components/project-editor';
import { apiRequest, createProposal, downloadFile } from '@/lib/api';
import {
  Empty,
  Field,
  Notice,
  PageShell,
  Pager,
  RemoteState,
  Status,
  useRemote,
} from '@/components/taskora-ui';
import { date, money } from '@/lib/i18n';
export default function ProjectDetailsPage() {
  const { id } = useParams();
  const { t, language, session, ready } = useApp();
  const remote = useRemote(ready && id ? `projects/${id}` : null, {
    token: session?.token,
  });
  const [page, setPage] = useState(1);
  const proposals = useRemote(ready && session?.token ? 'proposals' : null, {
    token: session?.token,
    query: { project: id, page },
  });
  const [form, setForm] = useState({
      cover_letter: '',
      amount: '',
      delivery_days: '',
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const project = remote.data;
  const owner = project?.owner === session?.user?.id;
  const alreadyApplied = proposals.data?.results.some(
    (p) => p.freelancer === session?.user?.id,
  );
  const change = (key) => (e) =>
    setForm((current) => ({ ...current, [key]: e.target.value }));
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await createProposal({ ...form, project: Number(id) }, session.token);
      setNotice(t('sent'));
      proposals.reload();
      remote.reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function decide(proposal, action) {
    setBusy(true);
    setError('');
    try {
      const data = await apiRequest(`proposals/${proposal}/${action}`, {
        method: 'POST',
        token: session.token,
      });
      if (action === 'accept') window.location.assign(`/contracts/${data.id}`);
      else proposals.reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <PageShell>
      <Link className="back-link" href="/projects">
        ← {t('orders')}
      </Link>
      <RemoteState remote={remote}>
        {project && (
          <>
            <section className="t-card">
              <div className="row-between">
                <span className="eyebrow">{t(project.category)}</span>
                <Status value={project.status} />
              </div>
              <h1>{project.title}</h1>
              <div className="skill-tags">
                {project.skills.map((skill) => (
                  <span key={skill}>{skill}</span>
                ))}
              </div>
              <p className="preserve-lines">{project.description}</p>
              <dl className="detail-list">
                <div>
                  <dt>{t('budget')}</dt>
                  <dd>
                    {money(project.budget_min, language)} –{' '}
                    {money(project.budget_max, language)}
                  </dd>
                </div>
                <div>
                  <dt>{t('client')}</dt>
                  <dd>
                    {project.client_name}
                    {project.client_company
                      ? ` · ${project.client_company}`
                      : ''}
                  </dd>
                </div>
                <div>
                  <dt>{t('deadline')}</dt>
                  <dd>{date(project.deadline, language)}</dd>
                </div>
                <div>
                  <dt>{t('proposals')}</dt>
                  <dd>{project.proposal_count}</dd>
                </div>
              </dl>
              {project.contract_id && (
                <Link
                  className="t-button"
                  href={`/contracts/${project.contract_id}`}
                >
                  {t('viewContract')}
                </Link>
              )}
            </section>
            {owner &&
              ['draft', 'published'].includes(project.status) &&
              !project.proposal_count && (
                <section className="t-card">
                  <details>
                    <summary>{t('editProject')}</summary>
                    <ProjectEditor project={project} onSaved={remote.reload} />
                  </details>
                  <button
                    className="text-link danger"
                    disabled={busy}
                    onClick={async () => {
                      if (!window.confirm(t('confirmCancelProject'))) return;
                      setBusy(true);
                      try {
                        await apiRequest(`projects/${id}`, {
                          method: 'DELETE',
                          token: session.token,
                        });
                        remote.reload();
                      } catch (e) {
                        setError(e.message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    {t('cancelProject')}
                  </button>
                </section>
              )}
            {!!project.attachments?.length && (
              <section className="t-card">
                <h2>{t('attachments')}</h2>
                {project.attachments.map((a) => (
                  <button
                    key={a.id}
                    className="text-link"
                    onClick={() =>
                      downloadFile(
                        `projects/${id}/attachments/${a.id}/download`,
                        session?.token,
                        a.filename,
                      ).catch((e) => setError(e.message))
                    }
                  >
                    {a.filename}
                  </button>
                ))}
              </section>
            )}
            <Notice error>{error}</Notice>
            <Notice>{notice}</Notice>
            {session?.token && (
              <RemoteState remote={proposals}>
                {owner ? (
                  <section className="t-card">
                    <h2>{t('proposals')}</h2>
                    {proposals.data?.results.length ? (
                      proposals.data.results.map((proposal) => (
                        <article className="t-card" key={proposal.id}>
                          <div className="row-between">
                            <h3>{proposal.freelancer_name}</h3>
                            <Status value={proposal.status} />
                            {proposal.status === 'pending' && (
                              <button
                                className="text-link"
                                disabled={busy}
                                onClick={() => decide(proposal.id, 'withdraw')}
                              >
                                {t('withdrawProposal')}
                              </button>
                            )}
                          </div>
                          <p className="preserve-lines">
                            {proposal.cover_letter}
                          </p>
                          <p>
                            {money(proposal.amount, language)} ·{' '}
                            {proposal.delivery_days} {t('days')}
                          </p>
                          {proposal.status === 'pending' &&
                            project.status === 'published' && (
                              <div className="actions">
                                <button
                                  className="t-button"
                                  disabled={busy}
                                  onClick={() => decide(proposal.id, 'accept')}
                                >
                                  {t('accept')}
                                </button>
                                <button
                                  className="t-button secondary"
                                  disabled={busy}
                                  onClick={() => decide(proposal.id, 'reject')}
                                >
                                  {t('reject')}
                                </button>
                              </div>
                            )}
                          {proposal.contract_id && (
                            <Link
                              className="text-link"
                              href={`/contracts/${proposal.contract_id}`}
                            >
                              {t('viewContract')}
                            </Link>
                          )}
                        </article>
                      ))
                    ) : (
                      <Empty text={t('noProposals')} />
                    )}
                    <Pager
                      data={proposals.data}
                      page={page}
                      onChange={setPage}
                    />
                  </section>
                ) : (
                  proposals.data?.results.map((proposal) => (
                    <section className="t-card" key={proposal.id}>
                      <h2>{t('myProposals')}</h2>
                      <Status value={proposal.status} />
                      {proposal.status === 'pending' && (
                        <button
                          className="text-link"
                          disabled={busy}
                          onClick={() => decide(proposal.id, 'withdraw')}
                        >
                          {t('withdrawProposal')}
                        </button>
                      )}
                      <p className="preserve-lines">{proposal.cover_letter}</p>
                      <p>
                        {money(proposal.amount, language)} ·{' '}
                        {proposal.delivery_days} {t('days')}
                      </p>
                      {proposal.contract_id && (
                        <Link
                          className="t-button"
                          href={`/contracts/${proposal.contract_id}`}
                        >
                          {t('viewContract')}
                        </Link>
                      )}
                    </section>
                  ))
                )}
              </RemoteState>
            )}
            {!owner && project.status === 'published' && !alreadyApplied && (
              <section className="t-card" id="apply">
                {!session?.user ? (
                  <>
                    <p>{t('loginToApply')}</p>
                    <Link className="t-button" href="/login">
                      {t('login')}
                    </Link>
                  </>
                ) : session.user.role !== 'freelancer' ? (
                  <>
                    <p>{t('freelancerOnly')}</p>
                    <Link
                      className="t-button secondary"
                      href="/dashboard?view=settings"
                    >
                      {t('goSettings')}
                    </Link>
                  </>
                ) : (
                  <>
                    <h2>{t('apply')}</h2>
                    <form className="t-form" onSubmit={submit}>
                      <Field label={t('coverLetter')}>
                        <textarea
                          value={form.cover_letter}
                          onChange={change('cover_letter')}
                          required
                        />
                      </Field>
                      <div className="form-columns">
                        <Field label={t('amount')}>
                          <input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={form.amount}
                            onChange={change('amount')}
                            required
                          />
                        </Field>
                        <Field label={t('deliveryDays')}>
                          <input
                            type="number"
                            min="1"
                            max="365"
                            value={form.delivery_days}
                            onChange={change('delivery_days')}
                            required
                          />
                        </Field>
                      </div>
                      <button
                        className="t-button"
                        disabled={busy || proposals.loading}
                      >
                        {busy ? t('loading') : t('send')}
                      </button>
                    </form>
                  </>
                )}
              </section>
            )}
          </>
        )}
      </RemoteState>
    </PageShell>
  );
}
