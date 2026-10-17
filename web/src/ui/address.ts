/** Keeps the address in step with the choice, so a reload or a shared link comes back to it. */
export function writeAddress(project: number | null, taskId: string): void {
  const url = new URL(window.location.href);
  for (const [key, value] of [
    ["project", project?.toString() ?? ""],
    ["task", taskId],
  ] as const) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  window.history.replaceState(null, "", url);
}
