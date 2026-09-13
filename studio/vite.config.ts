import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import type { ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

const srcDir = fileURLToPath(new URL("./src", import.meta.url));

/**
 * Split stable framework dependencies from the application bundle.
 *
 * @param id - Rollup module identifier being assigned to an output chunk.
 * @returns A stable vendor chunk name, or undefined for application modules.
 */
function studioVendorChunk(id: string): string | undefined {
  return id.includes("/node_modules/") ? "vendor" : undefined;
}

/**
 * 开发（``vite``）与本地预览（``vite preview``）共用：把 ``/zhixing-studio`` 转到 ``python -m zhixing.studio``（默认 8765）。
 * 注意：仅 dev 默认把 ``VITE_STUDIO_API_BASE`` 设为 ``/zhixing-studio``；preview 需自行设直连地址或同源代理前缀。
 */
const zhixingStudioDevProxy = {
  "/zhixing-studio": {
    target: process.env.ZHIXING_STUDIO_PROXY_TARGET ?? "http://127.0.0.1:8765",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/zhixing-studio/, "") || "/",
    configure: (proxy) => {
      proxy.on("error", (err: unknown, _req: unknown, res: unknown) => {
        const r = res as { headersSent?: boolean; writeHead?: (c: number, h: Record<string, string>) => void; end?: (b: string) => void };
        if (r?.headersSent || typeof r?.writeHead !== "function" || typeof r?.end !== "function") return;
        r.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
        r.end(
          JSON.stringify({
            error: "zhixing_studio_unreachable",
            message: String((err as Error)?.message ?? err),
          }),
        );
      });
    },
  },
} satisfies Record<string, string | ProxyOptions>;

export default defineConfig({
  plugins: [react()],
  build: {
    // The current authoring application is broad but split from its stable vendor graph.
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: studioVendorChunk,
      },
    },
  },
  resolve: {
    alias: {
      "@": srcDir,
    },
  },
  server: {
    port: 5173,
    proxy: zhixingStudioDevProxy,
  },
  preview: {
    proxy: zhixingStudioDevProxy,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
