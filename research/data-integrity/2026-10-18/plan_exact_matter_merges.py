"""Scope-reviewed exact bylaw alias plan; no fuzzy merging or database writes."""
import hashlib
import json
from pathlib import Path
import re
from pipeline.ingestion.matter_matching import matter_identifiers

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
REASONS = {
    (21,503): ('community standards', 'The same Community Standards2255 and Miscellaneous Amending2262 bundle; committee recommendation/readings/adoption stages.'),
    (32,66,1621): ('animal', 'The same Animal Responsibility2239 and Animal Control Miscellaneous2212 bundle through committee/readings/adoption.'),
    (65,1173): ('streets', 'The same Streets and Traffic2233 and Miscellaneous2181 bundle; drafting/readings/adoption.'),
    (165,803): ('4365', 'Same OCP amendment31/bylaw1840 at4365 West Shore Parkway, first reading and adoption.'),
    (166,804): ('4365', 'Same zoning amendment562/bylaw1841 at4365 West Shore Parkway, first reading and adoption.'),
    (206,217): ('residential', 'Same complete2274/2273 Omnibus68 residential-zone and small-scale housing bundle.206 is an orphan; retain evidenced217 as canonical.'),
    (329,776): ('parking', 'Same Omnibus50 Downtown Parking zoning amendment517/bylaw1752; staff report/first reading/adoption.'),
    (341,814): ('2512', 'Same amendment539/bylaw1792 at2512 Duncan Place; first reading/public hearing/later readings.'),
    (393,1625): ('sook', 'Same amendment527/bylaw1767 C9 Sooke Road rezoning. Shared2682–2706 site; later title also names2668/2674, an evolution within the same numbered bylaw, not a disjoint property.'),
    (506,888): ('jacklin', 'Same amendment762/bylaw2278 at3084/3088/3094/3096 Jacklin Road; application/readings/adoption.'),
    (529,707): ('3130', 'Same amendment483/bylaw1692 at3130 Jacklin Road; reading/rescission/adoption history. A jointly considered1716 OCP bylaw is related context, not a distinct linked property.'),
    (915,1171): ('financial', 'Same bylaw2069 for the2022–2026 Financial Plan, readings and adoption.'),
    (916,1172): ('tax', 'Same bylaw2070 for2022 Tax Rates, readings and adoption.'),
    (993,1050): ('2691', 'Same amendment724/bylaw2174 rezoning at2691 Sooke Road. Associated C9 policy direction is part of the application discussion, not a different property application.'),
    (1070,1428): ('890', 'Same amendment621/bylaw1969 at890 Walfred Road; first reading/hearing/readings/adoption.'),
    (1210,1455): ('2207', 'Same OCP49/bylaw2149 and zoning708/bylaw2150 bundle for2207 Millstream Road; first reading/hearing/readings/adoption.'),
}
HOLDS = {
    (231,661): 'Matter661 includes agenda item1631 solely for Bylaw1703, while its identifier and proposed merge identify1694. Correct the1703 link and re-audit before consolidating.',
    (912,1297): 'Matter912 includes agenda item2622 solely for Bylaw1990 adoption, while its identifier and proposed merge identify1989. Correct the1990 link and re-audit before consolidating.',
}


def normalize(text):
    return re.sub(r'[^a-z0-9]+', ' ', text.casefold()).strip()


def build_plan(data, previous):
    matters = {m['id']:m for m in data['matters']}
    meetings = {m['id']:m for m in data['meetings']}
    agenda_by_matter = {}
    for item in data['agenda_items']:
        agenda_by_matter.setdefault(item.get('matter_id'), []).append(item)
    cache = {}
    groups = []
    for old in previous['duplicate_groups']:
        ids = tuple(old['matter_ids'])
        if ids == (205,218):
            continue
        group = {'matter_ids':list(ids), 'bylaws':old['bylaws'],
            'mode':'hold', 'reason':HOLDS.get(ids), 'members':[]}
        if ids in REASONS:
            anchor, reason = REASONS[ids]
            group.update({'reason':reason, 'canonical_id':217 if ids == (206,217) else min(ids)})
        for mid in ids:
            matter = matters[mid]
            items = agenda_by_matter.get(mid, [])
            member = {'id':mid,'title':matter['title'],'identifier':matter.get('identifier'),
                'status':matter['status'],'agenda_item_ids':[a['id'] for a in items],
                'agenda_items':items, 'source_proofs':[]}
            targets = {p for p in matter_identifiers(matter) if p.startswith('Bylaw ')}
            assert targets == set(old['bylaws']), f'Identity changed for{mid}'
            assert not (matter.get('meta') or {}).get('canonical_matter_id'), f'Already aliased{mid}'
            if ids not in HOLDS:
                # The orphan206 has no links to lose; its full explicit bundle/title
                # is checked against the linked217 official scope source.
                source_items = items or [a for other in ids for a in agenda_by_matter.get(other, [])]
                for target in sorted(targets):
                    number = target.split(' ',1)[1]
                    proof = None
                    for item in source_items:
                        folder = Path(meetings[item['meeting_id']]['archive_path'])
                        if not folder.is_absolute():folder = ROOT/folder
                        for kind, name in [('Minutes','minutes.md'),('Agenda','agenda.md')]:
                            path = folder/name
                            if not path.is_file():continue
                            if path not in cache:cache[path] = path.read_text()
                            text = cache[path]
                            for match in re.finditer(r'(?<!\d)'+re.escape(number)+r'(?!\d)',text):
                                quote = text[max(0,match.start()-600):match.end()+600]
                                norm = normalize(quote)
                                if normalize(anchor) not in norm:continue
                                if not re.search(r'bylaws? (?:no?s? )?'+re.escape(number)+r'\b',norm):continue
                                urls = [p.read_text().strip() for p in sorted((folder/kind).glob('*.url')) if p.read_text().strip()]
                                if not urls:continue
                                proof = {'bylaw':target, 'linked_agenda_item_id':item['id'], 'meeting_id':item['meeting_id'],
                                    'source_file':str(path.relative_to(ROOT)), 'source_urls':urls,
                                    'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'source_quote':quote.strip(),
                                    'subject_anchor':anchor,'orphan_scope_checked_against_linked_member':not bool(items)}
                                break
                            if proof:break
                        if proof:break
                    if proof:member['source_proofs'].append(proof)
            group['members'].append(member)
        if ids not in HOLDS:
            missing = [m['id'] for m in group['members'] if len(m['source_proofs']) != len(group['bylaws'])]
            if missing:
                group['reason'] += f' HOLD: no complete bounded official context proof for members{missing}.'
            else:group['mode'] = 'safe'
        groups.append(group)
    return {'mode':'read_only_scope_review','summary':{'safe_groups':sum(g['mode']=='safe' for g in groups),
        'safe_alias_records':sum(len(g['matter_ids'])-1 for g in groups if g['mode']=='safe'),
        'held_groups':sum(g['mode']=='hold' for g in groups)},'groups':groups}


if __name__ == '__main__':
    data=json.loads(Path('/private/tmp/matter-merge-scope-data.json').read_text())
    previous=json.loads((OUT/'matter-repair-proposal.json').read_text())
    plan=build_plan(data,previous)
    (OUT/'exact-matter-merge-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(plan['summary']))
    for g in plan['groups']:
        print(g['mode'],g['matter_ids'],g['reason'])
