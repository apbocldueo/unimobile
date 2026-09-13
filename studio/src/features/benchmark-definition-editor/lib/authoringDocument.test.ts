import { describe, expect, it } from "vitest";
import { benchmarkAuthoringDocumentFixture } from "@/entities/benchmark-authoring";
import {
  authoringMembers,
  equalJson,
  normalizeAuthoringInventory,
  patchJsonPath,
  patchManifest,
  patchProtocol,
} from "@/features/benchmark-definition-editor";

describe("authoring document helpers", () => {
  it("clones, compares, and normalizes inventory deterministically", () => {
    const document = benchmarkAuthoringDocumentFixture();
    document.taskFiles = [
      { path: "tasks/z.json", tasks: [] },
      { path: "tasks/a.json", tasks: [] },
    ];
    const normalized = normalizeAuthoringInventory(document);
    expect(normalized.taskFiles.map((item) => item.path)).toEqual([
      "tasks/a.json",
      "tasks/z.json",
    ]);
    expect(equalJson({ a: 1, b: 2 }, { b: 2, a: 1 })).toBe(true);
    expect(authoringMembers(normalized).map((item) => item.key)).toContain(
      "task:tasks/a.json",
    );
  });

  it("patches manifest and Protocol fields without dropping extensions", () => {
    const source = benchmarkAuthoringDocumentFixture();
    const manifest = patchManifest(source, ["title"], "Edited");
    const protocol = patchProtocol(
      manifest,
      "protocols/default.yaml",
      ["seed"],
      99,
    );
    expect(protocol.manifest.document.title).toBe("Edited");
    expect(protocol.manifest.document.x_extension).toEqual({
      nested: ["must", "survive"],
    });
    expect(protocol.protocolFiles[0]?.document.x_protocol).toBe("preserved");
    expect(source.manifest.document.title).toBe("Authoring Fixture");
  });

  it("supports immutable nested mapping and array path updates", () => {
    const source = { nested: { values: [1, 2], extension: true } };
    const patched = patchJsonPath(source, ["nested", "values", 1], 3);
    expect(patched).toEqual({
      nested: { values: [1, 3], extension: true },
    });
    expect(source.nested.values).toEqual([1, 2]);
    expect(() => patchJsonPath(source, ["nested", "values", 5], 3)).toThrow(
      /out of range/,
    );
  });
});
