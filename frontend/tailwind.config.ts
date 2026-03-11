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
          primary: "#3B82F6",
          secondary: "#60A5FA",
          tertiary: "#93C5FD",
          success: "#22C55E",
          warning: "#F59E0B",
          error: "#EF4444",
          gold: "#F59E0B",
        },
        background: {
          base: "#1F1F1F",
          elevated: "#2A2A2A",
          surface: "#363636",
          muted: "#404040",
        },
        border: {
          DEFAULT: "#404040",
          subtle: "#363636",
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
