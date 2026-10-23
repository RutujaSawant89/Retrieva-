const CITATION = /\[(S\d+(?:\s*[,;]\s*S\d+)*)\]/g

/** Turn "[S1]" / "[S1, S2]" into markdown links the renderer turns into citation chips. */
export function linkCitations(markdown: string): string {
  return markdown.replace(CITATION, (_, group: string) =>
    group
      .split(/\s*[,;]\s*/)
      .map((label) => `[${label}](#cite-${label})`)
      .join(''),
  )
}
