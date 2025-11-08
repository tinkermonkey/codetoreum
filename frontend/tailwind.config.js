/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Semantic color tokens (shadcn/ui style)
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // GitHub-style color tokens (for compatibility with legacy UX)
        'gh-canvas': {
          DEFAULT: 'var(--gh-canvas)',
          subtle: 'var(--gh-canvas-subtle)',
        },
        'gh-border': {
          DEFAULT: 'var(--gh-border)',
          muted: 'var(--gh-border-muted)',
        },
        'gh-fg': {
          DEFAULT: 'var(--gh-fg)',
          default: 'var(--gh-fg-default)',
          muted: 'var(--gh-fg-muted)',
          subtle: 'var(--gh-fg-subtle)',
        },
        'gh-accent': {
          primary: 'var(--gh-accent-primary)',
          emphasis: 'var(--gh-accent-emphasis)',
        },
        'gh-success': 'var(--gh-success)',
        'gh-danger': 'var(--gh-danger)',
        'gh-warning': 'var(--gh-warning)',
        'gh-warning-subtle': 'var(--gh-warning-subtle)',
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
}
