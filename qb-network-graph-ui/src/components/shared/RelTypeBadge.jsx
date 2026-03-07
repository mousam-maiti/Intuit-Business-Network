import { QB } from '@/constants/colors';

export function RelTypeBadge({ type, size = 'sm' }) {
  const isVendor = type === 'vendor';
  return (
    <span
      className="badge"
      style={{
        backgroundColor: isVendor ? QB.purpleLight : QB.greenLight,
        color: isVendor ? QB.purpleDark : QB.greenDark,
        fontSize: size === 'xs' ? '9px' : '10px',
      }}
    >
      {isVendor ? '\u2190 Vendor' : '\u2192 Client'}
    </span>
  );
}
