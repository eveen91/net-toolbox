import { afterEach, describe, expect, it, vi } from "vitest";
import { handleAccessibleDialogKeyDown } from "./useAccessibleDialog.js";

const event = (key, shiftKey = false) => ({ key, shiftKey, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } });
let activeElement;

afterEach(() => { vi.unstubAllGlobals(); activeElement = undefined; });

describe("accessible dialog keyboard handling", () => {
  it("closes with Escape", () => {
    const onClose = vi.fn(); const keyEvent = event("Escape");
    handleAccessibleDialogKeyDown(keyEvent, null, onClose);
    expect(keyEvent.defaultPrevented).toBe(true); expect(onClose).toHaveBeenCalledOnce();
  });

  it("traps Tab focus between first and last controls", () => {
    const first = { focus: () => { activeElement = first; } }; const last = { focus: () => { activeElement = last; } };
    const dialog = { querySelectorAll: () => [first, last] };
    vi.stubGlobal("document", { get activeElement() { return activeElement; } });
    activeElement = last;
    const forward = event("Tab"); handleAccessibleDialogKeyDown(forward, dialog, vi.fn());
    expect(forward.defaultPrevented).toBe(true); expect(activeElement).toBe(first);
    const backward = event("Tab", true); handleAccessibleDialogKeyDown(backward, dialog, vi.fn());
    expect(backward.defaultPrevented).toBe(true); expect(activeElement).toBe(last);
  });
});
