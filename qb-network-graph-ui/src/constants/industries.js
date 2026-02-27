import { QB } from './colors';

/** NAICS code → industry metadata */
export const INDUSTRIES = {
  '236220': { label: 'Commercial Building',  sector: 'Construction',  color: QB.green },
  '238210': { label: 'Electrical',           sector: 'Construction',  color: QB.cyan },
  '238220': { label: 'Plumbing & HVAC',     sector: 'Construction',  color: QB.purple },
  '238910': { label: 'Site Preparation',     sector: 'Construction',  color: QB.orange },
  '423220': { label: 'Home Furnishings',     sector: 'Wholesale',     color: '#a855f7' },
  '423310': { label: 'Lumber & Wood',        sector: 'Wholesale',     color: '#16a34a' },
  '423320': { label: 'Masonry Materials',    sector: 'Wholesale',     color: '#ca8a04' },
  '423330': { label: 'Roofing & Siding',     sector: 'Wholesale',     color: '#ea580c' },
  '423510': { label: 'Metal Supplies',       sector: 'Wholesale',     color: '#9333ea' },
  '423610': { label: 'Electrical Supplies',  sector: 'Wholesale',     color: '#0284c7' },
  '423710': { label: 'Hardware',             sector: 'Wholesale',     color: '#7c3aed' },
  '423720': { label: 'Plumbing Supplies',    sector: 'Wholesale',     color: '#6d28d9' },
  '423730': { label: 'HVAC Supplies',        sector: 'Wholesale',     color: '#2563eb' },
  '531210': { label: 'Office Real Estate',   sector: 'Real Estate',   color: '#059669' },
  '531311': { label: 'Property Management',  sector: 'Real Estate',   color: '#0d9488' },
  '532412': { label: 'Equipment Rental',     sector: 'Rental',        color: '#d97706' },
  '541512': { label: 'IT Services',          sector: 'Technology',    color: QB.link },
  '541330': { label: 'Engineering',          sector: 'Professional',  color: '#dc2626' },
  '561730': { label: 'Landscaping',          sector: 'Services',      color: '#15803d' },
  '562111': { label: 'Waste Collection',     sector: 'Services',      color: '#71717a' },
  '722511': { label: 'Restaurants',          sector: 'Food Service',  color: '#e11d48' },
};

/** Safe industry lookup with fallback */
export const getIndustry = (naicsCode) =>
  INDUSTRIES[naicsCode] || { label: 'Unknown', sector: 'Other', color: '#999' };
