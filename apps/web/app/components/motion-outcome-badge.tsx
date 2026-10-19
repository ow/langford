import { Badge } from "./ui/badge";
import { cn } from "../lib/utils";
import {
  normalizeMotionResult,
  OUTCOME_STYLES,
  OUTCOME_LABELS,
} from "../lib/motion-utils";

interface MotionOutcomeBadgeProps {
  result: string | null | undefined;
  showVoteCounts?: boolean;
  yesVotes?: number;
  noVotes?: number;
  className?: string;
}

/**
 * Shared badge component for displaying motion outcomes.
 *
 * Normalizes raw database result strings (e.g. "CARRIED", "DEFEATED", "CARRRIED")
 * into color-coded badges: green for passed, red for failed, yellow for tabled,
 * gray for withdrawn.
 *
 * Missing outcomes are explicit; an unrecognized source result is shown verbatim.
 */
export function MotionOutcomeBadge({
  result,
  showVoteCounts = false,
  yesVotes,
  noVotes,
  className,
}: MotionOutcomeBadgeProps) {
  const outcome = normalizeMotionResult(result);
  if (!outcome) {
    return (
      <Badge variant="outline" className={cn("text-[10px] font-bold uppercase tracking-wide text-zinc-600", className)}>
        {result?.trim() || "Outcome not recorded"}
      </Badge>
    );
  }

  return (
    <Badge
      variant="outline"
      className={cn(
        "text-[10px] font-bold uppercase tracking-wide",
        OUTCOME_STYLES[outcome],
        className,
      )}
    >
      {OUTCOME_LABELS[outcome]}
      {showVoteCounts && yesVotes != null && yesVotes > 0 && (
        <span className="ml-1 opacity-80">
          ({yesVotes}-{noVotes ?? 0})
        </span>
      )}
    </Badge>
  );
}
