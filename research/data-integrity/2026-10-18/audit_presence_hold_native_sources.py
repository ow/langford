"""Read-only native source census of 63 presence holds, without changing guards."""
import json,hashlib,re,subprocess
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,timezone
from bs4 import BeautifulSoup
from pipeline.ingestion.official_ballots import load_official_minutes
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent;CACHE=Path('/private/tmp/presence-hold-native-review');CACHE.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();norm=lambda s:re.sub(r'[^a-z0-9]+',' ',s.casefold()).strip()
def main():
 census_file=Path('/private/tmp/langford-presence179-event-census.json');events=json.loads(census_file.read_bytes());groups=defaultdict(list)
 for e in events:groups[e['meeting_id']].append(e)
 snap=json.loads((OUT/'ballot-source-current-snapshot.json').read_bytes());meetings={m['id']:m for m in snap['meetings']};people=json.loads((OUT/'vote-people-current-snapshot.json').read_bytes());records=[]
 for mid,items in groups.items():
  meeting=meetings[mid];source=load_official_minutes(meeting,root=ROOT,people=people,cache_dir=CACHE/'sources');assert not source.get('error'),(mid,source)
  original=ROOT/source['source_file'];assert sha(original)==source['source_sha256'];target=CACHE/(source['source_sha256']+'.txt')
  if original.suffix=='.html':native=BeautifulSoup(original.read_text(),'html.parser').get_text('\n',strip=True);target.write_text(native)
  else:subprocess.run(['pdftotext','-layout',str(original),str(target)],check=True,capture_output=True);native=target.read_text()
  text=source['text'];enriched=[]
  for event in items:
   pos=event['offset'];start=text.rfind('\n\n',0,pos);stop=text.find('\n\n',pos)
   start=max(0,start+2) if start>=0 else 0;stop=stop if stop>=0 else len(text)
   paragraph=text[start:stop].strip();context=text[max(0,pos-450):min(len(text),pos+850)]
   evidence=paragraph if paragraph else context
   enriched.append({**event,'native_paragraph':evidence,'native_paragraph_found_in_raw_source':norm(evidence) in norm(native),'source_context':context})
  records.append({'meeting_id':mid,'stored_date':meeting['meeting_date'],'native_date':source.get('local_date'),'native_date_evidence':source.get('source_date_evidence'),'catalog_classification':meeting['classification'],'native_classification':source['source_classification'],'source_file':source['source_file'],'source_url':source['source_url'],'source_sha256':source['source_sha256'],'fresh_native_text_sha256':sha(target),'affected_motions':sorted(set(m for e in items for m in e['affected_motions'])),'events':enriched})
 output={'mode':'read_only_native_presence_hold_census','at':datetime.now(timezone.utc).isoformat(),'input_sha256':sha(census_file),'summary':{'meetings':len(records),'unique_held_events':len(events),'affected_motions':len(set(m for r in records for m in r['affected_motions'])),'native_classifications':dict(Counter(r['native_classification'] for r in records)),'events_raw_native_quote_verified':sum(e['native_paragraph_found_in_raw_source']for r in records for e in r['events']),'database_writes':0},'records':records}
 p=OUT/'presence179-native-source-census.json';p.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output['summary']));print('sha256',sha(p))
if __name__=='__main__':main()
