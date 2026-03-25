"use client";

import { useEffect } from "react";

interface Shortcut {
  key: string;
  meta?: boolean;
  shift?: boolean;
  action: () => void;
}

export function useGlobalShortcuts(shortcuts: Shortcut[]) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const metaPressed = event.metaKey || event.ctrlKey;

      for (const shortcut of shortcuts) {
        const target = event.target as HTMLElement | null;
        const isEditable =
          target?.tagName === "INPUT" ||
          target?.tagName === "TEXTAREA" ||
          Boolean(target?.isContentEditable);

        if (
          event.key.toLowerCase() === shortcut.key.toLowerCase() &&
          metaPressed === Boolean(shortcut.meta) &&
          event.shiftKey === Boolean(shortcut.shift)
        ) {
          if (shortcut.key.toLowerCase() !== "k" && isEditable) {
            return;
          }
          event.preventDefault();
          shortcut.action();
          return;
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [shortcuts]);
}
