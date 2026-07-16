export const EQUATION_PLACEHOLDER_PATTERN = /\[\[EQ:([A-Za-z0-9_-]+)\]\]/g

export function referencedEquationLabels(
  ...texts: Array<string | null | undefined>
): Set<string> {
  const labels = new Set<string>()
  for (const text of texts) {
    if (!text) continue
    for (const match of text.matchAll(EQUATION_PLACEHOLDER_PATTERN)) labels.add(match[1])
  }
  return labels
}
