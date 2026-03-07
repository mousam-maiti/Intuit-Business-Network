/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        qb: {
          green:        '#2CA01C',
          'green-dark': '#108000',
          'green-light':'#D4F7D0',
          teal:         '#0097A7',
          'teal-dark':  '#006B76',
          'teal-light': '#E0F4F5',
          cyan:         '#00B4D8',
          orange:       '#E8710A',
          'orange-light':'#FFF3E0',
          red:          '#DC2626',
          'red-light':  '#FEE2E2',
          link:         '#0077C5',
          dormant:      '#C4C4C4',
          sidebar:      '#1B2028',
          'sidebar-hover':'#2A313B',
          'sidebar-active':'#343D49',
          'content-bg': '#F4F5F7',
          'card-bg':    '#FFFFFF',
          'card-border':'#E3E8EE',
          'text-primary':'#393A3D',
          'text-secondary':'#6B6C72',
          'text-muted': '#8C8C8C',
        },
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
