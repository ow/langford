"""Finite original-roster attendance plan. No database access or writes.

Uses the existing pipeline's native PDF reader; PDF geometry separates PRESENT,
ABSENT and ATTENDING even when text order interleaves table columns. Missing
members remain unknown. Original bytes/coordinates and source URLs are retained.
"""
import argparse, hashlib, json, re
from pathlib import Path
from datetime import datetime
import fitz
from pipeline.parser import get_pdf_text

COUNCIL = {143: ('Stew Young','S','Young'),133: ('Denise Blackwell','D','Blackwell'),
           134: ('Matt Sahlstrom','M','Sahlstrom'),135: ('Lanny Seaton','L','Seaton'),
           136: ('Norma Stewart','N','Stewart'),35: ('Lillian Szpak','L','Szpak'),137: ('Roger Wade','R','Wade')}

def section_text(words):
    # Layout order, not PDF content-stream order; preserve token boxes too.
    lines=[]
    for w in sorted(words,key=lambda w:(round(w[1]/3),w[0])):
        if not lines or abs(lines[-1][0]-w[1])>3:lines.append((w[1],[w]))
        else:lines[-1][1].append(w)
    return '\n'.join(' '.join(w[4] for w in sorted(row,key=lambda w:w[0]))for _,row in lines)

def extract(pdf):
    with fitz.open(pdf)as doc:
        page=doc[0];words=page.get_text('words')
        body=[r.y0 for phrase in ['CALL TO ORDER','TERRITORIAL ACKNOWLEDGEMENT','PROCLAMATION RESULTS','SWEARING INTO OFFICE']for r in page.search_for(phrase)]
        stop=min(body)if body else page.rect.height
        headings=[w for w in words if w[4].upper().rstrip(':')in{'PRESENT','ABSENT','REGRETS','ATTENDING'}and w[1]<stop]
        sections=[]
        for h in headings:
            kind=h[4].upper().rstrip(':')
            if kind=='ATTENDING':continue
            end=min([w[1] for w in headings if w[1]>h[1]+3]+[stop])
            selected=[w for w in words if w!=h and h[1]-2<=w[1]<end-2]
            sections.append({'heading':kind,'quote':section_text(selected),'word_boxes':[list(w)for w in selected], 'bounds':[0,h[1]-2,page.rect.width,end-2]})
        return {'first_page_text':page.get_text(),'sections':sections,'page_count':len(doc)}

def main():
    a=argparse.ArgumentParser();a.add_argument('--before',required=True);a.add_argument('--repo',required=True);a.add_argument('--output',required=True);args=a.parse_args()
    before=json.loads(Path(args.before).read_text());out=Path(args.output);out.mkdir(parents=True,exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
    result=[]
    for m in before['meetings']:
        docs=[d for d in before['documents']if d['meeting_id']==m['id']and(d['file_path']or'').startswith('Minutes/')]
        docs.sort(key=lambda d:('signed'not in d['file_path'].lower(),d['id']))
        candidates=[]
        for d in docs:
            pdf=Path(args.repo)/m['archive_path']/d['file_path'];sha=hashlib.sha256(pdf.read_bytes()).hexdigest();cp=cache/(sha+'.json')
            if cp.exists():e=json.loads(cp.read_text())
            else:
                e=extract(pdf);e['native_text_sha256']=hashlib.sha256(get_pdf_text(str(pdf)).encode()).hexdigest();cp.write_text(json.dumps(e,indent=2))
            first=e['first_page_text'];date=datetime.fromisoformat(m['meeting_date']);date_pattern=rf'{date.strftime("%B")}\s+0?{date.day}(?:st|nd|rd|th)?[^\d]{{0,8}}{date.year}'
            date_ok=bool(re.search(date_pattern,first[:750],re.I))
            minutes_ok=bool(re.search(r'\bMinutes\b',first[:350],re.I))
            candidates.append({'source_url':d['source_url'],'source_sha256':sha,'file_path':str(pdf),'document_id':d['id'],'date_verified':date_ok,'minutes_heading_verified':minutes_ok,**e})
        # Prefer signed minutes; never silently choose a different meeting/date.
        verified=[s for s in candidates if s['date_verified']and s['minutes_heading_verified']and s['sections']]
        source=verified[0]if verified else (candidates[0]if candidates else None)
        records=[];holds=[]
        for pid,(name,initial,surname)in COUNCIL.items():
            matches=[]
            if source and source['date_verified']and source['minutes_heading_verified']:
                for sec in source['sections']:
                    for hit in re.finditer(r'\b'+surname+r'\b',sec['quote'],re.I):
                        # Municipality/term roster reviewed separately; initials
                        # must agree when supplied. Unique Mayor Young is valid.
                        prefix=sec['quote'][max(0,hit.start()-18):hit.start()]
                        token=re.search(r'\b([A-Z])\.?\s*$',prefix)
                        if token and token[1].upper()!=initial:continue
                        if pid==143 and not token and not re.search(r'Mayor\s*$',prefix,re.I):continue
                        if pid!=143 and not token:continue
                        matches.append(sec)
            states={('present'if s['heading']=='PRESENT'else'absent')for s in matches}
            if len(states)!=1:holds.append({'person_id':pid,'reason':'no_explicit_roster_entry'if not states else'conflicting_roster_sections'});continue
            state=states.pop();sec=matches[0]
            records.append({'person_id':pid,'state':state,'source_heading':sec['heading'],'source_quote':sec['heading']+'\n'+sec['quote'],'source_page':1,'bounds':sec['bounds']})
        result.append({'meeting_id':m['id'],'local_date':m['meeting_date'],'type':m['type'],'archive_path':m['archive_path'],'source':source,'records':records,'holds':holds,'alternative_sources':[s['source_url']for s in candidates if s is not source]})
    (out/'roster-plan.json').write_text(json.dumps({'schema':'historical-roster-plan/v1','finite_meetings':89,'council_mapping':COUNCIL,'meetings':result},indent=2))
    from collections import Counter
    print(Counter(r['state']for m in result for r in m['records']));print('records',sum(len(m['records'])for m in result),'holds',sum(len(m['holds'])for m in result))
    for m in result:
        if m['holds']:print(m['meeting_id'],m['local_date'],'records',[(r['person_id'],r['state'])for r in m['records']],'holds',m['holds'])
if __name__=='__main__':main()
