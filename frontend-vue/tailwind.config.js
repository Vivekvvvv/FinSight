export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        // 暖白 AI 助手风 token
        fin: {
          bg: '#f7f6f4',
          card: '#ffffff',
          border: '#ebe9e3',
          text: '#1f1d1a',
          muted: '#8c887e',
          primary: '#cc785c',
          'primary-deep': '#a85c43',
          'primary-soft': '#faece4',
          success: '#2e7d57',
          danger: '#c44545',
          warning: '#d97706',
        },
      },
      borderRadius: {
        input: '26px',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'PingFang SC', 'Microsoft YaHei', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
