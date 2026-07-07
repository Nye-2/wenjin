import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        serif: ["var(--font-serif)", '"STSong"', '"SimSun"', "serif"],
        sans: [
          "var(--font-sans)",
          '"Noto Sans SC"',
          "-apple-system",
          "BlinkMacSystemFont",
          '"PingFang SC"',
          "sans-serif",
        ],
        inter: ["Inter", "var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "var(--font-mono)", "monospace"],
      },
      colors: {
        wenjin: {
          ink: "#132235",
          navy: "#1F4263",
          teal: "#2E6F6D",
          cyan: "#5C97A5",
          line: "#D7DEE2",
          brass: "#A67C39",
          paper: "#F7F4EE",
          wash: "#EEF2F3",
          success: "#0D9265",
          warning: "#C68A1A",
          error: "#C42B2B",
        },
        background: {
          base: "#F5F7FA",
          elevated: "#FAFBFE",
          surface: "#EBF0F7",
          muted: "#DDE5F0",
        },
        border: {
          DEFAULT: "#D8E1ED",
          subtle: "#E8EFF7",
          focus: "#3B82C4",
        },
        // Compute Stage dark theme colors
        compute: {
          base: "#0B0F14",
          elevated: "#111820",
          surface: "#1A2330",
          border: "#232D3D",
          "text-primary": "#E8ECF2",
          "text-secondary": "#8A94A6",
          "text-muted": "#5A6378",
          cyan: "#5C97A5",
          gold: "#C8A050",
          green: "#2D9D78",
          red: "#D14B4B",
        },
      },
      animation: {
        shimmer: "shimmer 3s ease-in-out infinite",
        "pulse-slow": "pulse 3s ease-in-out infinite",
        "status-pulse": "status-pulse 2s ease-in-out infinite",
        "shimmer-slide": "shimmer-slide 1.5s ease-in-out infinite",
        "fade-in": "fade-in 300ms ease-out",
        "slide-up": "slide-up 400ms cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-right": "slide-in-right 400ms cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in": "scale-in 200ms cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        shimmer: {
          "0%, 100%": { transform: "translateX(-100%)" },
          "50%": { transform: "translateX(100%)" },
        },
        "status-pulse": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
        "shimmer-slide": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(-20px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.96)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
      spacing: {
        "18": "4.5rem",
        "22": "5.5rem",
        "30": "7.5rem",
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
      },
      transitionTimingFunction: {
        apple: "cubic-bezier(0.16, 1, 0.3, 1)",
        flow: "cubic-bezier(0.4, 0, 0.2, 1)",
      },
      transitionDuration: {
        "400": "400ms",
        "600": "600ms",
      },
    },
  },
  plugins: [],
};

export default config;
