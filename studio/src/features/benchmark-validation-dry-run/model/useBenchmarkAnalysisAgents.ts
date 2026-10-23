import { useInfiniteQuery } from "@tanstack/react-query";
import { listStudioAgents } from "@/entities/agent";

/**
 * Load bounded cursor pages of Agent candidates for immutable selection.
 *
 * Returns:
 *   TanStack infinite-query state plus the flattened, server-bounded candidates.
 */
export function useBenchmarkAnalysisAgents() {
  const query = useInfiniteQuery({
    queryKey: ["studio", "agents", "benchmark-validation"],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => listStudioAgents(50, pageParam),
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
  });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return { ...query, items };
}
