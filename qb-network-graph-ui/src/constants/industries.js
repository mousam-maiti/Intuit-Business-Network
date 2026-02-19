import { QB } from './colors';

/** NAICS code → industry metadata */
export const INDUSTRIES = {
  '238220': { label: 'Plumbing & HVAC',     sector: 'Construction',  color: QB.purple },
  '238210': { label: 'Electrical',           sector: 'Construction',  color: QB.cyan },
  '423720': { label: 'Plumbing Supplies',    sector: 'Wholesale',     color: '#7c3aed' },
  '541512': { label: 'IT Services',          sector: 'Technology',    color: QB.link },
  '236220': { label: 'Commercial Building',  sector: 'Construction',  color: QB.green },
  '423510': { label: 'Metal Supplies',       sector: 'Wholesale',     color: '#9333ea' },
  '541330': { label: 'Engineering',          sector: 'Professional',  color: '#dc2626' },
  '238910': { label: 'Site Preparation',     sector: 'Construction',  color: QB.orange },
};

/** Safe industry lookup with fallback */
export const getIndustry = (naicsCode) =>
  INDUSTRIES[naicsCode] || { label: 'Unknown', sector: 'Other', color: '#999' };
