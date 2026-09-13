import { studioRequest } from "@/shared/api";
import {
  parseExperimentPreview,
  type ExperimentPreview,
  type ExperimentPreviewRequest,
} from "../model/experimentPreview.schema";

/** Request a deterministic preview without creating an Experiment. */
export async function previewExperiment(
  input: ExperimentPreviewRequest,
): Promise<ExperimentPreview> {
  return parseExperimentPreview(
    await studioRequest("/studio/benchmark-experiments/preview", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  );
}
