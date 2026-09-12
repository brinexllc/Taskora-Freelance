'use client';
import { useState } from 'react';
import { useApp } from '@/components/app-providers';
import { Field } from '@/components/taskora-ui';
export const acceptanceKeys = [
  'acceptance_criteria',
  'demonstration_method',
  'test_scenario',
];
export function AcceptanceFields({ value, onChange, required = false }) {
  const { t } = useApp();
  return (
    <fieldset className="acceptance-fields">
      <legend>{t('acceptance_criteria')}</legend>
      {acceptanceKeys.map((key) => (
        <Field label={t(key)} key={key}>
          <textarea
            value={value[key] || ''}
            onChange={(e) => onChange(key, e.target.value)}
            required={required}
            maxLength={5000}
          />
        </Field>
      ))}
      <Field label={t('review_days')}>
        <input
          type="number"
          min={1}
          max={30}
          required
          value={value.review_days ?? 3}
          onChange={(e) => onChange('review_days', Number(e.target.value))}
        />
      </Field>
    </fieldset>
  );
}
export function AcceptanceTerms({ contract, act, busy }) {
  const { t } = useApp();
  const [value, setValue] = useState(
    Object.fromEntries(
      [...acceptanceKeys, 'review_days'].map((key) => [key, contract[key]]),
    ),
  );
  return (
    <section className="t-card">
      <h2>{t('acceptance_criteria')}</h2>
      <dl>
        {acceptanceKeys.map((key) => (
          <div key={key}>
            <dt>{t(key)}</dt>
            <dd className="preserve-lines">{contract[key] || '—'}</dd>
          </div>
        ))}
        <div>
          <dt>{t('review_days')}</dt>
          <dd>{contract.review_days ?? '—'}</dd>
        </div>
      </dl>
      <p>{t('noAutomaticPayment')}</p>
      {[
        'draft',
        'customer_accepted',
        'freelancer_accepted',
        'awaiting_funding',
      ].includes(contract.status) && (
        <details>
          <summary>{t('amendTerms')}</summary>
          <form
            className="t-form"
            onSubmit={async (e) => {
              e.preventDefault();
              await act(
                'amend',
                { ...value, expected_version: contract.version },
                'saved',
              );
            }}
          >
            <AcceptanceFields
              value={value}
              required
              onChange={(key, next) =>
                setValue((current) => ({ ...current, [key]: next }))
              }
            />
            <button className="t-button secondary" disabled={busy}>
              {t('amendTerms')}
            </button>
          </form>
        </details>
      )}
    </section>
  );
}
