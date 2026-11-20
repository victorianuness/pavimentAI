// Configuração do Tailwind (CDN) compartilhada por TODAS as páginas.
// Carregar depois do <script src="https://cdn.tailwindcss.com"></script>.
// Para usar a cor da marca: bg-brand-600, text-brand-700, border-brand-200, etc.
tailwind.config = {
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef4fb',
          100: '#dbe8f7',
          200: '#bfd3ed',
          300: '#9dbbe0',
          400: '#648bb9',
          500: '#315f9d',
          600: '#1f4f87',
          700: '#173d68',
          800: '#102f56',
          900: '#071a33',
        },
        ink: {
          DEFAULT: '#101c2d',
          soft: '#5b6877',
          faint: '#8995a4',
        },
        line: '#e3ebe6',      // bordas
        surface: '#f6faf7',   // fundos suaves
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
      },
    },
  },
};
