"""Execute an explicitly approved exact merge proposal with CAS and rollback.

Default is validation only. Live use requires --apply and approval of the exact
proposal scope. Keep the before-values file private; never overwrite it.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from supabase import create_client
from pipeline.config import SUPABASE_URL,SUPABASE_SECRET_KEY

ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser()
p.add_argument('--proposal',type=Path,required=True)
p.add_argument('--plan',type=Path,required=True)
p.add_argument('--rollback',type=Path,required=True)
p.add_argument('--receipt',type=Path,required=True)
p.add_argument('--apply',action='store_true')
args=p.parse_args()
proposal=json.loads(args.proposal.read_text())
plan=json.loads(args.plan.read_text())
assert proposal['plan_sha256']==hashlib.sha256(args.plan.read_bytes()).hexdigest()
changes=proposal['changes']
ids=[c['id'] for c in changes]
assert len(ids)==len(set(ids))
canonical_ids={c['id'] for c in changes if c['role']=='canonical'}
for change in changes:
    if change['role']=='alias':
        target=change['after']['meta']['canonical_matter_id']
        assert target in canonical_ids and target!=change['id']
    else:
        assert not change['after']['meta'].get('canonical_matter_id')
# Recheck immutable source proof before any network mutation.
for group in plan['groups']:
    if group['mode']!='safe':continue
    for member in group['members']:
        for proof in member['source_proofs']:
            assert hashlib.sha256((ROOT/proof['source_file']).read_bytes()).hexdigest()==proof['source_sha256']
client=create_client(SUPABASE_URL,SUPABASE_SECRET_KEY)
columns='id,title,identifier,status,category,first_seen,last_seen,meta,municipality_id,bylaw_id'
current=client.table('matters').select(columns).in_('id',ids).execute().data
by_id={row['id']:row for row in current}
for change in changes:
    assert by_id.get(change['id'])==change['before'],f'Current row changed{change["id"]}; refresh/review proposal'
item_columns='id,matter_id,title,meeting_id,matter_status_snapshot'
links=client.table('agenda_items').select(item_columns).in_('matter_id',ids).order('id').execute().data
assert links==sorted(proposal['unchanged_agenda_links'],key=lambda a:a['id']),'Agenda scope changed; replan'
assert not args.rollback.exists(),'Never overwrite before-values'
backup={'at':datetime.now(timezone.utc).isoformat(),'proposal_sha256':hashlib.sha256(args.proposal.read_bytes()).hexdigest(),
    'records':[{'before':c['before'],'after':c['after'],'applied':False} for c in changes], 'agenda_links_before':links}
args.rollback.write_text(json.dumps(backup,indent=2)+'\n');args.rollback.chmod(0o600)
print(f'Validated{len(canonical_ids)}groups/{len(ids)-len(canonical_ids)}aliases. apply={args.apply}',flush=True)
if args.apply:
    for record in backup['records']:
        before=record['before']
        query=client.table('matters').update(record['after']).eq('id',before['id']).eq('status',before['status'])
        for key in ['meta','first_seen','last_seen']:
            value=before[key]
            query=query.is_(key,'null') if value is None else query.eq(key,json.dumps(value,separators=(',',':')) if key=='meta' else value)
        response=query.execute()
        assert len(response.data)==1,f'Concurrent change{before["id"]}; stop and inspect rollback receipt'
        record['applied']=True
        args.rollback.write_text(json.dumps(backup,indent=2)+'\n')
    after_links=client.table('agenda_items').select(item_columns).in_('matter_id',ids).order('id').execute().data
    assert links==after_links,'Concurrent agenda changes; inspect before-values'
    retained=client.table('matters').select('id,meta,status,first_seen,last_seen').in_('id',ids).execute().data
    assert len(retained)==len(ids),'Original IDs must all remain'
    receipt={'mode':'applied','at':datetime.now(timezone.utc).isoformat(),'groups':len(canonical_ids),
        'aliases':len(ids)-len(canonical_ids),'original_ids_retained':len(retained),'agenda_links_unchanged':len(links),
        'canonical_ids':sorted(canonical_ids),'after':retained,'proposal_sha256':backup['proposal_sha256']}
    args.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
    print('Applied and verified all reviewed aliases',flush=True)
