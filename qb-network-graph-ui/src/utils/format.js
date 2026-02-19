/** Format number as currency shorthand: $1.2M, $450K, $900 */
export const fmt = (n) =>
  n >= 1e6 ? '$' + (n / 1e6).toFixed(1) + 'M'
  : n >= 1e3 ? '$' + (n / 1e3).toFixed(0) + 'K'
  : '$' + n;

/** Format percentage: 0.91 → "91%" */
export const pct = (n) => Math.round(n * 100) + '%';
