import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const srcDir = fileURLToPath(new URL("./src", import.meta.url));

/**
 * 开发（``vite``）与本地预览（``vite preview``）共用：把 ``/zhixing-studio`` 转到 ``python -m zhixing.studio``（默认 8765）。
 * 注意：仅 dev 默认把 ``VITE_STUDIO_API_BASE`` 设为 ``/zhixing-studio``；preview 需自行设直连地址或同源代理前缀。
 */
const zhixingStudioDevProxy = {
  "/zhixing-studio": {
    target: "http://127.0.0.1:8765",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/zhixing-studio/, "") || "/",
    configure: (proxy: { on: (ev: string, fn: (...args: unknown[]) => void) => void }) => {
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
};

export default defineConfig({
  plugins: [react()],
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
});
