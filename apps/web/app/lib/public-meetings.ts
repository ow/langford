/** Scheduled inaugurations are public events even before an agenda is posted. */
export const PUBLIC_MEETING_FILTER =
  "has_agenda.eq.true,has_minutes.eq.true,has_transcript.eq.true,summary.not.is.null,type.eq.Inauguration";
