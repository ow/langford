/**
 * Where an AI-answer citation should take the reader: the exact transcript
 * moment, the meeting's decisions, or the matter/bylaw page.
 */
export function sourceHref(source: any): string {
  if (!source) return "#";
  if (source.type === "bylaw" && source.bylaw_id) return `/bylaws/${source.bylaw_id}`;
  if (source.type === "matter" && source.id) return `/matters/${source.id}`;
  if (!source.meeting_id) return "#";
  const meeting = `/meetings/${source.meeting_id}`;
  if (source.type === "transcript" && source.id) return `${meeting}#transcript=${source.id}`;
  if (source.type === "motion" || source.type === "vote") return `${meeting}#decisions`;
  return meeting;
}

export function sourceLinkLabel(source: any): string {
  switch (source?.type) {
    case "bylaw":
      return "View bylaw";
    case "matter":
      return "View matter";
    case "transcript":
      return "Play this moment";
    case "motion":
    case "vote":
      return "See the decision";
    default:
      return "View in meeting";
  }
}
