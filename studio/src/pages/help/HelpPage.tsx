import { HelpTopics } from "@/features/help-center";

/** Compose the Help feature inside the existing Studio visual shell. */
export function HelpPage() {
  return <main className="h-full overflow-auto bg-[var(--zx-app)] p-8 text-[color:var(--zx-text-body)]"><HelpTopics /></main>;
}
