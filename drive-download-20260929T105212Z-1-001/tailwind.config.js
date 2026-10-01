/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#aa3bff',
        accent: '#c084fc',
        background: 'var(--bg)',
        foreground: 'var(--text)',
      },
    },
  },
  plugins: [],
};
