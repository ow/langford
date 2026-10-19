/** A named identity, rather than a diarization cluster or anonymous role label. */
export function isNamedParticipant(name: string): boolean {
  const label = name.trim().replace(/[_-]+/g, " ");
  return !!label && !/^(?:(?:unknown|unidentified|anonymous)\b|(?:speaker|spk|participant)(?:[\s_-]|\d|$)|(?:mayor|chair|councillor|councilor|staff|public(?: speaker)?|guest(?: speaker)?|multiple speakers)$)/i.test(label);
}
