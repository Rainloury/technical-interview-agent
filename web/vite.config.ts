import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `@` 必须与 tsconfig.json 的 paths 保持一致；vitest.config.ts 通过 mergeConfig 继承这里。
export default defineConfig({
  plugins: [react()],
  // 目标对齐 Android WebView 91（Chromium 91）：压缩器不会把 `max-width` 改写成
  // Media Queries L4 的 `(width<=760px)` 区间语法，避免旧 WebView 丢弃整段响应式规则。
  build: {
    target: "chrome87",
    cssTarget: "chrome87",
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 3001,
    strictPort: true,
  },
  preview: {
    host: "127.0.0.1",
    port: 3001,
    strictPort: true,
  },
});
