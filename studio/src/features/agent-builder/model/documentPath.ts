import { parseStudioFlowDocument, type StudioFlowDocument } from "@/entities/agent-graph";

/** Return the only editable schema-3 canvas; nested raw-control canvases are forbidden. */
export function documentAtCanvasPath(
  root: StudioFlowDocument,
  canvasPath: readonly string[],
): StudioFlowDocument {
  if (canvasPath.length) throw new Error("schema-3 capability documents have no nested editable canvas");
  return root;
}

/** Update the only editable schema-3 canvas and re-run the strict parser. */
export function updateDocumentAtCanvasPath(
  root: StudioFlowDocument,
  canvasPath: readonly string[],
  update: (document: StudioFlowDocument) => StudioFlowDocument,
): StudioFlowDocument {
  if (canvasPath.length) throw new Error("schema-3 capability documents have no nested editable canvas");
  return parseStudioFlowDocument(update(root));
}
