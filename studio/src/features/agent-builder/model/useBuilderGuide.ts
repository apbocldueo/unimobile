import { useState } from "react";

export const BUILDER_GUIDE_PREFERENCE_KEY = "zx-builder-guide-dismissed-v1";

/** Read optional visibility preferences without blocking authoring.
 * Args: defaultDismissed applies when storage is missing or unavailable.
 * Returns: Whether the guide starts collapsed; storage errors do not escape.
 */
function readDismissedPreference(defaultDismissed: boolean): boolean {
  if (typeof window === "undefined") return defaultDismissed;
  try {
    const preference = window.localStorage.getItem(BUILDER_GUIDE_PREFERENCE_KEY);
    return preference === null ? defaultDismissed : preference === "1";
  } catch {
    return defaultDismissed;
  }
}

/** Manage only the dismissible Builder guide preference; document state remains elsewhere.
 * Args: defaultDismissed hides onboarding for populated drafts unless a user preference exists.
 * Returns: Visibility and explicit preference commands; never edits the document.
 */
export function useBuilderGuide(defaultDismissed = false) {
  const [dismissed, setDismissed] = useState(() => readDismissedPreference(defaultDismissed));

  /** Persist the guide visibility choice while tolerating unavailable storage. */
  const persist = (value: boolean) => {
    setDismissed(value);
    try {
      window.localStorage.setItem(BUILDER_GUIDE_PREFERENCE_KEY, value ? "1" : "0");
    } catch {
      // Private browsing or blocked storage must not prevent graph editing.
    }
  };

  return {
    visible: !dismissed,
    dismiss: () => persist(true),
    reopen: () => persist(false),
  } as const;
}
