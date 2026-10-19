"""Hypothetical documentary membership census. NO database/source-code writes.

The oath-backed membership proposal is injected only into in-memory audit data.
Generic role-only physical events are held, except the individually documented
June6,2022 unique MayorYoung return proposal (reported separately).
"""
import json,re,hashlib
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import audit_full_ballots as a
from pipeline.ingestion.official_ballots import inspect_motion,event_timeline
OUT=Path(__file__).parent
roles=[(133,'D. Blackwell','Denise Blackwell','Councillor','2018-11-05'),(134,'M. Sahlstrom','Matt Sahlstrom','Councillor','2018-11-05'),(135,'L. Seaton','Lanny Seaton','Councillor','2018-11-05'),(136,'N. Stewart','Norma Stewart','Councillor','2018-11-05'),(137,'R. Wade','Roger Wade','Councillor','2018-11-05'),(35,'Lillian Szpak','Lillian Szpak','Councillor','2018-11-05'),(143,'Stew Young','Stewart Young','Mayor','2018-11-19')]
proposals=[{'person_id':pid,'name':old,'canonical_full_name_proposal':full,'organization_id':1,'organization_name':'Council','classification':'Council','role':role,'start_date':start,'end_date':'2022-11-06','proposal_only':True} for pid,old,full,role,start in roles]
new_memberships=a.data['memberships']+proposals
live=json.loads((OUT/'full-current-vote-inventory.json').read_text());has_rows={v['motion_id'] for v in live['votes']}
remaining=[m for m in a.data['motions'] if m['result'] and m['id'] not in has_rows]
ids=sorted({m['meeting_id'] for m in remaining})
with ThreadPoolExecutor(max_workers=4) as pool:sources=dict(zip(ids,pool.map(a.source_for,[a.meetings[mid] for mid in ids])))
results=[];role_proposals=[]
for m in remaining:
 original=sources[m['meeting_id']];source=dict(original)
 if source.get('error'):results.append({'motion_id':m['id'],'status':source['error']});continue
 source['presence_events'],source['unknown_presence_events']=event_timeline(source,new_memberships)
 # Do not mistake ignored role-only return language for continuous absence.
 generic=list(re.finditer(r'\b[Tt]he\s+(?:Mayor|Chair|Acting Mayor)\s+(?:left|returned|arrived|joined|departed|exited|rejoined|disconnected|reconnected)\b',source['text']))
 for hit in generic:
  quote=source['text'][hit.start():hit.end()+100].split('\n\n')[0]
  source['unknown_presence_events'].append({'offset':hit.start(),'reason':'generic_role_presence_needs_unique_official_role_binding','source_quote':quote})
 inspected=inspect_motion(m,source,meeting=a.meetings[m['meeting_id']],people=a.people,memberships=new_memberships,policy=a.policy)
 inspected['hypothesis']='only_documented_2018_memberships_added_in_memory';results.append(inspected)
 if m['id'] in (2570,2571):
  scoped=dict(source);scoped['unknown_presence_events']=[e for e in source['unknown_presence_events'] if e.get('reason')!='generic_role_presence_needs_unique_official_role_binding']
  hits=[h for h in generic if source['text'][h.start():h.end()]=='The Mayor returned']
  if len(hits)!=1:continue
  h=hits[0];returnquote=re.match(r'The Mayor returned to the meeting at 5:37pm\.',source['text'][h.start():])
  if not returnquote or not re.search(r'PRESENT:[\s\S]{0,100}Mayor S\. Young',source['text']):continue
  event={'offset':h.start(),'person_id':143,'state':'present','source_quote':returnquote[0],'verb':'returned','role_binding_proposal':{'official_role':'Mayor','official_roster_identity':'Mayor S. Young','dated_person_id':143,'other_temporary_role':'Councillor Wade assumed the role as Chair (not Mayor)'}}
  scoped['presence_events']=sorted(source['presence_events']+[event],key=lambda e:e['offset'])
  proposal=inspect_motion(m,scoped,meeting=a.meetings[m['meeting_id']],people=a.people,memberships=new_memberships,policy=a.policy)
  proposal['role_binding_proposal']=event;role_proposals.append(proposal)
summary={'database_writes':0,'source_code_writes':0,'scope_resulted_motions_without_rows':len(remaining),'hypothetical_memberships':len(proposals),'statuses':dict(Counter(r['status'] for r in results)),'potential_complete_choices':sum(len(r.get('votes',[])) for r in results if r['status']=='reconstructable_candidate'),'role_bound_case_statuses':dict(Counter(r['status'] for r in role_proposals)),'additional_role_bound_choices':sum(len(r.get('votes',[])) for r in role_proposals if r['status']=='reconstructable_candidate')}
(OUT/'historical-membership-unlock-proposals.json').write_text(json.dumps({'summary':summary,'membership_proposals':proposals,'motions':results,'separate_role_binding_proposals':role_proposals},indent=2));print(json.dumps(summary,indent=2),flush=True)
