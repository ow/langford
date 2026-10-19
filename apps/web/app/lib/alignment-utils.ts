import { membershipIsActiveOn } from "./council-terms";
// Helper to parse dates without timezone shifts
export const parseAlignmentDate = (dateStr: string | null | undefined) => {
  if (!dateStr) return null;
  const [y, m, d] = dateStr.split(/[- : T]/).map(Number);
  return new Date(y, m - 1, d || 1);
};

export interface AlignmentResult {
  personId: number;
  personName: string;
  imageUrl?: string | null;
  totalMotions: number;
  matchingVotes: number;
  alignmentRate: number;
}

/**
 * Calculates how often a target person aligns with all other people 
 * based on provided votes and memberships within a specific date range.
 */
export function calculateAlignmentForPerson(
  targetPersonId: number,
  allVotes: any[],
  memberships: any[],
  startDate: Date,
  endDate: Date
): AlignmentResult[] {
  // 1. Group votes by motion
  const votesByMotion: Record<number, { day: string; votes: Record<number, string> }> = {};
  allVotes.forEach((v) => {
    const d = parseAlignmentDate(v.motions?.meetings?.meeting_date);
    if (d && d >= startDate && d <= endDate) {
      if (!votesByMotion[v.motion_id]) {
        votesByMotion[v.motion_id] = { day: v.motions.meetings.meeting_date.slice(0, 10), votes: {} };
      }
      votesByMotion[v.motion_id].votes[v.person_id] = v.vote;
    }
  });

  // Preserve individual service intervals: returning councillors may have gaps.
  const members = new Map<number, { name: string; image_url?: string; intervals: any[] }>();
  memberships.forEach((membership) => {
    if (!membership.people) return;
    const personId = membership.people.id;
    const person = members.get(personId) || { name: membership.people.name, image_url: membership.people.image_url, intervals: [] as any[] };
    person.intervals.push(membership);
    members.set(personId, person);
  });
  const target = members.get(targetPersonId);
  if (!target) return [];

  const results: AlignmentResult[] = [];

  members.forEach((otherPerson, otherId) => {
    if (otherId === targetPersonId) return;

    let totalCommonMotions = 0;
    let matchingVotes = 0;

    Object.values(votesByMotion).forEach(({ day, votes: motionVotes }) => {
      const targetVote = motionVotes[targetPersonId];
      const otherVote = motionVotes[otherId];
      if (targetVote && otherVote
        && target.intervals.some((membership) => membershipIsActiveOn(membership, day))
        && otherPerson.intervals.some((membership) => membershipIsActiveOn(membership, day))) {
        totalCommonMotions++;
        if (targetVote === otherVote) matchingVotes++;
      }
    });

    if (totalCommonMotions > 0) {
      results.push({
        personId: otherId,
        personName: otherPerson.name,
        imageUrl: otherPerson.image_url,
        totalMotions: totalCommonMotions,
        matchingVotes: matchingVotes,
        alignmentRate: (matchingVotes / totalCommonMotions) * 100
      });
    }
  });

  return results.sort((a, b) => b.alignmentRate - a.alignmentRate);
}
