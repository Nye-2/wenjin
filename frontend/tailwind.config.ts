import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        academic: {
          primary: "#1E3A8A",
          secondary: "#3B82F6",
          tertiary: "#60A5FA",
          gold: "#B8860B",
          success: "#059669",
          warning: "#D97706",
          error: "#DC2626",
        },
        background: {
          base: "#F8F6F3",
          elevated: "#FFFEFA",
          surface: "#F1F5F9",
          muted: "#E8ECF4",
        },
        border: {
          DEFAULT: "#E2E8F0",
          subtle: "#F1F5F9",
          focus: "#3B82F6",
        },
      },
      animation: {
        "gradient-x": "gradient-x 3s ease infinite",
        shimmer: "shimmer 3s ease-in-out infinite",
        "pulse-slow": "pulse 3s ease-in-out infinite",
      },
      keyframes: {
        "gradient-x": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        shimmer: {
          "0%, 100%": { transform: "translateX(-100%)" },
          "50%": { transform: "translateX(100%)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
