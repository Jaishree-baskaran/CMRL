/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Noto Sans"', 'sans-serif'],
      },
      colors: {
        brand: {
          50: '#f5f7fa',
          100: '#eaeef4',
          500: '#0052cc',
          600: '#0043a4',
          900: '#0c2340',
        }
      }
    },
  },
  plugins: [],
}
