/** Appended to every system prompt by the AI client so individual prompts can't forget them. */
export const HOUSE_RULES =
  "House rules for anything written about people: never infer or assume anyone's gender. " +
  "Do not use he/him/his or she/her/hers unless the source text states that person's pronouns; " +
  "refer to people by name, role or title, or use they/them, or start the sentence with the verb.";

export function withHouseRules(system?: string): string {
  return system && system.trim().length > 0
    ? `${system.trimEnd()}\n\n${HOUSE_RULES}`
    : HOUSE_RULES;
}
