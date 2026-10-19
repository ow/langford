"""Small official HTML fixture shared by ballot ownership tests."""
from pathlib import Path
from pipeline.ingestion.official_ballots import load_official_minutes

PEOPLE=[{'id':1,'name':'Scott Goodmanson'},{'id':21,'name':'Colby Harder'},{'id':23,'name':'Kimberley Guiry'},{'id':24,'name':'Mary Wagner'},{'id':25,'name':'Keith Yacucha'},{'id':26,'name':'Mark Morley'}]
MEMBERS=[{'person_id':p['id'],'name':p['name'],'start_date':'2022-11-07','end_date':None,'classification':'Council'} for p in PEOPLE]
TEXT='THAT Council adopt Tree Protection Bylaw No. 2269, 2026 as presented.'
POLICY={'municipality_slug':'langford','policy_status':'verified_unchanged','enabled_from':'2021-10-18','enabled_through':'2026-10-18','validated_as_of':'2026-10-18','rule_id':'langford_1971_dissent_recording','bylaw_url':'https://langford.ca/procedure.pdf','bylaw_sha256':'policy-sha'}


def official_context(tmp_path, *, result='CARRIED', opposition='', event='', unknown='', meeting_id=77, source_date='January 8, 2026', source_title='Council Meeting'):
    folder=tmp_path/'archive'/'meeting'/'Minutes';folder.mkdir(parents=True)
    roster=''.join('<li>'+p['name']+'</li>' for p in PEOPLE)+unknown
    html=f'''<title>{source_title} - {source_date}</title>
    <div class="AgendaHeaderAttendanceTable"><div><div class="Label">PRESENT:</div><div class="Value"><ul>{roster}</ul></div></div>
    <div><div class="Label">ATTENDING:</div><div class="Value">Staff</div></div></div>
    <div class="AgendaItems"><div class="AgendaItemTitleRow"><span class="AgendaItemCounter">1.</span><span class="AgendaItemTitle">CALL TO ORDER</span></div>
    <div class="AgendaItemMinutes">{event}</div>
    <div class="AgendaItemMotion"><div class="MovedBy"><div class="Value">Colby Harder</div></div><div class="SecondedBy"><div class="Value">Kimberley Guiry</div></div>
    <div class="MotionText">{TEXT}</div><div class="MotionResult">Motion {result}.</div><div class="PostMotionText">{opposition}</div></div></div>'''
    path=folder/'Minutes.html';path.write_text(html)
    Path(str(path)+'.url').write_text('https://pub-langford.escribemeetings.com/Meeting.aspx?Id=meeting&Agenda=PostMinutes')
    from datetime import datetime
    meeting={'id':meeting_id,'classification':'Council','municipality_slug':'langford','meeting_date':datetime.strptime(source_date,'%B %d, %Y').date().isoformat(),'archive_path':'archive/meeting'}
    source=load_official_minutes(meeting,root=tmp_path,people=PEOPLE,cache_dir=tmp_path/'cache')
    return {'status':'available','meeting':meeting,'source':source,'people':PEOPLE,'memberships':MEMBERS,'policy':POLICY}
