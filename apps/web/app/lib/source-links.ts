/**
 * Where an AI-answer citation should take the reader: the exact transcript
 * moment, the meeting's decisions, or the matter/bylaw page.
 */
import { bylawPath, matterPath, meetingPath } from "./paths";
export function sourceHref(source: any): string {
  if (!source) return "#";
  if (source.type === "bylaw" && source.bylaw_id) return bylawPath({ id: source.bylaw_id, slug: source.bylaw_slug });
  if (source.type === "matter" && source.id) return matterPath({ id: source.id, slug: source.matter_slug ?? source.slug });
  if (!source.meeting_id) return "#";
  const meeting = meetingPath({ id: source.meeting_id, slug: source.meeting_slug });
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
