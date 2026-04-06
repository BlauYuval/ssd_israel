/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#eef3ff",
          100: "#d9e4ff",
          200: "#b3c8ff",
          400: "#4d7fff",
          600: "#0038B8",
          700: "#002fa0",
          800: "#002688",
          900: "#001d6e",
        },
      },
    },
  },
  plugins: [],
}
