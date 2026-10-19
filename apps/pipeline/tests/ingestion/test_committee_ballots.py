"""CAC owner contract: citizen votes, staff boundaries, attendance and quorum.

These cases exercise the public source-to-candidate boundary. Council ballot
coverage cannot detect wrongly treating citizen committee members as outsiders.
No production seams or private-predicate assertions are added.
"""
import pytest
from datetime import date as calendar_date
from pipeline.ingestion.committee_ballots import inspect_committee_motion
from pipeline.ingestion.official_ballots import load_official_minutes

PEOPLE=[{'id':i,'name':n}for i,n in enumerate(['Keith Yacucha','Mark Morley','Colby Harder','Chris Foxall','Frazer Johnson','Nicolas Lehman','Robin Plomp','Jacqui Whiteway','Moira McDonald','Mary Wagner','Melisa Miles'],1)]
MEMBERS=[{'person_id':i,'name':n,'classification':'Council','role':'Councillor','start_date':'2022-11-07','end_date':'2026-11-01'}for i,n in [(1,'Keith Yacucha'),(2,'Mark Morley'),(3,'Colby Harder'),(10,'Mary Wagner')]]
POLICY={'municipality_slug':'langford','policy_status':'verified_unchanged','enabled_from':'2021-10-18','enabled_through':'2026-10-18'}
BODY='THAT the Community Advisory Committee recommend that Council review the policy.'

def context(tmp_path,*,present=None,absent='',event='',opposition='',date='2025-08-26'):
    present=present or ['Councillor K. Yacucha - Chair','Councillor M. Morley - Vice-Chair','Councillor C. Harder','C. Foxall','F. Johnson','N. Lehman','R. Plomp','J. Whiteway']
    path=tmp_path/'archive/committee/Minutes/Minutes.html';path.parent.mkdir(parents=True)
    roster=''.join(f'<li>{name}</li>'for name in present)
    printed_date=calendar_date.fromisoformat(date).strftime('%B %d, %Y')
    path.write_text(f'''<title>Community Advisory Committee Minutes - {printed_date}</title><div class="AgendaHeaderAttendanceTable"><div><span class="Label">PRESENT:</span><div class="Value">{roster}</div></div><div><span class="Label">ABSENT:</span><div class="Value">{absent}</div></div><div><span class="Label">ATTENDING:</span><div class="Value"><li>M. Miles, Manager of Legislative Services</li></div></div></div><div class="AgendaItems"><div class="AgendaItemMinutes">{event}</div><div class="AgendaItemMotion"><div class="MovedBy"><span class="Value">FOXALL</span></div><div class="SecondedBy"><span class="Value">JOHNSON</span></div><div class="MotionText">{BODY}</div><div class="MotionResult">CARRIED</div><div class="PostMotionText">{opposition}</div></div></div>''')
    PathLike=type(path);PathLike(str(path)+'.url').write_text('https://pub-langford.escribemeetings.com/Meeting.aspx?Id=fixture')
    meeting={'id':7,'title':'Advisory Committee','archive_path':'archive/committee','meeting_date':date,'classification':'Committee','municipality_slug':'langford'}
    source=load_official_minutes(meeting,root=tmp_path,people=PEOPLE,cache_dir=tmp_path/'cache')
    return {'id':9,'meeting_id':7,'result':'CARRIED','text_content':BODY},source,meeting

def inspect(tmp_path,**kwargs):
    motion,source,meeting=context(tmp_path,**kwargs)
    return inspect_committee_motion(motion,source,meeting=meeting,people=PEOPLE,memberships=MEMBERS,policy=POLICY)

def test_official_member_roster_admits_citizens_excludes_staff_and_visiting_councillors(tmp_path):
    r=inspect(tmp_path,present=['Councillor K. Yacucha - Chair','Councillor M. Morley - Vice-Chair','Councillor C. Harder','C. Foxall','F. Johnson','N. Lehman','R. Plomp','J. Whiteway','Councillor M. Wagner'],opposition='Committee members F. Johnson and C. Foxall opposed.')
    assert r['status']=='reconstructable_candidate'
    assert {v['person_id']:v['vote']for v in r['votes']}=={1:'Yes',2:'Yes',3:'Yes',4:'No',5:'No',6:'Yes',7:'Yes',8:'Yes'}
    assert r['membership_evidence']=='official_dated_committee_member_observation'
    assert r['outcome_role']=='committee_guidance_or_recommendation'

