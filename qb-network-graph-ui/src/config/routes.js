/**
 * Route definitions for the app.
 * Each route maps a path to a sidebar nav item.
 */
export const ROUTES = [
  { path: '/',           id: 'dashboard', label: 'Dashboard' },
  { path: '/network',    id: 'network',   label: 'Business network' },
  { path: '/search',     id: 'search',    label: 'Search network' },
  { path: '/review',     id: 'review',    label: 'Match review' },
  { path: '/lineage',    id: 'lineage',   label: 'Connection lineage' },
  { path: '/assist',     id: 'assist',    label: 'Intuit Assist' },
];

/** Map view id → path for programmatic navigation */
export const viewToPath = Object.fromEntries(ROUTES.map((r) => [r.id, r.path]));
