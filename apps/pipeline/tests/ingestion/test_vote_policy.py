import hashlib
from types import SimpleNamespace
from unittest.mock import Mock
from pipeline.ingestion.vote_policy import refresh_vote_policy


def response(content,status=200):
    return SimpleNamespace(content=content,text=content.decode(),status_code=status,headers={'ETag':'known'},raise_for_status=lambda:None)


def test_unchanged_official_rule_extends_automatically_but_changed_policy_holds(tmp_path):
    content=b'known official procedure bylaw'
    rule={'official_directory':'https://city.example/bylaws/','bylaw_url':'https://city.example/procedure.pdf','bylaw_sha256':hashlib.sha256(content).hexdigest(),'enabled_through':'2026-10-18'}
    session=Mock()
    index=response(b'<a href="/procedure.pdf">Council Procedure Bylaw</a>')
    session.get.side_effect=[index,response(content)]
    refreshed=refresh_vote_policy(rule,tmp_path/'cache.json','2026-11-01',session)
    assert refreshed['enabled_through']=='2026-11-01'
    assert refreshed['policy_status']=='verified_unchanged'
    # Even though the familiar URL is unchanged, new bytes cannot inherit approval.
    session.get.side_effect=[index,response(b'amended procedure')]
    changed=refresh_vote_policy(rule,tmp_path/'cache.json','2026-11-02',session)
    assert changed['policy_status']=='changed_document_requires_machine_re_evaluation'
    assert changed['enabled_through']=='2026-10-18'
    session.get.side_effect=[response(b'<a href="/new.pdf">Council Procedure Bylaw</a>')]
    replaced=refresh_vote_policy(rule,tmp_path/'cache.json','2026-11-02',session)
    assert replaced['policy_status']=='changed_official_link_requires_machine_re_evaluation'
