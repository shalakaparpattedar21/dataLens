/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: { ink: '#142338', muted: '#66758a', mist: '#f5f7fb', brand: '#4759d8', primary: 'var(--primary)', success: 'var(--success)', warning: 'var(--warning)', error: 'var(--error)', info: 'var(--info)', mint: '#dff7ee' },
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'], serif: ['"Playfair Display"', 'Georgia', 'serif'] },
      fontSize: { xs: ['13px', '1.5'], sm: ['15px', '1.55'], base: ['16px', '1.6'] },
    },
  },
  plugins: [],
}
