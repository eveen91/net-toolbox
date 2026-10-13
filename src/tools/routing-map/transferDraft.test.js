import { expect, it } from "vitest";
import { removeMovedHost } from "./transferDraft.js";
it("removes moved blocks without changing unrelated unsaved input", () => {
  const draft = "# notes\n@router\nroute one\n@other\nunparsed input\n@router\nroute two\n";
  expect(removeMovedHost(draft, "router")).toBe("# notes\n@other\nunparsed input\n");
  expect(removeMovedHost(draft, "unknown")).toBe(draft);
});
