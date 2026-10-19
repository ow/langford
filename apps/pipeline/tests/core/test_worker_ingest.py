"""Queue completion follows persisted content, not merely an old public meeting ID."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

import pytest
import worker


@pytest.mark.parametrize('summary,has_minutes,download_minutes,expected_status,source_only',[
    pytest.param(None,False,False,'failed',None,id='transcript-only-row-is-not-complete'),
    pytest.param('Existing summary',False,True,'failed',None,id='new-minutes-have-not-been-ingested'),
    pytest.param('Planned agenda overview',False,False,'succeeded',None,id='planned-agenda-only-cached-skip'),
    pytest.param('Existing summary',True,True,'succeeded',True,id='fact-only-repair-has-no-paid-follow-ons'),
    pytest.param('New summary',True,True,'succeeded',False,id='enriched-meeting-retains-profile-refresh'),
])
def test_ingest_completion_requires_advertised_sources(tmp_path,summary,has_minutes,download_minutes,expected_status,source_only):
    job={'id':88,'job_type':'ingest_meeting','municipality_id':1,'args':{'source_meeting_id':7,'skip_diarization':True}}
    municipality=SimpleNamespace(id=1,slug='langford',name='Langford')
    source={'id':7,'meeting_date':'2026-12-01','video_url':None}
    meeting=MagicMock()
    for method in ['select','eq']:
        getattr(meeting,method).return_value=meeting
    meeting.execute.return_value.data=[{'id':42,'video_url':None,'summary':summary,'has_agenda':True,'has_minutes':has_minutes}]
    sources=MagicMock()
    client=MagicMock();client.table.side_effect=lambda name:meeting if name=='meetings' else sources
    archiver=MagicMock()
    archiver._ingest_meetings.return_value={'source_only_refresh':source_only} if source_only is not None else None
    archiver.extract_documents_for_meeting.return_value={'skipped':'html_only_agenda','incomplete_attachment_extraction':True}
    downloads=[str(tmp_path/'Agenda'/'Agenda.html')]
    if download_minutes:downloads.append(str(tmp_path/'Minutes'/'Minutes.html'))
    with patch.object(worker,'get_supabase',return_value=client),patch.object(worker,'claim_job',return_value=job),patch.object(worker,'start_heartbeat',return_value=(MagicMock(),MagicMock())),patch.object(worker,'capture_job_output',return_value=nullcontext()),patch.object(worker,'record_job_event'),patch.object(worker,'finish_job') as finish,patch.object(worker,'load_municipality_by_id',return_value=municipality),patch.object(worker,'Archiver',return_value=archiver),patch.object(worker,'_resolve_archive_path',return_value=(str(tmp_path),42,7)),patch.object(worker,'_get_source_meeting',return_value=source),patch.object(worker,'_ensure_source_documents',return_value=downloads),patch.object(worker,'_ensure_source_audio'):
        assert worker.work_once('test-worker',5) is True
    assert finish.call_args.args[2]==expected_status
    if expected_status=='failed':
        assert not sources.update.called
        assert not archiver._embed_new_content.called
    else:
        assert sources.update.call_args.args[0]=={'status':'ingested','ingested_meeting_id':42}
        assert finish.call_args.kwargs['result']['ingestion_skipped'] is (source_only is None)
        if source_only:
            assert not archiver.extract_documents_for_meeting.called
            assert not archiver.refresh_profiles_after_meetings.called
            assert not archiver._embed_new_content.called
            assert finish.call_args.kwargs['result']['source_only_refresh'] is True
        else:
            assert archiver.refresh_profiles_after_meetings.called is (source_only is False)
            assert archiver.extract_documents_for_meeting.called
            assert archiver._embed_new_content.called
    # An ordinary ingest request must not implicitly force old acoustic rows.
    assert archiver._ingest_meetings.call_args.kwargs['force_update'] is False
