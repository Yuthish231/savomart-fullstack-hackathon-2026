/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Savomart brand. Purple carries actions and chrome; yellow is the highlight
        // (hotspots, active pins) and is only placed on purple/dark, never as text on white.
        savo: {
          purple: "#782B90",
          "purple-dark": "#5A1F6C",
          "purple-light": "#F3E9F6",
          yellow: "#FFF200",
          "yellow-soft": "#FFFBB3",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
