import { useMutation } from "@tanstack/react-query";
import { previewExperiment } from "./experimentPreviewApi";

/** Expose preview as an explicit non-persistent command. */
export function usePreviewExperiment() {
  return useMutation({ mutationFn: previewExperiment });
}
