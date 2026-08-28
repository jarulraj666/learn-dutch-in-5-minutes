import type { Config } from "tailwindcss";

// Brand palette carried over from the original index.html gradient.
const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          from: "#667eea",
          to: "#764ba2",
          50: "#f4f3fd",
          100: "#e9e7fb",
          200: "#d0cbf6",
          300: "#b0a7ef",
          400: "#8b7de6",
          500: "#667eea",
          600: "#5a5fd0",
          700: "#764ba2",
          800: "#5d3b80",
          900: "#432b5c",
        },
      },
      backgroundImage: {
        brand: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
