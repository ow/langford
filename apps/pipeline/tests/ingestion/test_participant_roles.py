"""Owner contracts for documentary, meeting-only government role observations."""
import pytest

PEOPLE=[{'id':125,'name':'E. Sinclair'},{'id':3,'name':'B. Hutchins'},{'id':400,'name':'Alex Smith'}]
TEXT='''City of Langford
Committee of the Whole Minutes
August 21, 2023, 1:00 p.m.
PRESENT: Mayor S. Goodmanson
ATTENDING: B. Hutchins, Director of Corporate Services

1. CALL TO ORDER

E. Sinclair, Senior Manager, Regional and Strategic Planning, Capital Regional District
(CRD) provided a presentation to Council.
'''

def evaluate(text=TEXT,people=PEOPLE,**changes):
    from pipeline.ingestion.participant_roles import participant_role_observations
    source={'text':text,'source_header':text[:text.index('PRESENT')],'source_format':'original_pdf_layout','source_file':'archive/langford/Committee of the Whole/2023/minutes.pdf','source_url':'https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=1','source_sha256':'a'*64,'local_date':'2023-08-21','stored_date':'2023-08-21'}
    source.update(changes)
    return participant_role_observations(source,meeting={'id':27,'meeting_date':'2023-08-21'},people=people)


def test_observed_staff_role_binds_only_this_meeting_and_original_statement():
    result=evaluate();regional=result['observations']['125']
    assert regional['classification']=='government_staff'
    assert regional['role']=='Senior Manager, Regional and Strategic Planning'
    assert regional['organization']=='Capital Regional District'
    assert regional['person_id']==125 and regional['meeting_id']==27
    assert regional['observed_date']=='2023-08-21' and regional['native_source_date']=='2023-08-21'
    assert regional['method']=='official_minutes_explicit_role_v1'
    assert regional['source_sha256']=='a'*64 and regional['source_quote']in TEXT
    assert 'provided a presentation to Council'in regional['source_quote']
    assert not {'start_date','end_date'}&regional.keys()


@pytest.mark.parametrize('unscoped_title',['Director of Acme Developments','Administrative Coordinator'])
def test_formal_attending_columns_reconstruct_municipal_role_without_private_director(unscoped_title):
    text=TEXT.replace('ATTENDING: B. Hutchins, Director of Corporate Services','ATTENDING:             B. Hutchins, Director of Corporate       Alex Smith, '+unscoped_title+'\n                       Services')
    result=evaluate(text)
    assert result['observations']['3']['role']=='Director of Corporate Services'
    assert result['observations']['3']['organization']=='City of Langford'
    assert '400'not in result['observations']


def test_initial_collision_is_held_but_explicit_full_name_is_not_guessed():
    people=PEOPLE+[{'id':126,'name':'Evelyn Sinclair'}]
    result=evaluate(people=people)
    assert '125'not in result['observations'] and result['holds']
    result=evaluate(TEXT.replace('E. Sinclair','Evelyn Sinclair'),people=people)
    assert result['observations']['126']['role']=='Senior Manager, Regional and Strategic Planning'


@pytest.mark.parametrize('sentence',[
    'Council discussed E. Sinclair, Senior Manager, Regional and Strategic Planning, Capital Regional District, for a future presentation.',
    'E. Sinclair, Senior Manager, Regional and Strategic Planning, Capital Regional District, will provide a presentation next month.',
    'A resident, E. Sinclair, explained that she works as Senior Manager for Capital Regional District.',
    'Councillor E. Sinclair, Senior Manager, Regional and Strategic Planning, Capital Regional District, provided a presentation to Council.',
    'E. Sinclair, Director of Acme Developments, provided a presentation to Council.',
    'E. Sinclair, Consultant, Capital Regional District, provided a presentation to Council.',
])
def test_mentions_private_jobs_and_nonstaff_political_capacity_do_not_become_staff(sentence):
    result=evaluate(TEXT[:TEXT.index('E. Sinclair')]+sentence)
    assert '125'not in result['observations']


