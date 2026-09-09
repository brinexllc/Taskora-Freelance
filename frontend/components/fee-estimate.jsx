'use client';
import { useApp } from '@/components/app-providers';
import { money } from '@/lib/i18n';
import { feePreview } from '@/lib/fee-preview';
export function FeeEstimate({ amount, policy }) {
  const { t, language } = useApp();
  const preview = policy && feePreview(amount, policy.freelancer_fee_percent);
  if (!policy) return null;
  return (
    <div className="fee-estimate">
      <strong>{t('feeEstimate')}</strong>
      <p>
        {t('freelancerCommission')}: {policy.freelancer_fee_percent}%
        {preview ? ` · ${money(preview.fee, language)}` : ''}
      </p>
      {preview && (
        <p>
          {t('netAmount')}: <strong>{money(preview.net, language)}</strong> ·{' '}
          {t('customerReserves')}: {money(amount, language)}
        </p>
      )}
      <p>{t('customerCommission')}: {policy.customer_fee_percent}%</p>
      <p className="muted">{t('feeEstimateHint')}</p>
    </div>
  );
}
