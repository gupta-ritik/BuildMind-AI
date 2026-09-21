/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: '#0b0d10',
        panel: '#13161b',
        border: '#22262e',
        accent: '#4f8cff',
        success: '#3ecf8e',
        danger: '#f2545b',
        warn: '#e2a33d',
        muted: '#8b93a1',
      },
    },
  },
  plugins: [],
};
