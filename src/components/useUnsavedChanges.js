import { useEffect, useRef } from "react";

export default function useUnsavedChanges(dirty, busy = false) {
  const state = useRef({ dirty, busy });
  state.current = { dirty, busy };
  useEffect(() => {
    const guard = (event) => {
      if (state.current.busy || (state.current.dirty && !window.confirm("Discard unsaved changes and leave this view?"))) event.preventDefault();
    };
    const unload = (event) => {
      if (!state.current.dirty && !state.current.busy) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("nt-before-navigate", guard);
    window.addEventListener("beforeunload", unload);
    return () => {
      window.removeEventListener("nt-before-navigate", guard);
      window.removeEventListener("beforeunload", unload);
    };
  }, []);
}
