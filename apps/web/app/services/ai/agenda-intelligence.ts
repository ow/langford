import { z } from "zod";

/**
 * Agenda-item "intelligence": the web-side single source for the prompt and schema
 * used by /api/intel. The pipeline has its own copy in
 * apps/pipeline/pipeline/ingestion/process_agenda.py (generate_agenda_intelligence);
 * keep the two in step until they share a definition.
 */
export const AgendaItemIntelligenceSchema = z.object({
  detailed_analysis: z.string(),
  arguments: z.array(
    z.object({
      side: z.enum(["Pro", "Con"]),
      point: z.string(),
      speaker: z.string(),
    }),
  ),
  questions: z.array(
    z.object({
      question: z.string(),
      asked_by: z.string(),
      answered_by: z.string(),
      answer: z.string(),
    }),
  ),
  sentiment_score: z.number().min(-1).max(1),
});

export type AgendaItemIntelligence = z.infer<typeof AgendaItemIntelligenceSchema>;

export const AGENDA_INTELLIGENCE_SCHEMA_NAME = "agenda_item_intelligence";

export const AGENDA_INTELLIGENCE_SYSTEM =
  "You are a City Council Intelligence Analyst. You extract structured insight from municipal meeting transcripts.";

export const MAX_TRANSCRIPT_CHARS = 50_000;

export function buildAgendaIntelligencePrompt(itemTitle: string, transcriptText: string): string {
  return `Analyze the following transcript segment which corresponds to a specific Agenda Item: "${itemTitle}".

**GOAL**: Extract deep insights into the discussion, PRIORITIZING the contributions, concerns, and arguments made by Council Members (Mayor and Councillors).

**TRANSCRIPT**:
${transcriptText.slice(0, MAX_TRANSCRIPT_CHARS)}

**INSTRUCTIONS**:
1. **detailed_analysis**: Write a comprehensive 2-3 paragraph narrative. Focus on the Council's reaction to the proposal, the core of their debate, and how they reached their decision.
2. **arguments**: Extract key arguments for (Pro) and against (Con) the item/motion, each with the point and the speaker.
   - FOCUS ON COUNCIL MEMBERS. Only include staff/applicant points if they are critical context for a Council member's objection or support.
   - "Pro" should reflect reasons for support expressed by Council.
   - "Con" should reflect specific concerns, skepticism, or objections raised by Council.
3. **questions**: List specific questions asked by Council members to Staff or Applicants, who asked, who answered, and the answers they received.
4. **sentiment_score**: Analyze the overall tone of the *Council's* discussion (not the public or staff). -1.0 (Critical/Hostile) to 1.0 (Supportive/Favorable). 0.0 is Neutral/Procedural.`;
}
