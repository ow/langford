"""Offline reviewable canonicalization updates. No database access or writes."""
import hashlib
import json
from pathlib import Path
from pipeline.ingestion.matter_lifecycle import lifecycle_evidence

OUT=Path(__file__).parent
ROOT=Path(__file__).resolve().parents[3]
data=json.loads(Path('/private/tmp/matter-merge-scope-data.json').read_text())
plan_path=OUT/'exact-matter-merge-plan.json'
plan=json.loads(plan_path.read_text())
plan_hash=hashlib.sha256(plan_path.read_bytes()).hexdigest()
matters={m['id']:m for m in data['matters']}
meetings={m['id']:m for m in data['meetings']}
updates=[]
for group in plan['groups']:
    if group['mode']!='safe':continue
    ids=group['matter_ids'];canonical=matters[group['canonical_id']]
    members=[matters[mid] for mid in ids]
    assert all(not (m.get('meta') or {}).get('canonical_matter_id') for m in members)
    assert all(not (m.get('meta') or {}).get('merged_matter_ids') for m in members)
    linked_items=[a for a in data['agenda_items'] if a.get('matter_id') in ids]
    item_ids={a['id'] for a in linked_items}
    dates=[str(d)[:10] for m in members for d in [m.get('first_seen'),m.get('last_seen')] if d]
    dates.extend(meetings[a['meeting_id']]['meeting_date'][:10] for a in linked_items)
    meta={**(canonical.get('meta') or {}),'merged_matter_ids':sorted(mid for mid in ids if mid!=canonical['id']),
        'matter_merge':{'rule':'exact_bylaw_set_subject_scope_v1','source_matter_ids':ids,
            'bylaws':group['bylaws'],'reason':group['reason'],'plan_sha256':plan_hash,'links_preserved':True}}
    terminal=[]
    for motion in data['motions']:
        if motion['agenda_item_id'] not in item_ids:continue
        evidence=lifecycle_evidence(canonical,motion)
        if evidence:
            evidence['meeting_date']=meetings[motion['meeting_id']]['meeting_date']
            # Carry independently validated proof only for the exact same motion.
            old=next(((m.get('meta') or {}).get('lifecycle_evidence') for m in members if ((m.get('meta') or {}).get('lifecycle_evidence') or {}).get('motion_id')==motion['id']),None)
            if old:evidence={**evidence,**old}
            terminal.append(evidence)
    status=canonical['status']
    if terminal:
        latest=max(terminal,key=lambda e:(str(e['meeting_date']),e['motion_id']))
        meta['lifecycle_evidence']=latest
        status=latest['status']
    after={'meta':meta,'status':status,'first_seen':min(dates) if dates else None,'last_seen':max(dates) if dates else None}
    updates.append({'id':canonical['id'],'role':'canonical','before':canonical,'after':after})
    for member in members:
        if member['id']==canonical['id']:continue
        updates.append({'id':member['id'],'role':'alias','before':member,'after':{'meta':{
            **(member.get('meta') or {}),'canonical_matter_id':canonical['id'],
            'merge_evidence':{'rule':'exact_bylaw_set_subject_scope_v1','bylaws':group['bylaws'],
                'plan_sha256':plan_hash,'links_preserved':True}}}})
result={'mode':'offline_proposal_not_applied','automatic_approval':'live_apply_rejected_pending_explicit_user_scope_approval',
    'groups':sum(g['mode']=='safe' for g in plan['groups']),'alias_records':sum(u['role']=='alias' for u in updates),
    'plan_sha256':plan_hash,'changes':updates,'unchanged_agenda_links':[a for a in data['agenda_items'] if a.get('matter_id') in {u['id'] for u in updates}]}
(OUT/'exact-matter-merge-updates.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'groups':result['groups'],'alias_records':result['alias_records'],'row_updates':len(updates),'agenda_links_retained':len(result['unchanged_agenda_links'])}))
