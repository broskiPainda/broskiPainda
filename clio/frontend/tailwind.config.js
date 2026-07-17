/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        navy: "#0b1424",
        parchment: "#f4ecd8",
      },
      fontFamily: {
        display: ["Georgia", "Cambria", "serif"],
      },
    },
  },
  plugins: [],
};
