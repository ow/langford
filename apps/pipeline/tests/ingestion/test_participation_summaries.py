"""Published public-comment labels must not repeat uncertain ASR identities."""
import pytest

from pipeline.ingestion.participation_validation import canonicalize_participation


@pytest.mark.parametrize('address,street', [
    ('932 Rells Crescent', 'Rowils Crescent'),
    ('107-932 Rells Crescent', 'Rowils Crescent'),
    ('932 1/2 Rells Crescent', 'Rowils Crescent'),
    ('Unit 7, 932½ Rells Crescent', 'Rowils Crescent'),
    ('932 Rells Crescent #12', 'Rowils Crescent'),
    ('932 Rells Crescent, unit seven', 'Rowils Crescent'),
    ('nine thirty-two Rells Crescent', 'Rowils Crescent'),
    ('1234 Skyview Ridge', 'Skyview Ridge'),
    ('1234 Bearspaw Plateau', 'Bearspaw Plateau'),
    ('932 Rells Crescent, unit forty-two', 'Rowils Crescent'),
    ('nine two three Klahanie', 'Klahanie'),
])
def test_public_summary_checks_names_streets_and_all_bullet_fields(address, street):
    people = [
        {'id': 41, 'name': 'Chris Foxall'}, {'id': 89, 'name': 'N. Joel'},
        {'id': 42, 'name': 'Alex Smith'}, {'id': 43, 'name': 'Alice Smith'},
    ]
    generated = {'overview': f'Comments on {address}.', 'speakers': [
        {'who': f'Chris Foxhall ({address})', 'position': 'concerned',
         'point': f'Warns about access to {address} and supports parking.', 'topic': f'{address} variance'},
        {'who': 'Normal Joel', 'position': 'opposes', 'point': 'Opposes reduced parking, citing 2025 funding for Madrona Ridge and 20 parking spaces.', 'topic': 'Parking'},
        {'who': 'A. Smith (44 Rowils Crescent)', 'position': 'asks',
         'point': 'She asks for 20 parking spaces.', 'topic': 'Parking'},
        {'who': 'Invented Person (17 Imaginary Road)', 'position': 'asks',
         'point': 'Asks for safer roads.', 'topic': '17 Imaginary Road safety'},
        {'who': 'Alex Smith', 'position': 'asks', 'point': 'Requests safer crossings.', 'topic': 'Road safety'},
        {'who': 'Invented Person', 'position': 'asks', 'point': 'Asks the mayor to reconsider his decision.', 'topic': 'Road safety'},
        {'who': 'Invented Person', 'position': 'other', 'point': 'Says the applicant withdrew her proposal.', 'topic': 'Road safety'},
    ]}
    result = canonicalize_participation(generated, people=people,
        statement_names=[{'id': 1, 'person_id': 41, 'speaker_name': 'Chris Foxall'}],
        street_evidence={'streets': ['Rowils Crescent', 'Skyview Ridge', 'Bearspaw Plateau', 'Klahanie Road'],
                         'street_aliases': {'Rells Crescent': 'Rowils Crescent'}},
        source_text="My name is Chris Foxhall. My name is Normal Joel. I am A. Smith. My name is Invented Person.")
    # Suffixless spoken civic numbers are private, but do not establish the
    # street suffix required for a verified location label.
    first_label = 'Chris Foxall' if street == 'Klahanie' else f'Chris Foxall ({street})'
    assert [s['who'] for s in result['speakers']] == [
        first_label, 'N. Joel', 'A resident (Rowils Crescent)', 'A resident', 'A resident', 'A resident', 'A resident',
    ]
    assert result['overview'] == f'Comments on {street}.'
    assert result['speakers'][0]['topic'] == f'{street} variance'
    assert result['speakers'][0]['point'] == f'Warns about access to {street} and supports parking.'
    assert result['speakers'][1]['point'] == 'Opposes reduced parking, citing 2025 funding for Madrona Ridge and 20 parking spaces.'
    assert result['speakers'][2]['point'] == 'Asks for 20 parking spaces.'
    assert result['speakers'][3]['topic'] == 'Imaginary Road safety'
    assert result['speakers'][5]['point'] == 'Asks the mayor to reconsider their decision.'
    assert result['speakers'][6]['point'] == 'Says the applicant withdrew their proposal.'
    assert all('person_id' not in s for s in result['speakers'])
