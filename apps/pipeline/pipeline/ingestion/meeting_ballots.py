"""Meeting-scoped documentary ballot context for ordinary ingestion."""
from datetime import datetime, timezone
import json
import re
from pathlib import Path

from .official_ballots import load_official_minutes, inspect_motion, complete_ballot_proof
from .vote_policy import refresh_vote_policy
from .committee_ballots import inspect_committee_motion, refresh_committee_policy
from .canonical_motions import catalog_cac_candidate
from .vote_evidence import normalize_text


def prepare_ballot_context(supabase, *, municipality_id, meeting, root):
    """Load once per meeting; uncertainty disables inference, not source choices."""
    try:
        municipality = supabase.table('municipalities').select('slug').eq('id', municipality_id).maybe_single().execute().data
        if not isinstance(municipality, dict) or municipality.get('slug') != 'langford':
            return {'status': 'municipality_recording_rule_not_validated'}
        catalog_cac = catalog_cac_candidate(meeting)
        if meeting['classification'] not in ('Council', 'Committee of the Whole') and not catalog_cac:
            return {'status': 'committee_membership_rules_need_validation'}
        rule = json.loads((Path(__file__).parent/'policies'/'langford-voting.json').read_text())
        cache = Path(root)/'reports'/'vote-policy'
        checked = datetime.now(timezone.utc).date().isoformat()
        policy = refresh_vote_policy(rule, cache/'langford.json', checked)
        orgs = supabase.table('organizations').select('id').eq('municipality_id', municipality_id).eq('classification', 'Council').execute().data
        org_ids = [row['id'] for row in orgs]
        if not org_ids:
            return {'status': 'council_membership_inventory_unavailable'}
        rows = supabase.table('memberships').select('person_id,role,start_date,end_date,person:people(name)').in_('organization_id', org_ids).execute().data
        memberships = [{'person_id': row['person_id'], 'name': row['person']['name'], 'role': row.get('role'), 'start_date': row['start_date'], 'end_date': row['end_date'], 'classification': 'Council'} for row in rows if row.get('person')]
        people = []
        while True:
            batch = supabase.table('people').select('id,name').order('id').range(len(people), len(people)+999).execute().data
            people.extend(batch)
            if len(batch) < 1000:
                break
        meeting = {**meeting, 'municipality_slug': 'langford'}
        source = load_official_minutes(meeting, root=root, people=people, cache_dir=cache/'sources')
        if catalog_cac and re.search(r'community\s+advisory\s+committee', source.get('source_header', ''), re.I):
            policy = refresh_committee_policy(policy, checked)
        return {'status': 'available', 'meeting': meeting, 'source': source, 'people': people, 'memberships': memberships, 'policy': policy}
    except Exception as error:
        return {'status': 'ballot_context_unavailable', 'error_type': type(error).__name__}


def evaluate_ballot(motion, context, existing_choices=()):
    """All-or-nothing inference; existing choices are never silently contradicted."""
    if context['status'] != 'available':
        return {'status': context['status']}
    catalog_cac = catalog_cac_candidate(context['meeting']) and bool(re.search(r'community\s+advisory\s+committee', context['source'].get('source_header', ''), re.I))
    inspector = inspect_committee_motion if catalog_cac else inspect_motion
    candidate = inspector(motion, context['source'], meeting=context['meeting'], people=context['people'], memberships=context['memberships'], policy=context['policy'])
    if candidate['status'] != 'reconstructable_candidate':
        return candidate
    choices = {row['person_id']: row['vote'] for row in candidate['votes']}
    if any(row['person_id'] not in choices or row['vote'] != choices[row['person_id']] for row in existing_choices):
        return {'status': 'existing_vote_conflicts_with_reconstructed_ballot'}
    proof = complete_ballot_proof(candidate, context['policy'])
    for key in ('member_observations', 'excluded_nonvoting_attendees', 'committee_chair_person_ids', 'committee_quorum_minimum_appointees', 'committee_policy_validation'):
        if key in candidate:
            proof[key] = candidate[key]
    return {**candidate, 'proof': proof}


def index_prior_ballots(motions, votes):
    """Only a unique unchanged motion body can carry choices across recreation."""
    index = {}
    for motion in motions:
        key = normalize_text(motion.get('text_content'))
        entry = {'motion': motion, 'votes': [vote for vote in votes if vote['motion_id'] == motion['id']]}
        if key in index:
            index[key] = None  # Ambiguous repeated resolutions cannot inherit a ballot.
        elif key:
            index[key] = entry
    return index


def merge_ballot_evidence(motion, named_choices, context, prior=None):
    """Return choices and metadata; current uncertainty never erases prior choices."""
    prior = prior or {}
    old_choices = prior.get('votes', [])
    prior_meta = prior.get('motion', {}).get('meta') or {}
    prior_proof = prior_meta.get('prior_ballot_proof') or prior_meta.get('ballot_reconstruction')
    current = {row.get('person_id'): row for row in named_choices if row.get('person_id') is not None}
    by_name = {row['person_name']: row for row in named_choices}
    # Canonical IDs supplied by the validated source context prevent a name alias
    # from evading conflict checks. The source-only fallback also receives IDs
    # from the ingester before reaching this boundary.
    for person in context.get('people', []):
        if person['name'] in by_name:
            current[person['id']] = {**by_name[person['name']], 'person_id': person['id']}
    explicit_conflict = any(row['person_id'] in current and current[row['person_id']]['vote'] != row['vote'] for row in old_choices)
    candidate = evaluate_ballot(motion, context, old_choices)
    metadata = dict(motion.get('meta') or {})
    if not explicit_conflict and candidate['status'] == 'reconstructable_candidate':
        metadata.update({'individual_vote_coverage': 'reconstructed_complete', 'ballot_reconstruction': candidate['proof']})
        metadata['vote_record'] = {**metadata.get('vote_record', {}), 'coverage': 'reconstructed_complete'}
        choices = candidate['votes']
    else:
        hold = {'status': 'existing_vote_conflicts_with_current_source' if explicit_conflict else candidate['status']}
        if candidate.get('events'):
            hold['events'] = candidate['events']
        if candidate.get('unknown'):
            hold['unknown'] = candidate['unknown']
        metadata['ballot_reconstruction'] = hold
        # Alignment consumers admit only complete ballots. A preserved choice
        # is still partial evidence when current validation is held.
        metadata['individual_vote_coverage'] = 'named_only'
        if old_choices:
            preserved = {row['person_id']: {**row, 'evidence': 'preserved_existing_choice'} for row in old_choices}
            if not explicit_conflict and candidate['status'] != 'existing_vote_conflicts_with_reconstructed_ballot':
                preserved.update({pid: row for pid, row in current.items() if pid not in preserved})
            choices = list(preserved.values())
            hold['prior_choices_preserved'] = True
        else:
            choices = named_choices
        metadata['vote_record'] = {**metadata.get('vote_record', {}), 'coverage': 'partial' if choices else 'not_recorded'}
        previous_labels = (prior_proof or {}).get('choice_provenance', {})
        hold['choice_provenance'] = {
            f"person_{row['person_id']}": previous_labels.get(f"person_{row['person_id']}", row.get('evidence', 'explicit_named'))
            for row in choices if row.get('person_id') is not None
        }
    if prior_proof:
        metadata['prior_ballot_proof'] = prior_proof
    if prior_meta.get('vote_record'):
        metadata['prior_vote_record'] = prior_meta['vote_record']
    return choices, metadata
