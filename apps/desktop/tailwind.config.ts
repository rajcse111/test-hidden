import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#111827",
        panel: "#1f2937",
        accent: "#2dd4bf",
      },
      boxShadow: {
        overlay: "0 18px 70px rgba(0,0,0,0.42)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
} satisfies Config;

