/**
 * 模块切换前的异步校验（占位：可替换为真实接口）。
 * 默认等待 1s 后成功；配置 VITE_MODULE_NAV_ENDPOINT 时改为 POST 校验；
 * sessionStorage「zx-nav-fail-once」=「1」时下一次调用失败（便于联调错误态）。
 */
const LOAD_MS = 1000;

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const id = window.setTimeout(() => resolve(), ms);
    const onAbort = () => {
      window.clearTimeout(id);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export async function requestModuleSwitch(targetPath: string, signal?: AbortSignal): Promise<void> {
  await sleep(LOAD_MS, signal);

  const endpoint = typeof import.meta !== "undefined" ? import.meta.env?.VITE_MODULE_NAV_ENDPOINT : undefined;
  if (typeof endpoint === "string" && endpoint.length > 0) {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: targetPath }),
      signal,
    });
    if (!res.ok) throw new Error(`module_nav_http_${res.status}`);
    return;
  }

  if (typeof window !== "undefined" && window.sessionStorage?.getItem("zx-nav-fail-once") === "1") {
    window.sessionStorage.removeItem("zx-nav-fail-once");
    throw new Error("module_nav_simulated_fail");
  }
}
