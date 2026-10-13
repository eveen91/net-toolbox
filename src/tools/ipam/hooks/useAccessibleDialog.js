import { useEffect, useRef } from "react";

const focusable = "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

export function handleAccessibleDialogKeyDown(event, dialog, onClose) {
  if (event.key === "Escape") {
    event.preventDefault();
    onClose();
    return;
  }
  if (event.key !== "Tab" || !dialog) return;
  const items = [...dialog.querySelectorAll(focusable)];
  if (!items.length) return;
  const firstItem = items[0];
  const lastItem = items.at(-1);
  if (event.shiftKey && document.activeElement === firstItem) {
    event.preventDefault();
    lastItem.focus();
  } else if (!event.shiftKey && document.activeElement === lastItem) {
    event.preventDefault();
    firstItem.focus();
  }
}

export function useAccessibleDialog(isOpen, onClose, { restoreFocus = true } = {}) {
  const dialogRef = useRef(null);
  const openerRef = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  const captureOpener = () => {
    openerRef.current = document.activeElement;
  };

  useEffect(() => {
    if (!isOpen) return undefined;
    if (!openerRef.current) openerRef.current = document.activeElement;
    const dialog = dialogRef.current;
    const first = dialog?.querySelector(focusable);
    first?.focus();
    const onKeyDown = (event) => handleAccessibleDialogKeyDown(event, dialog, () => closeRef.current());
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (restoreFocus) openerRef.current?.focus?.();
    };
  }, [isOpen, restoreFocus]);

  return { dialogRef, captureOpener };
}
