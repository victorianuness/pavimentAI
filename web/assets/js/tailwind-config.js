// Configuração do Tailwind (CDN) compartilhada por TODAS as páginas.
// Carregar depois do <script src="https://cdn.tailwindcss.com"></script>.
// Para usar a cor da marca: bg-brand-600, text-brand-700, border-brand-200, etc.
tailwind.config = {
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f2faf5',
          100: '#e0f3e7',
          200: '#c1e6cf',
          300: '#93d2ae',
          400: '#5bb787',
          500: '#34a06b',
          600: '#1f8556',
          700: '#196a46',
          800: '#16543a',
          900: '#134531',
        },
        ink: {
          DEFAULT: '#14231b', // texto principal (preto esverdeado)
          soft: '#5b6b62',    // texto secundário
          faint: '#8a9a91',   // legendas
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
