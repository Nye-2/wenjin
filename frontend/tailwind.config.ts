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
          primary: "#4F46E5",
          secondary: "#06B6D4",
          success: "#10B981",
          warning: "#F59E0B",
          error: "#EF4444",
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
