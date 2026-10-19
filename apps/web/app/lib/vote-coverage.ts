/**
 * How complete a motion's individual vote record is. Minutes often name only
 * the people opposed; the pipeline can reconstruct a full roll call from
 * attendance and the rule that dissent must be recorded (meta written by
 * pipeline/ingestion/ballot_reconstruction.py).
 */
type MotionLike = {
  meta?: any;
  votes?: { person_id?: number | null; vote?: string | null }[] | null;
};

export function isReconstructedVote(motion: MotionLike): boolean {
  return motion.meta?.individual_vote_coverage === "reconstructed_complete";
}

/** True when this person's choice was inferred rather than named in the source. */
export function isInferredChoice(motion: MotionLike, personId?: number | null): boolean {
  if (personId == null) return false;
  const ballot = motion.meta?.ballot_reconstruction;
  return Boolean(
    ballot?.choice_provenance?.[`person_${personId}`]?.startsWith("inferred_") ||
      ballot?.votes?.some(
        (choice: any) => choice.person_id === personId && choice.evidence?.startsWith("inferred_"),
      ),
  );
}

/** Short tally label: "5–2" for complete records, null when only partial names exist. */
export function voteTally(motion: MotionLike): string | null {
  if (!isReconstructedVote(motion)) return null;
  const votes = motion.votes || [];
  const yes = votes.filter((v) => v.vote === "Yes").length;
  const no = votes.filter((v) => v.vote === "No").length;
  return yes + no > 0 ? `${yes}–${no}` : null;
}