@pytest.mark.parametrize('change',[
    {'local_date':'2023-08-25'},
    {'source_header':'City of Langford\nCouncil Minutes\nAugust 25, 2023\n'},
    {'source_format':'cached_transcript'},
    {'source_file':'/Users/private/archive/minutes.pdf'},
    {'source_file':'archive/../private/minutes.pdf'},
    {'source_sha256':'unverified'},
    {'source_url':'https://example.com/minutes.pdf'},
])
def test_unbound_original_provenance_and_own_header_date_hold_the_observations(change):
    result=evaluate(**change)
    assert result['observations']=={} and result['status']=='source_held'


def test_duplicate_canonical_full_names_never_assign_one_native_appearance_to_two_people():
    text = TEXT.replace('E. Sinclair', 'Evelyn Sinclair')
    people = PEOPLE + [{'id':126,'name':'Evelyn Sinclair'}, {'id':127,'name':'Evelyn Sinclair'}]
    result = evaluate(text, people=people)
    assert not {'125','126','127'} & result['observations'].keys()
    assert any(hold['reason'] == 'ambiguous_full_name' for hold in result['holds'])
    assert result['observations']['3']['person_id'] == 3


@pytest.mark.parametrize('corrupted_city',['Langforc','Langibrd','Langfbrd'])
def test_corrupted_municipal_heading_does_not_certify_staff_organization(corrupted_city):
    result = evaluate(TEXT.replace('City of Langford','City of '+corrupted_city))
    assert '3' not in result['observations']
    assert any(hold['reason']=='municipal_organization_heading_unknown' for hold in result['holds'])
    assert result['observations']['125']['organization']=='Capital Regional District'


COMMITTEE_PEOPLE=PEOPLE+[
    {'id':34,'name':'Keith Yacucha'},{'id':44,'name':'Frazer Johnson'},
    {'id':43,'name':'Robin Plomp'},{'id':41,'name':'Chris Foxall'},
]
COMMITTEE_TEXT=TEXT.replace('Committee of the Whole Minutes','Community Advisory Committee Minutes').replace(
    'PRESENT: Mayor S. Goodmanson',
    'PRESENT: Councillor K. Yacucha - Chair\n         F. Johnson\n         R. Plomp - Remote\nABSENT: C. Foxall',
)


@pytest.mark.parametrize('heading',['Community Advisory Committee','Sustainable Development Advisory Committee'])
def test_committee_service_is_observed_only_in_own_native_present_roster(heading):
    result=evaluate(COMMITTEE_TEXT.replace('Community Advisory Committee',heading),people=COMMITTEE_PEOPLE)
    for pid in ['34','44','43']:
        observed=result['observations'][pid]
        assert observed['classification']=='committee_member' and observed['role']=='Committee member'
        assert observed['organization']==heading and observed['meeting_id']==27
        assert observed['observed_date']=='2023-08-21'
        assert observed['evidence_kind']=='formal_committee_present_roster'
        assert 'PRESENT:' in observed['source_quote'] and 'ABSENT:' not in observed['source_quote']
    assert '41'not in result['observations']
    assert result['observations']['3']['classification']=='government_staff'
    assert result['observations']['125']['classification']=='government_staff'


@pytest.mark.parametrize('heading',['Council','Committee of the Whole','Advisory Committee'])
def test_committee_members_public_comments_or_generic_heading_do_not_establish_service(heading):
    text=COMMITTEE_TEXT.replace('Community Advisory Committee',heading)+'\nF. Johnson, Langford Resident, addressed Council about the Community Advisory Committee.\n'
    result=evaluate(text,people=COMMITTEE_PEOPLE)
    assert not any(o['classification']=='committee_member'for o in result['observations'].values())


def test_ambiguous_committee_identity_is_held_without_guessing_or_losing_documented_staff():
    people=COMMITTEE_PEOPLE+[{'id':4000,'name':'Frances Johnson'}]
    result=evaluate(COMMITTEE_TEXT,people=people)
    assert '44'not in result['observations'] and '4000'not in result['observations']
    assert result['observations']['43']['classification']=='committee_member'
    assert result['observations']['125']['classification']=='government_staff'
    assert any(h['reason']=='ambiguous_initial_surname'for h in result['holds'])


def test_guest_or_staff_cannot_become_member_from_unbounded_or_nonmember_roster_labels():
    result=evaluate(COMMITTEE_TEXT.replace('F. Johnson','Public Speaker F. Johnson'),people=COMMITTEE_PEOPLE)
    assert not any(o['classification']=='committee_member'for o in result['observations'].values())
    assert result['observations']['3']['classification']=='government_staff'

