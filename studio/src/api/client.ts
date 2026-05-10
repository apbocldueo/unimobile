/**
 * HTTP 客户端封装（占位）。
 * 后续从 import.meta.env.VITE_API_BASE_URL 读取基地址。
 */
export async function apiGet(path: string): Promise<unknown> {
  throw new Error(`apiGet 尚未实现: ${path}`);
}
