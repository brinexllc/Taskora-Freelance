// Integer cents/basis points keep previews identical to backend Decimal ROUND_HALF_UP.
export function feePreview(amount, percent) {
  const parse = (value) => {
    const text = String(value ?? '');
    if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
    const [whole, fraction = ''] = text.split('.');
    return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  };
  const cents = parse(amount),
    rate = parse(percent);
  if (cents == null || rate == null || rate > 10000n) return null;
  const fee = (cents * rate + 5000n) / 10000n;
  const format = (value) =>
    `${value / 100n}.${String(value % 100n).padStart(2, '0')}`;
  return { fee: format(fee), net: format(cents - fee) };
}
