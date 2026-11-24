export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: { extend: { colors: { ink: "#1b2a3a", paper: "#f3f4f8", teal: { 50: "rgb(var(--c50) / <alpha-value>)", 100: "rgb(var(--c100) / <alpha-value>)", 200: "rgb(var(--c200) / <alpha-value>)", 600: "rgb(var(--c600) / <alpha-value>)", 700: "rgb(var(--c700) / <alpha-value>)", 900: "rgb(var(--c900) / <alpha-value>)" } },
    fontFamily: { sans: ['"Segoe UI"', "system-ui", "Roboto", "sans-serif"] } } },
  plugins: [],
};
