import lisaFoxall from "../data/public-participation/lisa-foxall.json";
import type { ParticipationHistory } from "../components/profile/public-participation";

// Explicit identity and municipality binding: an initial/surname match alone is
// insufficient to publish a resident's statements on an elected person's profile.
export function getPublicParticipationHistory(personId: number, municipalitySlug: string): ParticipationHistory | null {
  const histories = [lisaFoxall];
  return histories.find((history) => history.personId === personId && history.municipalitySlug === municipalitySlug) || null;
}
