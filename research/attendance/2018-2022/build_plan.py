"""Bind a visually reviewed finite roster ledger to original source bytes."""
import argparse, hashlib, json
from pathlib import Path
from collections import Counter
MAPPING={'Y':143,'D':133,'M':134,'L':135,'N':136,'S':35,'R':137}
a=argparse.ArgumentParser();a.add_argument('--extracted',required=True);a.add_argument('--reviewed',required=True);a.add_argument('--before',required=True);a.add_argument('--output',required=True);args=a.parse_args()
x=json.loads(Path(args.extracted).read_text());review=json.loads(Path(args.reviewed).read_text());before=json.loads(Path(args.before).read_text())
assert len(x['meetings'])==89 and len(review['reviewed'])==88
records=[];sources=[];holds=[]
# These image-only originals have no usable native text. Roster transcriptions
# were checked against the rendered originals, not a model-produced summary.
scanned_quotes={
73:'PRESENT: Mayor S. Young; Councillors: D. Blackwell, M. Sahlstrom, L. Seaton, N. Stewart, L. Szpak and R. Wade.',
119:'PRESENT: Remote by telephone: Mayor S. Young; Councillors: D. Blackwell, M. Sahlstrom, L. Seaton, N. Stewart, L. Szpak, and R. Wade.',
142:'PRESENT: Remote by telephone: Mayor S. Young; Councillors: D. Blackwell, M. Sahlstrom, L. Seaton, N. Stewart, and L. Szpak. ABSENT: Councillor R. Wade.',
223:'PRESENT: Mayor Young, D. Blackwell, L. Seaton, N. Stewart, and L. Szpak. By Teleconference: M. Sahlstrom and R. Wade.',
204:'PRESENT: Mayor S. Young; Councillor D. Blackwell; Councillor L. Szpak; Councillor N. Stewart; Councillor M. Sahlstrom; Councillor L. Seaton; Councillor R. Wade - Remote.',
279:'PRESENT: Mayor S. Young; Councillor D. Blackwell; Councillor M. Sahlstrom; Councillor L. Seaton; Councillor N. Stewart; Councillor L. Szpak; Councillor R. Wade.',
42:'PRESENT: Mayor S. Young; Councillor D. Blackwell; Councillor M. Sahlstrom; Councillor L. Seaton; Councillor N. Stewart; Councillor L. Szpak; Councillor R. Wade.'}
for m in x['meetings']:
 mid=m['meeting_id']
 if mid==123:continue
 source=m['source'];assert source and source['source_url'].startswith(('https://langford.ca/','https://pub-langford.escribemeetings.com/'))
 assert hashlib.sha256(Path(source['file_path']).read_bytes()).hexdigest()==source['source_sha256']
 encoded=review['reviewed'][str(mid)].split('|');assert len(encoded)==3 and sorted(''.join(encoded))==sorted(MAPPING)
 sources.append({k:source[k]for k in ['source_url','source_sha256','file_path','document_id','page_count']}|{'meeting_id':mid,'local_date':m['local_date'],'visual_date_and_roster_reviewed':True})
 native=source['first_page_text'].strip();quote=scanned_quotes.get(mid)or native
 assert quote
 for i,group in enumerate(encoded):
  for letter in group:
   if i==2:holds.append({'meeting_id':mid,'person_id':MAPPING[letter],'reason':next((reason for key,reason in review['unknown_reasons'].items()if key.split(':')[0]==str(mid)and letter in key.split(':')[1]),'No explicit entry')});continue
   state=['present','absent'][i]
   surname=x['council_mapping'][str(MAPPING[letter])][2]
   sections=[sec for sec in source['sections'] if (sec['heading']=='PRESENT')==(state=='present') and surname.lower() in sec['quote'].lower()]
   record_quote=(sections[0]['heading']+'\n'+sections[0]['quote']) if sections else quote
   if mid in scanned_quotes:record_quote=quote
   evidence={'schema':'council-attendance/v1','method':'original_roster','state':state,'meeting_id':mid,'person_id':MAPPING[letter],
     'local_date':m['local_date'],'source_url':source['source_url'],'source_sha256':source['source_sha256'],'source_page':1,
     'source_quote':record_quote,'review':'Original page image; explicit named roster section. Presence does not assert full-meeting duration or physical modality.',
     'reviewed_meeting_state':state}
   override=review.get('body_overrides',{}).get(f'{mid}:{letter}')
   if override:evidence.update(override)
   assert evidence['state']==state
   records.append({'meeting_id':mid,'person_id':MAPPING[letter],'attendance_mode':'Unknown'if state=='present'else'Absent','notes':json.dumps(evidence,sort_keys=True,separators=(',',':'))})
assert len(records)==605 and len(holds)==11
assert len({(r['meeting_id'],r['person_id'])for r in records})==605
plan={'schema':'attendance-correction/v1','finite_meeting_ids':[m['id']for m in before['meetings']],
      'before_sha256':hashlib.sha256(Path(args.before).read_bytes()).hexdigest(),
      'review_sha256':hashlib.sha256(Path(args.reviewed).read_bytes()).hexdigest(),
      'sources':sources,'records':sorted(records,key=lambda r:(r['meeting_id'],r['person_id'])),'holds':holds,'cancellation':review['cancellation']}
Path(args.output).write_text(json.dumps(plan,indent=2)+'\n')
print(json.dumps({'verified_records':len(records),'states':dict(Counter(json.loads(r['notes'])['state']for r in records)),'holds':len(holds),'sources':len(sources),'plan_sha256':hashlib.sha256(Path(args.output).read_bytes()).hexdigest()}))
