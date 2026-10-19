"""Conservative recovery of outcomes from official minutes, never attendance ballots."""
import re
from difflib import SequenceMatcher


def normalize_text(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def minutes_motion_blocks(minutes):
    """Keep a recorded decision bounded by its own mover and the next mover.

    Markdown exports may repeat the minutes; identical normalized blocks are
    deduplicated. Notices and narrative without an explicit outcome stay unknown.
    """
    seen = set()
    starts = list(re.finditer(r"(?im)^[ \t]*\*{0,2}MOVED\s+BY\b\s*:?", minutes))
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(minutes)
        block = minutes[match.start():end]
        outcome = re.search(r"(?im)^\s*\*{0,2}(?:Motion\s+)?(CARRIED(?:\s+UNANIMOUSLY)?|DEFEATED|WITHDRAWN|NOT CARRIED|TABLED)\b[^\n]*", block)
        if not outcome:
            continue
        # Motion text begins after the seconder line and before its outcome.
        before = block[:outcome.start()]
        seconder = re.search(r"(?im)^.*SECONDED[^\n]*\n", before)
        body = before[seconder.end():] if seconder else before
        # Remove role-only name lines from exported blank MOVED BY/SECONDED rows.
        start = re.search(r"\bTHAT\b", body, re.I)
        if start:
            body = body[start.start():]
        key = normalize_text(body)
        source_key = normalize_text(block)
        if len(key)<25 or source_key in seen:
            continue
        seen.add(source_key)
        yield {"motion_text": body.strip(), "result": outcome.group(1).upper(),
               "outcome_quote": outcome.group(0).strip(),
               "after_outcome": block[outcome.end():].strip(), "source_block": block.strip()}


def match_minutes_motion(motion_text, minutes, *, threshold=1.0, margin=0.06):
    """Return an exact normalized source motion or None; ambiguity requires no write.

    No fuzzy matching is eligible for persistence: a one-digit bylaw/address or
    amount change, or added negation, can reverse which decision is identified.
    """
    target = normalize_text(motion_text)
    candidates=[]
    for block in minutes_motion_blocks(minutes):
        score=SequenceMatcher(None,target,normalize_text(block['motion_text']),autojunk=False).ratio()
        candidates.append((score,block))
    candidates.sort(key=lambda pair:pair[0],reverse=True)
    if not candidates or candidates[0][0]<threshold:
        return None
    if len(candidates)>1 and candidates[0][0]-candidates[1][0]<margin:
        return None
    score,block=candidates[0]
    return {**block,"match_score":round(score,5)}



def named_votes(block, canonical_names):
    """Validate explicit source choices only; never trust model or attendance votes.

    Read at most nine lines after a uniquely matched official decision, stop at
    the next decision, and resolve surnames uniquely to existing canonical names.
    An outcome/unanimity alone never supplies a person's choice.
    """
    if not block:
        return []
    after = '\n'.join(block['after_outcome'].splitlines()[:9])
    after = re.split(r'(?im)^\s*\*{0,2}(?:Motion\s+)?(?:CARRIED|DEFEATED|WITHDRAWN)\b', after)[0]
    after = re.split(r'(?m)^\s*\d+\.(?:\d+)?\s+[A-Z]', after)[0]
    surnames = {}
    for name in set(canonical_names):
        parts = normalize_text(name).split()
        if len(parts) >= 2 and len(parts[-1]) >= 3:
            surnames.setdefault(parts[-1], []).append(name)
    votes=[]
    for line in after.splitlines():
        clean=re.sub(r'[*_>]', '', line).strip()
        prefix=re.match(r'(OPPOSED|AGAINST|NO|IN FAVOU?R|YES|ABSTAIN(?:ED)?|RECUSED)\s*:\s*(.+)',clean,re.I)
        suffix=re.match(r'((?:\d+\s+)?(?:Mayor|Councillors?|Committee [Mm]ember)\s+.+?)\s+(opposed|voted against|voted (?:in )?favou?r|voted yes|voted no|abstained|recused)\b',clean,re.I)
        if prefix:
            verb,names=prefix.groups()
        elif suffix:
            names,verb=suffix.groups()
        else:
            continue
        names=re.split(r'\bOn the (?:Main )?Motion\b|\s+\d+\.(?:\d+)?\s',names,flags=re.I)[0].strip()
        # A suffix quote ends at the choice, before e.g. a returning attendee.
        quote=clean[:suffix.end()] if suffix and not prefix else f'{verb}: {names}'
        if normalize_text(quote) not in normalize_text(block['source_block']):
            continue
        verb=verb.casefold()
        choice='Yes' if verb in ('yes','in favour','in favor','voted in favour','voted in favor','voted favour','voted favor','voted yes') else 'Abstain' if verb.startswith('abstain') else 'Recused' if verb.startswith('recus') else 'No'
        for surname,known in surnames.items():
            if len(known)==1 and re.search(r'\b'+re.escape(surname)+r'\b',normalize_text(names)):
                votes.append({'person_name':known[0],'vote':choice,'source_quote':quote})
    choices={}
    for vote in votes:choices.setdefault(vote['person_name'],set()).add(vote['vote'])
    # Contradictory source choices remain held; duplicated exports are harmless.
    unique={}
    for vote in votes:
        if len(choices[vote['person_name']])==1:unique[(vote['person_name'],vote['vote'])]=vote
    return list(unique.values())


def outcome_family(result):
    result=normalize_text(result)
    if result.startswith('carried') or result=='passed':return 'passed'
    if result in ('defeated','not carried','failed'):return 'failed'
    return result


def critical_identity(text):
    """Protect identifiers, quantities/units, action polarity and conditions."""
    numbers=tuple(re.findall(r'\$?\d[\d,]*(?:\.\d+)?%?',text or ''))
    protected={'not','no','never','without','unless','except','against','deny','refuse','reject','approve','adopt','receive','authorize','include','exclude','remove','reduce','increase','amend','delete','retain','proceed','defer','table','refer','rescind','waive','terminate'}
    words=normalize_text(text).split()
    return numbers,tuple(sorted(w for w in words if w in protected))


def match_motion_record(motion,minutes):
    """Prefer exact motion text; permit a uniquely verified verbatim source anchor.

    A source quote may rescue editorial wording only when identifiers/quantities,
    polarity and every substantive proposed token are supported by that quote.
    Callers persist the official motion text for quote-rescued proposals, retaining
    the proposal separately so a shortened description cannot alter the decision.
    """
    source=match_minutes_motion(motion.get('motion_text'),minutes)
    if source:return {**source,'anchor_method':'exact_motion_text'}
    quote=motion.get('motion_source_quote')
    if not quote or critical_identity(motion.get('motion_text'))!=critical_identity(quote):return None
    stop={'the','a','an','that','to','of','for','and','be','is','as','by','with','it','its','on','in','at','from','this','these','those'}
    proposed=set(normalize_text(motion.get('motion_text')).split())-stop
    official=set(normalize_text(quote).split())-stop
    if not proposed or not proposed<=official:return None
    source=match_minutes_motion(quote,minutes)
    return {**source,'anchor_method':'verbatim_quote_exact_identity'} if source else None
