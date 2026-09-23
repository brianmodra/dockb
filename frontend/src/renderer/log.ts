export function reportError(
  source: string,
  error: unknown,
  onMessage?: (text: string) => void,
): string {
  const text = `${source}: ${error instanceof Error ? error.message : String(error)}`;
  console.error(text);
  onMessage?.(text);
  return text;
}