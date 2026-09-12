'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { FileText, Download, MapPin } from 'lucide-react';
import { useApp } from '@/components/app-providers';
import { ProposalDiscussion } from '@/components/proposal-discussion';
import { ProjectClone } from '@/components/project-clone';
import { ProjectEditor } from '@/components/project-editor';
import { FeeEstimate } from '@/components/fee-estimate';
import { Chat } from '@/components/contract-workspace';
import { feePreview } from '@/lib/fee-preview';
import { apiRequest, createProposal, downloadFile } from '@/lib/api';
import {
  Empty,
  Avatar,
  Field,
  Notice,
  PageShell,
  Pager,
  ProjectProgress,
  RemoteState,
  Status,
  useRemote,
} from '@/components/taskora-ui';
import { date, money } from '@/lib/i18n';
export default function ProjectDetailsPage() {
  const { id } = useParams();
  const { t, language, session, ready } = useApp();
  const remote = useRemote(ready && id ? `projects/${id}` : null, {
    token: session?.authenticated,
  });
  const [page, setPage] = useState(1);
  const fees = useRemote('platform-fees');
  const proposals = useRemote(
    ready && session?.authenticated ? 'proposals' : null,
    {
      token: session?.authenticated,
      query: { project: id, page },
    },
  );
  const [form, setForm] = useState({
      cover_letter: '',
      amount: '',
      delivery_days: '',
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const project = remote.data;
  const contract = useRemote(
    project?.contract_id && session?.authenticated
      ? `contracts/${project.contract_id}`
      : null,
    { token: session?.authenticated },
  );
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
      await createProposal(
        {
          ...form,
          project: Number(id),
          expected_fee_policy_version: fees.data.policy_version,
        },
        session.authenticated,
      );
      setNotice(t('sent'));
      proposals.reload();
      remote.reload();
    } catch (err) {
      setError(
        err.code === 'FEE_POLICY_CHANGED' ? t('feePolicyChanged') : err.message,
      );
      if (err.code === 'FEE_POLICY_CHANGED') fees.reload();
    } finally {
      setBusy(false);
    }
  }
  async function decide(proposal, action) {
    if (action === 'accept') {
      const offer = proposals.data.results.find((p) => p.id === proposal);
      const preview = feePreview(
        offer.amount,
        fees.data.freelancer_fee_percent,
      );
      if (
        !window.confirm(
          `${t('customerReserves')}: ${money(offer.amount, language)}\n${t('platformFee')}: ${fees.data.freelancer_fee_percent}% (${money(preview.fee, language)})\n${t('netAmount')}: ${money(preview.net, language)}`,
        )
      )
        return;
    }
    setBusy(true);
    setError('');
    try {
      const data = await apiRequest(`proposals/${proposal}/${action}`, {
        method: 'POST',
        token: session.authenticated,
        body:
          action === 'accept'
            ? { expected_fee_policy_version: fees.data.policy_version }
            : undefined,
      });
      if (action === 'accept') window.location.assign(`/contracts/${data.id}`);
      else proposals.reload();
    } catch (err) {
      setError(
        err.code === 'FEE_POLICY_CHANGED' ? t('feePolicyChanged') : err.message,
      );
      if (err.code === 'FEE_POLICY_CHANGED') fees.reload();
    } finally {
      setBusy(false);
    }
  }
  return (
    <PageShell
      mobileTitle={t('project')}
      mobileStatus={project?.status}
      backHref="/dashboard?view=orders"
    >
      <Link className="back-link" href="/projects">
        ← {t('orders')}
      </Link>
      <RemoteState remote={remote}>
        {project && (
          <>
            <section className="t-card project-overview">
              <div className="row-between">
                <span className="eyebrow">{project.category_label}</span>
                <Status value={project.status} />
              </div>
              <h1>{project.title}</h1>
              <div className="project-client-card">
                <Avatar
                  profile={{
                    full_name: project.client_name,
                    avatar: project.client_avatar,
                  }}
                />
                <div>
                  <small>{t('client')}</small>
                  <strong>{project.client_name}</strong>
                  {project.client_location && (
                    <span>
                      <MapPin size={14} />
                      {project.client_location}
                    </span>
                  )}
                </div>
              </div>
              <div className="skill-tags">
                {project.skill_details.map((skill) => (
                  <span key={skill.id}>{skill.label}</span>
                ))}
              </div>
              {project.skills_unspecified && (
                <p className="muted">{t('technologiesDiscussed')}</p>
              )}
              <div className="project-description">
                <h2>{t('description')}</h2>
                <p className="preserve-lines">{project.description}</p>
                {project.skill_details.length > 0 && (
                  <>
                    <h2>{t('skills')}</h2>
                    <ul className="project-requirements">
                      {project.skill_details.map((skill) => (
                        <li key={skill.id}>{skill.label}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
              <dl className="detail-list">
                <div>
                  <dt>{t('budget')}</dt>
                  <dd>
                    {money(project.budget_min, language)}
                    {project.budget_min !== project.budget_max &&
                      ` – ${money(project.budget_max, language)}`}
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
              <div className="project-detail-progress">
                <ProjectProgress status={project.status} />
              </div>
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
              project.status === 'cancelled' &&
              (!contract.data || !Number(contract.data.escrow_amount)) && (
                <ProjectClone project={project} />
              )}
            {project.source_project && (
              <Link
                className="text-link"
                href={`/projects/${project.source_project}`}
              >
                {t('sourceProject')} #{project.source_project}
              </Link>
            )}
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
                          token: session.authenticated,
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
              <section className="t-card project-attachments">
                <h2>{t('attachments')}</h2>
                {project.attachments.map((a) => (
                  <button
                    key={a.id}
                    className="project-file-card"
                    onClick={() =>
                      downloadFile(
                        `projects/${id}/attachments/${a.id}/download`,
                        session?.authenticated,
                        a.filename,
                      ).catch((e) => setError(e.message))
                    }
                  >
                    <FileText size={24} />
                    <span>{a.filename}</span>
                    <Download size={18} />
                  </button>
                ))}
              </section>
            )}
            {contract.data && (
              <section className="t-card project-stages">
                <h2>{t('projectStages')}</h2>
                <ol className="project-stage-list">
                  {contract.data.events
                    .filter((e) =>
                      [
                        'created',
                        'signed',
                        'escrow_hold',
                        'submitted',
                        'revision',
                        'settled',
                        'dispute_resolved',
                        'dispute_opened',
                        'cancelled',
                        'fee_revised',
                      ].includes(e.kind),
                    )
                    .map((e) => (
                      <li key={e.id}>
                        <span />
                        <div>
                          <strong>{e.description}</strong>
                          <time>{date(e.created_at, language)}</time>
                        </div>
                      </li>
                    ))}
                </ol>
              </section>
            )}
            {contract.data && <Chat contract={contract.data} />}
            <Notice error>{error}</Notice>
            <Notice error>{fees.error}</Notice>
            {fees.error && (
              <button type="button" className="text-link" onClick={fees.reload}>
                {t('retry')}
              </button>
            )}
            <Notice>{notice}</Notice>
            {session?.authenticated && (
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
                                  disabled={
                                    busy ||
                                    fees.loading ||
                                    !!fees.error ||
                                    !fees.data
                                  }
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
                          <ProposalDiscussion proposal={proposal} />
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
                      <ProposalDiscussion proposal={proposal} />
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
                      <FeeEstimate amount={form.amount} policy={fees.data} />
                      <button
                        className="t-button"
                        disabled={
                          busy ||
                          proposals.loading ||
                          fees.loading ||
                          !!fees.error ||
                          !fees.data
                        }
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
