import type { Config } from 'tailwindcss'

const config: Config = {
  // Active le dark mode par classe .dark sur <html>
  darkMode: ['class'],

  content: [
    './src/**/*.{ts,tsx}',
    './index.html',
  ],

  theme: {
    extend: {
      // ---------------------------------------------------------
      // COULEURS — toutes mappées sur les CSS variables de tokens.css
      // Usage : bg-primary, text-muted-foreground, border-danger, etc.
      // ---------------------------------------------------------
      colors: {
        background: {
          DEFAULT: 'var(--background)',
          subtle:   'var(--background-subtle)',
        },
        foreground: 'var(--foreground)',

        card: {
          DEFAULT:    'var(--card)',
          foreground: 'var(--card-foreground)',
        },
        popover: {
          DEFAULT:    'var(--popover)',
          foreground: 'var(--popover-foreground)',
        },

        // Primary — Cerulean
        primary: {
          DEFAULT:    'var(--primary)',
          foreground: 'var(--primary-foreground)',
          subtle:     'var(--primary-subtle)',
          border:     'var(--primary-border)',
          hover:      'var(--primary-hover)',
          active:     'var(--primary-active)',
          50:  'var(--primary-50)',
          100: 'var(--primary-100)',
          200: 'var(--primary-200)',
          300: 'var(--primary-300)',
          400: 'var(--primary-400)',
          500: 'var(--primary-500)',
          600: 'var(--primary-600)',
          700: 'var(--primary-700)',
          800: 'var(--primary-800)',
          900: 'var(--primary-900)',
        },

        secondary: {
          DEFAULT:    'var(--secondary)',
          foreground: 'var(--secondary-foreground)',
        },

        muted: {
          DEFAULT:    'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },

        accent: {
          DEFAULT:    'var(--accent)',
          foreground: 'var(--accent-foreground)',
        },

        // Sémantiques
        success: {
          DEFAULT:    'var(--success)',
          foreground: 'var(--success-foreground)',
          subtle:     'var(--success-subtle)',
          border:     'var(--success-border)',
          text:       'var(--success-text)',
        },

        warning: {
          DEFAULT:    'var(--warning)',
          foreground: 'var(--warning-foreground)',
          subtle:     'var(--warning-subtle)',
          border:     'var(--warning-border)',
          text:       'var(--warning-text)',
        },

        danger: {
          DEFAULT:    'var(--danger)',
          foreground: 'var(--danger-foreground)',
          subtle:     'var(--danger-subtle)',
          border:     'var(--danger-border)',
          text:       'var(--danger-text)',
        },

        // Alias shadcn (pour compatibilité composants shadcn/ui)
        destructive: {
          DEFAULT:    'var(--destructive)',
          foreground: 'var(--destructive-foreground)',
        },

        info: {
          DEFAULT:    'var(--info)',
          foreground: 'var(--info-foreground)',
          subtle:     'var(--info-subtle)',
          border:     'var(--info-border)',
          text:       'var(--info-text)',
        },

        border:  'var(--border)',
        input:   'var(--input)',
        ring:    'var(--ring)',

        // Sidebar
        sidebar: {
          DEFAULT:            'var(--sidebar)',
          foreground:         'var(--sidebar-foreground)',
          primary:            'var(--sidebar-primary)',
          'primary-foreground': 'var(--sidebar-primary-foreground)',
          accent:             'var(--sidebar-accent)',
          'accent-foreground': 'var(--sidebar-accent-foreground)',
          border:             'var(--sidebar-border)',
          ring:               'var(--sidebar-ring)',
        },

        // Charts (accès direct si besoin en JS/inline)
        chart: {
          1: 'var(--chart-1)',
          2: 'var(--chart-2)',
          3: 'var(--chart-3)',
          4: 'var(--chart-4)',
          5: 'var(--chart-5)',
          6: 'var(--chart-6)',
        },
      },

      // ---------------------------------------------------------
      // BORDER RADIUS
      // Usage : rounded-sm, rounded-md, rounded-lg, rounded-xl, rounded-full
      // ---------------------------------------------------------
      borderRadius: {
        sm:   'var(--radius-sm)',
        md:   'var(--radius-md)',
        DEFAULT: 'var(--radius)',
        lg:   'var(--radius-lg)',
        xl:   'var(--radius-xl)',
        full: 'var(--radius-full)',
      },

      // ---------------------------------------------------------
      // TYPOGRAPHIE
      // Usage : font-sans, font-mono, text-sm, text-base, etc.
      // ---------------------------------------------------------
      fontFamily: {
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },

      fontSize: {
        xs:   ['var(--text-xs)',   { lineHeight: 'var(--leading-normal)' }],
        sm:   ['var(--text-sm)',   { lineHeight: 'var(--leading-normal)' }],
        base: ['var(--text-base)', { lineHeight: 'var(--leading-relaxed)' }],
        md:   ['var(--text-md)',   { lineHeight: 'var(--leading-tight)' }],
        lg:   ['var(--text-lg)',   { lineHeight: 'var(--leading-tight)' }],
        xl:   ['var(--text-xl)',   { lineHeight: 'var(--leading-tight)' }],
        '2xl': ['var(--text-2xl)', { lineHeight: 'var(--leading-tight)' }],
      },

      fontWeight: {
        normal:   'var(--font-normal)',
        medium:   'var(--font-medium)',
        semibold: 'var(--font-semibold)',
      },

      // ---------------------------------------------------------
      // ESPACEMENT
      // Tailwind génère spacing de 0 à 96 nativement (base 4px).
      // On étend uniquement pour les constantes layout.
      // Usage : h-topnav, w-sidebar
      // ---------------------------------------------------------
      spacing: {
        topnav:  'var(--topnav-height)',
        sidebar: 'var(--sidebar-width)',
      },

      height: {
        topnav: 'var(--topnav-height)',
      },

      width: {
        sidebar: 'var(--sidebar-width)',
      },
    },
  },

  plugins: [],
}

export default config
