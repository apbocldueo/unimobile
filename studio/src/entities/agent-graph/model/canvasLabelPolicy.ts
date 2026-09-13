const TERMINAL_OUTCOME_TEXT = /\b(done|fail(?:ed|ure)?|success(?:ful)?|completed?|terminal)\b|完成|失败|成功|终止/iu;

/** Return canvas-safe text without suppressing exact facts outside the graph. */
export function canvasSafeText(value: string | undefined, fallback = ""): string {
  const text = value?.trim() ?? "";
  return text && !TERMINAL_OUTCOME_TEXT.test(text) ? text : fallback;
}

/** Return whether compatibility presentation text is forbidden on a graph canvas. */
export function containsTerminalOutcomeText(value: string | undefined): boolean {
  return TERMINAL_OUTCOME_TEXT.test(value ?? "");
}
