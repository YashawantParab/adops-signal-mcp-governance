import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        surface: "#f6f7f9",
        line: "#d9dee7",
        accent: "#0f766e",
        warning: "#b7791f",
        danger: "#b42318"
      },
      boxShadow: {
        panel: "0 1px 2px rgba(23, 32, 51, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
