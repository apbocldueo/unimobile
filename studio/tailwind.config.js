/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "ZhiXing UI",
          "Times New Roman",
          "Microsoft YaHei",
          "微软雅黑",
          "PingFang SC",
          "system-ui",
          "serif",
        ],
      },
    },
  },
  plugins: [],
};
