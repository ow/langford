"""Read-only independent native-source review of 56 proposed source corrections.

No model verdict is evidence. No database writes or production module edits.
Reuses the independent reviewer's native extraction/identity/presence replay,
never the production source matcher or proposed model equivalence verdicts.
"""
from pathlib import Path
import importlib.util,json,re,hashlib,difflib
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timezone

OUT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('native_reviewer',OUT/'review_remaining_ballots_independently.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
snapshot=json.loads((OUT/'ballot-source-snapshot.json').read_text())
native.motions.update({m['id']:m for m in snapshot['motions']})
native.meetings.update({m['id']:m for m in snapshot['meetings']})
native.live['memberships']=snapshot['memberships']
inventory=json.loads((OUT/'full-current-vote-inventory.json').read_text())
native.existing=defaultdict(list)
for vote in inventory['votes']:native.existing[vote['motion_id']].append(vote)
inputs=['source-anchor-reconciliation.json','semantic-ballot-proposals.json']
rows={};origins={}
for filename in inputs:
 for row in json.loads((OUT/filename).read_text())['motions']:
  if row['status']=='reconstructable_candidate':
   rows[row['motion_id']]=row;origins.setdefault(row['motion_id'],[]).append(filename)
assert len(rows)==56

def load(item):
 key,proposal=item
 try:return key,native.read_source(proposal)
 except Exception as error:return key,{'error':str(error)}
unique={r['source_file']:r for r in rows.values()}
with ThreadPoolExecutor(max_workers=4)as pool:sources=dict(pool.map(load,unique.items()))

def item_number(source,block):
 headers=list(re.finditer(r'(?m)^[ \t]{0,10}(\d+(?:\.\d+)*)\.?\s+[A-Z][^\n]*',source['text'][:block['start']]))
 return headers[-1][1].strip('.')if headers else None

def actor_identity(block,field,pool):
 label=r'MOVED\s+BY'if field=='mover'else r'SECONDED(?:\s+BY)?'
 found=re.search(r'(?im)^\s*'+label+r'\s*[:;]?\s*([^\n]+)',block['block'])
 assert found,'native_'+field+'_missing'
 spans,ambiguous=native.exact_name_spans(found[1],pool,allow_surnames=True)
 ids={s[2]for s in spans}
 assert len(ids)==1 and not ambiguous,'native_'+field+'_not_unique'
 return next(iter(ids)),found[0].strip()

# Independent diff inspection found these change the operative status, retain
# non-operative material, or have unresolved native glyph/word ambiguities.
semantic_holds={
 1926:'proposed_body_starts_mid_whereas_clause',1927:'proposed_body_starts_mid_whereas_clause',
 2053:'proposed_body_has_dangling_conjunction',
 3326:'unresolved_native_extraction_word_fopthe',3328:'unresolved_native_extraction_word_ip',
 3335:'unresolved_statutory_clause_l_vs_uppercase_I',
}
notes={1819:'Operative purchase, ceiling, funding, borrowing and no-renewal conditions all retained; background recitals remain in original-text provenance.',
 2103:'Restores exact agenda correspondence subject Regional Units; withdrawal actor/date unchanged.',
 2283:'Restores omitted patron-use qualification; amount, facility, retained ownership and actors unchanged.',
 2384:'Restores omitted minor-amendments signing qualification; lease term, date and signing actors unchanged.'}
for mid in [2651,2652,2653,2654]:notes[mid]='Substantive source correction: restores omitted recommend-that-Council wrapper. This is a COTW recommendation, not a final Council directive; all original funding subjects/amounts remain.'
notes[2678]='Substantive source correction: restores omitted amendment wrapper; the added dust-bylaw-report clause and timing remain unchanged. This records an amendment, not a standalone final main motion.'
closure_ids={227,272,1645,2029,2032,2171,2247,2452,2554,2888,2899,3251,3450,3744}
for mid in closure_ids:notes[mid]='Restores complete statutory subject qualifiers within the same exact cited Community Charter clauses; closure action/time/citations preserved.'
records=[]
for mid,proposal in sorted(rows.items()):
 anchor=proposal.get('semantic_anchor_proposal')or proposal['source_anchor_reconciliation']
 old=anchor['original_motion_text'];official=anchor['official_motion_text']
 record={'motion_id':mid,'meeting_id':proposal['meeting_id'],'status':'hold','origin_artifacts':origins[mid],
  'original_motion_text':old,'proposed_official_motion_text':official,'source_file':proposal['source_file']}
 try:
  source=sources[proposal['source_file']]
  assert not source.get('error'),source.get('error')
  current=native.motions[mid];meeting=native.meetings[current['meeting_id']]
  assert native.norm(current['text_content'])==native.norm(old),'current_snapshot_text_differs'
  assert source['date']==proposal['source_date'],'native_proposal_date_mismatch'
  assert abs((date.fromisoformat(source['date'])-date.fromisoformat(meeting['meeting_date'][:10])).days)<=1,'native_catalog_date_mismatch'
  assert ('Committee of the Whole'in meeting['title'])==(source['source_body']=='Committee of the Whole'),'native_catalog_body_mismatch'
  if source['source_body']=='Committee of the Whole':assert source['date']>='2021-10-18','cotw_recording_rule_predates_verified_scope'
  candidates=[b for b in source['blocks']if native.norm(b['body'])==native.norm(official)]
  assert len(candidates)==1,'native_formal_body_not_unique:'+str(len(candidates))
  block=candidates[0]
  assert native.family(block['result'])==native.family(current['result'])==native.family(proposal['source_result']),'native_outcome_mismatch'
  expected_item=str(current.get('item_order')or anchor.get('source_item_number')or anchor.get('agenda_item_order')or'').strip('.')
  actual_item=item_number(source,block)
  assert expected_item and actual_item==expected_item,'native_agenda_anchor_mismatch:'+str(actual_item)+'/'+expected_item
  actors={}
  for field in ['mover','seconder']:
   actual,quote=actor_identity(block,field,source['pool'])
   expected=current.get(field)or anchor.get('source_'+field)or anchor.get(field)
   assert expected,'stored_'+field+'_not_recorded'
   spans,ambiguous=native.exact_name_spans(expected,source['pool'],allow_surnames=True)
   assert not ambiguous and {s[2]for s in spans}=={actual},'native_'+field+'_anchor_mismatch'
   actors[field]={'person_id':actual,'native_quote':quote,'stored_actor':expected}
  # Only one scoped source motion with these canonical actors is allowed.
  alternatives=[]
  for candidate in source['blocks']:
   if item_number(source,candidate)!=expected_item:continue
   try:
    pair={field:actor_identity(candidate,field,source['pool'])[0]for field in actors}
    if pair=={field:value['person_id']for field,value in actors.items()}:alternatives.append(candidate)
   except AssertionError:continue
  if len(alternatives)>1:
   # Same actor pair may move several different amendments in one item. Bind
   # every original substantive word and number, rather than selecting by rank.
   stop={'the','a','an','that','to','of','for','and','be','is','as','by','with','it','its','on','in','at','from','this','these','those','moved','seconded','motion','carried'}
   required=set(native.norm(old).split())-stop
   quantities=re.findall(r'\d+(?:[.,:/-]\d+)*',old)
   alternatives=[candidate for candidate in alternatives if required<=(set(native.norm(candidate['body']).split())-stop) and re.findall(r'\d+(?:[.,:/-]\d+)*',candidate['body'])==quantities]
  assert len(alternatives)==1 and alternatives[0]['start']==block['start'],'multiple_same_agenda_actor_identity_motions:'+str(len(alternatives))
  assert not re.search(r'(?im)^\s*(?:OPPOSED\s*:|(?:Mayor|Councillors?)\s+.+\b(?:opposed|gave a brief update)\b)',official),'proposed_motion_contains_vote_or_narrative_material'
  assert mid not in semantic_holds,semantic_holds.get(mid)
  # Critical quantities/citations and negation cannot disappear in a correction.
  numbers=lambda text:re.findall(r'\d+(?:[.,:/-]\d+)*',text)
  assert numbers(old)==numbers(official),'critical_number_sequence_differs'
  negative=lambda text:Counter(re.findall(r'\b(?:not|no|never|unless|without)\b',text.lower()))
  assert all(negative(official)[k]>=v for k,v in negative(old).items()),'stored_negation_removed'
  assert native.rule['enabled_from']<=source['date']<=native.rule['enabled_through']or'UNANIMOUS'in block['result'],'recording_rule_outside_verified_period'
  voters,events=native.present_at_vote(source['roster'],source['events'],source['unknown_events'],block['vote_offset'])
  active={p['id']for p in source['pool']}
  assert 4<=len(voters)<=7 and voters<=active,'dated_membership_or_quorum_not_proven'
  proposed={v['person_id']:v['vote']for v in proposal['votes']}
  assert len(proposed)==len(proposal['votes'])and set(proposed)==voters,'independent_voter_set_differs'
  for v in proposal['votes']:assert native.persons[v['person_id']]['name']==v['person_name'],'canonical_identity_differs'
  named,namedproof=native.decision_choices(block,source['pool'])
  assert set(named)<=voters,'named_voter_not_present'
  choices={pid:named.get(pid,'Yes')for pid in voters}
  assert choices==proposed,'independent_choices_differ'
  if'UNANIMOUS'in block['result']:assert all(v=='Yes'for v in choices.values()),'unanimity_conflicts'
  yes=sum(v=='Yes'for v in choices.values());no=sum(v=='No'for v in choices.values())
  assert(native.family(block['result'])=='passed')==(yes>no),'independent_tally_conflicts'
  assert all(choices.get(v['person_id'])==v['vote']for v in native.existing[mid]),'current_existing_choice_conflict'
  newchoices=[{'motion_id':mid,'person_id':pid,'vote':vote}for pid,vote in sorted(choices.items())if pid not in{v['person_id']for v in native.existing[mid]}]
  record.update({'status':'reviewed_source_correction','source_sha256':source['sha256'],'source_url':source['url'],'native_text_sha256':source['native_text_sha256'],
   'source_date':source['date'],'source_body':source['source_body'],'native_agenda_item':actual_item,'actors':actors,'scoped_formal_alternatives':len(alternatives),
   'critical_number_sequence':numbers(old),'qualification_review':notes.get(mid,'Only formatting/editorial wrappers changed; operative subject/action, identifiers, negation and qualifiers preserved.'),
   'source_motion_text':block['body'],'source_block':block['block'],'outcome_quote':block['outcome_quote'],'roster_quote':source['roster_quote'],
   'roster_person_ids':sorted(source['roster']),'present_person_ids':sorted(voters),'independent_events':events,'named_choice_proof':namedproof,
   'choices':[{'person_id':pid,'vote':choices[pid]}for pid in sorted(choices)],'new_choices':newchoices,'yes':yes,'no':no,
   'existing_choice_verification':{'written_snapshot_at':inventory['at'],'existing_vote_ids':[v['id']for v in native.existing[mid]],'requires_apply_CAS':True},
   'source_correction_kind':'substantive_omitted_recommendation_or_amendment_wrapper'if mid in[2651,2652,2653,2654,2678]else'restore_verbatim_official_formal_motion',
   'required_provenance':{'original_motion_text':old,'method':'independently_source_bound_verbatim_correction','not_model_verdict_evidence':True},
   'checks':['fresh_native_pdf_sha256','official_url','header_date_and_body','unique_exact_formal_body','unique_same_agenda_and_canonical_mover_seconder',
    'critical_ids_quantities_negation_and_qualifiers','independent_roster_and_presence_replay','dated_council_memberships','complete_named_dissent','independent_tally']})
 except Exception as error:record['reason']=str(error)
 records.append(record)
result={'mode':'independent_native_source_anchor_review_no_DB_writes_no_model_calls','at':datetime.now(timezone.utc).isoformat(),
 'input_sha256':{f:hashlib.sha256((OUT/f).read_bytes()).hexdigest()for f in inputs+['ballot-source-snapshot.json','full-current-vote-inventory.json']},'reviewer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'summary':{'candidates':len(records),'reviewed':sum(r['status']=='reviewed_source_correction'for r in records),'held':sum(r['status']=='hold'for r in records),
 'reviewed_new_choices':sum(len(r.get('new_choices',[]))for r in records),'hold_reasons':dict(Counter(r['reason']for r in records if r['status']=='hold'))},'records':records}
(OUT/'extra-source-anchor-independent-review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['summary'],indent=2),flush=True)
