import { Navigate, useParams } from "react-router-dom";
import { BenchmarkDefinitionWorkbench } from "@/widgets/benchmark-definition-workbench";

const DRAFT_ID = /^benchmark-draft-[a-f0-9]{32}$/;

/** Bind one validated opaque draft URL identity to the definition workbench. */
export function BenchmarkDraftEditPage() {
  const draftId = useParams<{ draftId: string }>().draftId ?? "";
  if (!DRAFT_ID.test(draftId)) {
    return <Navigate to="/benchmark-authoring" replace />;
  }
  return <BenchmarkDefinitionWorkbench draftId={draftId} />;
}
