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
