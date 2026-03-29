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
        display: ['"Playfair Display"', "Georgia", "serif"],
        serif: ['"Noto Serif SC"', '"STSong"', '"SimSun"', "serif"],
        sans: ['"DM Sans"', '"Noto Sans SC"', "-apple-system", "BlinkMacSystemFont", '"PingFang SC"', "sans-serif"],
      },
      colors: {
        guanlan: {
          ink: "#0A1628",
          deep: "#0F2847",
          wave: "#1B4B7A",
          crest: "#3B82C4",
          foam: "#7BB8E0",
          mist: "#B8D8EB",
          gold: "#C4934A",
          amber: "#E8B86D",
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
      },
      animation: {
        "gradient-x": "gradient-x 4s ease infinite",
        shimmer: "shimmer 3s ease-in-out infinite",
        "pulse-slow": "pulse 3s ease-in-out infinite",
        "wave-drift": "wave-drift 12s linear infinite",
        "wave-drift-slow": "wave-drift 18s linear infinite",
        "wave-float": "wave-float 6s ease-in-out infinite",
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
        "wave-drift": {
          "0%": { transform: "translateX(0) translateZ(0)" },
          "100%": { transform: "translateX(-50%) translateZ(0)" },
        },
        "wave-float": {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
