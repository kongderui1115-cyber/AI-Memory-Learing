// Identifiers for browser-only demo records, including HTTP VM previews.
let sequence = 0;

export function createPreviewId(): string {
  sequence += 1;
  return (
    globalThis.crypto?.randomUUID?.() ??
    `preview-${Date.now().toString(36)}-${sequence}`
  );
}