@pytest.mark.parametrize('case,expected',[
    ('absent_contradiction','committee_roster_present_absent_conflict'),
    ('unknown_member','committee_full_identity_not_proven'),
    ('no_chair','committee_quorum_or_chair_not_proven'),
    ('chair_leaves','committee_quorum_or_chair_not_proven'),
    ('before_whiteway','committee_appointment_date_conflict'),
])
def test_incomplete_eligibility_or_per_vote_quorum_never_infers_choices(tmp_path,case,expected):
    kwargs={}
    if case=='absent_contradiction':kwargs['absent']='J. Whiteway'
    if case=='unknown_member':kwargs['present']=['Councillor K. Yacucha - Chair','Councillor M. Morley - Vice-Chair','Councillor C. Harder','C. Foxall','F. Johnson','S. Klaver']
    if case=='no_chair':kwargs['present']=['Councillor C. Harder','C. Foxall','F. Johnson','N. Lehman','R. Plomp','J. Whiteway']
    if case=='chair_leaves':kwargs['event']='Councillor Yacucha left the meeting at 7:10 pm. Councillor Morley left the meeting at 7:11 pm.'
    if case=='before_whiteway':kwargs['date']='2023-08-26'
    r=inspect(tmp_path,**kwargs)
    assert r['status']==expected
    assert not r.get('votes')


def test_member_initially_absent_arrives_before_vote_and_is_not_silently_omitted(tmp_path):
    r=inspect(tmp_path,absent='M. McDonald',event='Committee Member M. McDonald joined the meeting at 7:05 pm.')
    assert r['status']=='reconstructable_candidate'
    assert {v['person_id']for v in r['votes']}==set(range(1,10))
    observation=next(o for o in r['member_observations']if o['person_id']==9)
    assert observation['observed_attendance']=='absent'
    assert 'M. McDonald' in observation['source_quote']


def test_new_arrival_without_contemporaneous_member_roster_observation_is_held(tmp_path):
    r=inspect(tmp_path,event='Committee Member M. McDonald joined the meeting at 7:05 pm.')
    assert r['status']=='committee_member_observation_unavailable'
    assert not r.get('votes')


@pytest.mark.parametrize('arrives,expected',[(False,'reconstructable_candidate'),('arrived at the meeting','unparsed_presence_event'),('joined remotely','unparsed_presence_event')])
def test_unknown_absent_member_is_held_only_when_physical_arrival_affects_ballot(tmp_path,arrives,expected):
    r=inspect(tmp_path,absent='S. Klaver',event=('Staff presented the report and answered questions. '*6+f'Committee Member S. Klaver {arrives} at 7:05 pm.') if arrives else '')
    assert r['status']==expected
    if arrives:assert not r.get('votes')


@pytest.mark.parametrize('change,expected',[
    ('unrelated_bio','verified_unchanged'),
    ('terms','committee_terms_changed_requires_machine_revalidation'),
    ('registry','committee_registry_changed_requires_machine_revalidation'),
    ('unavailable','committee_policy_verification_unavailable_hold'),
])
def test_automatic_refresh_advances_only_unchanged_primary_eligibility_evidence(tmp_path,change,expected):
    from pathlib import Path
    import requests
    from pipeline.ingestion.committee_ballots import refresh_committee_policy
    fixtures=Path(__file__).parents[1]/'fixtures'
    signed=(fixtures/'langford-cac-policy-2024.pdf').read_bytes()
    listing=(fixtures/'langford-cac-appointments-section.html').read_bytes()
    if change=='terms':signed+=b' changed official document'
    if change=='registry':listing=listing.replace(b'Chris Foxall',b'Alex Different')
    if change=='unrelated_bio':listing+=b'<section>Unrelated councillor biography changed.</section>'
    class PrimaryResponses:
        def __init__(self):self.payloads=iter([signed,listing])
        def get(self,url,timeout):
            if change=='unavailable':raise requests.ConnectionError('unavailable')
            response=requests.Response();response.status_code=200;response._content=next(self.payloads)
            return response
    updated=refresh_committee_policy(POLICY,'2026-10-20',session=PrimaryResponses())
    assert updated['committee_policy']['status']==expected
    if expected=='verified_unchanged':
        assert updated['committee_policy']['enabled_through']=='2026-10-20'
        assert updated['committee_policy']['validated_as_of']=='2026-10-20'
        motion,source,meeting=context(tmp_path,date='2026-10-20')
        candidate=inspect_committee_motion(motion,source,meeting=meeting,people=PEOPLE,memberships=MEMBERS,policy={**updated,'enabled_through':'2026-10-20'})
        assert candidate['status']=='reconstructable_candidate'
        assert candidate['committee_policy_validation']['validated_as_of']=='2026-10-20'
    else:
        motion,source,meeting=context(tmp_path)
        candidate=inspect_committee_motion(motion,source,meeting=meeting,people=PEOPLE,memberships=MEMBERS,policy=updated)
        assert candidate['status']==expected
        assert not candidate.get('votes')
