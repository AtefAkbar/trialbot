/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: [
          'SFMono-Regular', 'SF Mono', 'Menlo', 'Consolas',
          'Liberation Mono', 'ui-monospace', 'monospace',
        ],
      },
      colors: {
        // Bloomberg-terminal palette: amber on black.
        bbg: {
          bg: '#000000',
          panel: '#0a0a0a',
          head: '#161206',
          border: '#2a2a2a',
          grid: '#1c1c1c',
          amber: '#ff9800', // primary orange
          amber2: '#ffb84d', // lighter amber
          gold: '#ffcc33',
          text: '#d8d8d8', // data white
          dim: '#7d7d7d', // muted
          green: '#00d15f',
          red: '#ff3b30',
          cyan: '#33c6dd',
        },
        // Zone colors, tuned for black background.
        zone: {
          quiet: '#7d7d7d',
          sweet: '#00d15f',
          hot: '#ff9800',
          wild: '#ff3b30',
        },
      },
    },
  },
  plugins: [],
}
