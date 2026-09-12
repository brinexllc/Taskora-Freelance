'use client';
import Link from 'next/link';
import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';
import {
  Award,
  BriefcaseBusiness,
  CheckCircle2,
  Clock3,
  MapPin,
  MessageSquare,
  Star,
} from 'lucide-react';
import { useApp } from '@/components/app-providers';
import {
  Avatar,
  Empty,
  Notice,
  Pager,
  RemoteState,
  RemoteFeedback,
  useRemote,
} from '@/components/taskora-ui';
import { date, money } from '@/lib/i18n';

export function ProfileShowcase({ profile }) {
  const { t, language, session } = useApp();
  const own = session?.user?.profile?.id === profile.id;
  const freelancer = profile.role === 'freelancer';
  const [page, setPage] = useState(1);
  const reviews = useRemote(
    freelancer ? `profiles/${profile.id}/reviews` : null,
    { query: { page } },
  );
  const [selectedWork, setSelectedWork] = useState(null);
  const [allWorks, setAllWorks] = useState(false);
  const [contactNotice, setContactNotice] = useState(false);
  const contracts = useRemote(
    !own && session?.authenticated ? 'contracts' : null,
    {
      token: session?.authenticated,
      query: { participant_profile: profile.id, page_size: 1 },
    },
  );
  const conversation = contracts.data?.results[0];
  const contact = own
    ? '/dashboard?view=settings'
    : !session?.authenticated
      ? '/login'
      : conversation
        ? `/dashboard?view=messages&contract=${conversation.id}`
        : null;
  const orderLink =
    session?.user?.role === 'client'
      ? '/projects/new'
      : '/dashboard?view=settings';
  const dialog = useRef(null);
  useEffect(() => {
    if (selectedWork) dialog.current?.showModal();
    else dialog.current?.close();
  }, [selectedWork]);
  return (
    <div className="profile-showcase">
      <section className="showcase-header">
        <div className="showcase-identity">
          <div className="showcase-avatar">
            <Avatar profile={profile} large />
            {freelancer && profile.available && (
              <span className="availability-dot" title={t('available')} />
            )}
          </div>
          <div>
            <h1>{profile.full_name}</h1>
            <p className="showcase-location">
              <span>@{profile.username}</span>
              {profile.location && (
                <>
                  <i /> <MapPin size={14} /> {profile.location}
                </>
              )}
            </p>
            <strong className="showcase-specialty">
              {profile.professional_title ||
                profile.skill_details
                  ?.slice(0, 2)
                  .map((s) => s.label)
                  .join(' & ') ||
                t(profile.role)}
            </strong>
            <p className="showcase-about">{profile.about || t('noAbout')}</p>
            {freelancer && Number(profile.rate) > 0 && (
              <p className="showcase-rate">
                {money(profile.rate, language)} / {t(profile.rate_unit)}
              </p>
            )}
            {profile.spoken_languages?.length > 0 && (
              <p className="showcase-languages">
                <strong>{t('spokenLanguages')}:</strong>{' '}
                {profile.spoken_languages.join(' · ')}
              </p>
            )}
          </div>
        </div>
        <div className="showcase-actions">
          {contact ? (
            <Link className="t-button secondary" href={contact}>
              {t(own ? 'editProfile' : 'writeMessage')}
            </Link>
          ) : (
            <button
              className="t-button secondary"
              disabled={contracts.loading || !!contracts.error}
              onClick={() => setContactNotice(true)}
            >
              {t('writeMessage')}
            </button>
          )}
          <Link
            className="t-button"
            href={own ? '/dashboard?view=orders' : orderLink}
          >
            {t(own ? 'orders' : 'createOrder')}
          </Link>
        </div>
      </section>
      {!own && session?.authenticated && <RemoteFeedback remote={contracts} />}
      <Notice>{contactNotice && t('chatAfterContract')}</Notice>
      {freelancer && (
        <>
          <div className="showcase-stats">
            {[
              [
                Star,
                'rating',
                profile.rating == null ? '—' : `★ ${profile.rating.toFixed(1)}`,
              ],
              [
                BriefcaseBusiness,
                'completedOrders',
                profile.completed_projects || 0,
              ],
              [
                CheckCircle2,
                'onTimeProjects',
                profile.on_time_percent == null
                  ? '—'
                  : `${profile.on_time_percent}%`,
              ],
              [Award, 'memberSince', date(profile.created_at, language)],
            ].map(([Icon, label, value]) => (
              <div key={label}>
                <span>{t(label)}</span>
                <Icon size={22} />
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <section className="showcase-skills">
            <h2>{t('skills')}</h2>
            <div className="skill-tags">
              {profile.skill_details?.length ? (
                profile.skill_details.map((s) => (
                  <span key={s.id}>{s.label}</span>
                ))
              ) : (
                <p className="muted">{t('empty')}</p>
              )}
            </div>
          </section>
          <section className="showcase-portfolio">
            <h2>{t('portfolio')}</h2>
            {profile.portfolio?.length ? (
              <div
                className={`showcase-portfolio-grid${allWorks ? ' show-all' : ''}`}
              >
                {profile.portfolio.map((item, index) => (
                  <article key={`${item.title}-${index}`}>
                    <button
                      className="portfolio-preview"
                      onClick={() => setSelectedWork(item)}
                      aria-label={`${t('details')}: ${item.title}`}
                    >
                      {item.image ? (
                        <Image
                          src={item.image}
                          width={640}
                          height={440}
                          alt={item.title}
                          unoptimized
                        />
                      ) : (
                        <BriefcaseBusiness size={36} />
                      )}
                    </button>
                    <span>{item.category}</span>
                    <h3>
                      <button onClick={() => setSelectedWork(item)}>
                        {item.title}
                      </button>
                    </h3>
                    {item.description && <p>{item.description}</p>}
                    <button
                      className="portfolio-view-link"
                      onClick={() => setSelectedWork(item)}
                    >
                      {t('details')} →
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <div className="showcase-empty">
                <Empty text={t('noPortfolio')} />
                {own && (
                  <Link
                    href="/dashboard?view=settings#portfolio"
                    className="text-link"
                  >
                    {t('addPortfolio')}
                  </Link>
                )}
              </div>
            )}
            {profile.portfolio?.length > 4 && !allWorks && (
              <button
                className="t-button secondary portfolio-show-all"
                onClick={() => setAllWorks(true)}
              >
                {t('viewAll')} →
              </button>
            )}
          </section>
          <section className="showcase-services">
            <h2>{t('services')}</h2>
            {profile.services?.length ? (
              <div className="showcase-services-grid">
                {profile.services.map((item, index) => (
                  <article key={`${item.title}-${index}`}>
                    <h3>{item.title}</h3>
                    <p>{item.description}</p>
                    <strong>{money(item.price, language)}</strong>
                    <div>
                      <span>
                        <Clock3 size={14} /> {item.delivery_days} {t('days')}
                      </span>
                      <Link
                        href={
                          own ? '/dashboard?view=settings#services' : orderLink
                        }
                      >
                        {t(own ? 'editProfile' : 'createOrder')}
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="showcase-empty">
                <Empty text={t('noServices')} />
                {own && (
                  <Link
                    href="/dashboard?view=settings#services"
                    className="text-link"
                  >
                    {t('addService')}
                  </Link>
                )}
              </div>
            )}
          </section>
          <section className="showcase-achievements">
            <h2>{t('achievements')}</h2>
            <div className="achievement-grid">
              {profile.verified_skills?.length ? (
                profile.verified_skills.map((skill) => (
                  <article key={skill}>
                    <Award size={28} />
                    <div>
                      <strong>{skill}</strong>
                      <p>{t('verifiedSkills')}</p>
                    </div>
                  </article>
                ))
              ) : (
                <p className="muted">{t('noVerified')}</p>
              )}
            </div>
          </section>
          <section className="showcase-reviews">
            <h2>{t('customerReviews')}</h2>
            <RemoteState remote={reviews}>
              {reviews.data?.results.length ? (
                reviews.data.results.map((item) => (
                  <article className="showcase-review" key={item.id}>
                    <div>
                      <span className="review-avatar">
                        {item.author_name?.slice(0, 1)}
                      </span>
                      <div>
                        <strong>{item.author_name}</strong>
                        <time>{date(item.created_at, language)}</time>
                      </div>
                      <span className="rating">{'★'.repeat(item.rating)}</span>
                    </div>
                    <p>{item.text}</p>
                  </article>
                ))
              ) : (
                <Empty text={t('noCustomerReviews')} />
              )}
              <Pager data={reviews.data} page={page} onChange={setPage} />
            </RemoteState>
          </section>
        </>
      )}
      {profile.professional_experience && (
        <section>
          <h2>{t('professionalExperience')}</h2>
          <p className="preserve-lines">{profile.professional_experience}</p>
        </section>
      )}
      <div className="showcase-bottom-cta">
        {contact ? (
          <Link className="t-button" href={contact}>
            <MessageSquare size={18} />{' '}
            {t(own ? 'editProfile' : 'writeMessage')}
          </Link>
        ) : (
          <button className="t-button" onClick={() => setContactNotice(true)}>
            <MessageSquare size={18} />
            {t('writeMessage')}
          </button>
        )}
      </div>
      <dialog
        ref={dialog}
        aria-label={selectedWork?.title}
        className="portfolio-modal"
        onCancel={() => setSelectedWork(null)}
      >
        {selectedWork && (
          <div>
            <button className="text-link" onClick={() => setSelectedWork(null)}>
              {t('close')}
            </button>
            <h2>{selectedWork.title}</h2>
            {selectedWork.image && (
              <Image
                src={selectedWork.image}
                alt={selectedWork.title}
                width={1200}
                height={900}
                unoptimized
              />
            )}
            <p>{selectedWork.description}</p>
            {selectedWork.url && (
              <a
                href={selectedWork.url}
                target="_blank"
                rel="noopener noreferrer"
                className="t-button"
              >
                {t('openProject')}
              </a>
            )}
          </div>
        )}
      </dialog>
    </div>
  );
}
