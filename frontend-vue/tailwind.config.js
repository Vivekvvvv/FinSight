export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        // Claude 暖白赤橙 —— 与 src/styles/tokens.css 的 --fin-* 亮色值保持一致。
        // 权威在 tokens.css（全站 700+ 处 var(--fin-*) 消费）；这里仅供
        // 少数 Tailwind 工具类需要时复用同一套色，改色请两处同步。
        fin: {
          bg: '#faf9f5',
          card: '#ffffff',
          border: '#e9e6df',
          text: '#1a1a18',
          'text-2': '#5a5751',
          muted: '#8c887e',
          primary: '#cc785c',
          'primary-deep': '#a85c43',
          'primary-soft': '#faece4',
          accent: '#7c9885',
          success: '#3d9970',
          danger: '#d1493f',
          warning: '#d97706',
        },
      },
      borderRadius: {
        input: '8px',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'PingFang SC', 'Microsoft YaHei', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
