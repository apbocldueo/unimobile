/** 合并 className（占位；后续可接 tailwind-merge）。 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
