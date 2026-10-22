/** Accept only root-relative return paths; browsers normalize backslashes and controls. */
export function safeRedirect(value: string | null, fallback: string): string {
  if (
    !value || !value.startsWith("/") || value.startsWith("//") ||
    /[\\\u0000-\u0020\u007f]/.test(value)
  ) {
    return fallback;
  }
  return value;
}
