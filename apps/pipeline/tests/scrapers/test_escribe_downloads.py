"""Archive files must never admit an error page or an interrupted PDF as reusable."""
from datetime import date
from unittest.mock import MagicMock

import pytest
import requests
import fitz

from pipeline.scrapers.base import MunicipalityConfig, ScrapedDocument, ScrapedMeeting
from pipeline.scrapers.escribe import EscribeScraper


@pytest.mark.parametrize('body', [b'<html>Service unavailable</html>', b'', b'%PDF-1.7 incomplete'])
def test_non_pdf_response_is_not_archived(tmp_path, body):
    scraper = EscribeScraper(MunicipalityConfig(1, 'test', 'Test', 'Test', {'base_url': 'https://example.org'}))
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = iter([body])
    scraper.session.get = MagicMock(return_value=response)
    meeting = ScrapedMeeting(date(2026, 1, 1), 'Council', documents=[ScrapedDocument('Agenda','https://example.org/file', 'Agenda', 'pdf')])
    assert scraper.download_documents(meeting, str(tmp_path)) == []
    assert not list(tmp_path.rglob('*.pdf'))
    assert not list(tmp_path.rglob('*.part'))


def test_interrupted_pdf_does_not_poison_retry(tmp_path):
    scraper = EscribeScraper(MunicipalityConfig(1, 'test', 'Test', 'Test', {'base_url': 'https://example.org'}))
    response = MagicMock()
    response.__enter__.return_value = response
    def broken_download(*args, **kwargs):
        yield b'%PDF-1.7 partial'
        raise requests.ConnectionError('connection dropped')
    response.iter_content.side_effect = broken_download
    scraper.session.get = MagicMock(return_value=response)
    meeting = ScrapedMeeting(date(2026, 1, 1), 'Council', documents=[ScrapedDocument('Agenda','https://example.org/file', 'Agenda', 'pdf')])
    assert scraper.download_documents(meeting, str(tmp_path)) == []
    assert not list(tmp_path.rglob('*.pdf'))
    assert not list(tmp_path.rglob('*.part'))
    response.iter_content.side_effect = None
    with fitz.open() as document:
        document.new_page().insert_text((30,30),'Council agenda')
        complete_pdf = document.tobytes()
    response.iter_content.return_value = iter([complete_pdf])
    paths = scraper.download_documents(meeting, str(tmp_path))
    assert len(paths) == 1
    assert (tmp_path/'Agenda'/'Agenda.pdf').read_bytes() == complete_pdf


def test_official_html_minutes_recover_after_pdf_challenge(tmp_path):
    scraper = EscribeScraper(MunicipalityConfig(1, 'test', 'Test', 'Test', {'base_url': 'https://example.org'}))
    pdf_response = MagicMock()
    pdf_response.__enter__.return_value = pdf_response
    pdf_response.raise_for_status.side_effect = requests.HTTPError('403 browser verification')
    html_response = MagicMock()
    html_response.text = '<h1 id="AgendaHeaderTitle">Council Minutes</h1><h2 id="AgendaItem1">6. Adopted Bylaw 2275</h2>'
    scraper.session.get = MagicMock(side_effect=[pdf_response, html_response])
    meeting = ScrapedMeeting(
        date(2026, 1, 1), 'Council',
        documents=[ScrapedDocument('Minutes','https://example.org/file', 'Minutes', 'pdf')],
        meta={'escribe_meeting': {'MeetingLinks': [{'Type':'PostMinutes','Format':'HTML','Url':'/Meeting.aspx?Agenda=PostMinutes'}]}},
    )
    paths = scraper.download_documents(meeting, str(tmp_path))
    assert len(paths) == 1
    assert (tmp_path/'Minutes'/'Minutes.html').read_text() == html_response.text
    assert (tmp_path/'Minutes'/'Minutes.html.url').read_text() == 'https://example.org/Meeting.aspx?Agenda=PostMinutes'
    assert not list(tmp_path.rglob('*.pdf'))


def test_html_challenge_page_is_not_mistaken_for_minutes(tmp_path):
    scraper = EscribeScraper(MunicipalityConfig(1, 'test', 'Test', 'Test', {'base_url': 'https://example.org'}))
    response = MagicMock()
    response.text = '<html><title>Verifying your browser</title>Please wait</html>'
    scraper.session.get = MagicMock(return_value=response)
    meeting = ScrapedMeeting(date(2026, 1, 1), 'Council', meta={'escribe_meeting': {'MeetingLinks': [{'Type':'PostMinutes','Format':'HTML','Url':'/minutes'}]}})
    assert scraper.download_documents(meeting, str(tmp_path)) == []
    assert not list(tmp_path.rglob('*.html'))


@pytest.mark.parametrize('old_content',['<html>Old challenge response</html>','%PDF-1.7 incomplete'])
def test_corrupt_cached_pdf_is_quarantined_before_html_recovery(tmp_path, old_content):
    scraper = EscribeScraper(MunicipalityConfig(1, 'test', 'Test', 'Test', {'base_url': 'https://example.org'}))
    folder=tmp_path/'Agenda';folder.mkdir()
    (folder/'Agenda.pdf').write_text(old_content)
    official='<h1 id="AgendaHeaderTitle">Council Agenda</h1><h2 id="AgendaItem1">1. Adoption</h2>'
    (folder/'Agenda.html').write_text(official)
    response=MagicMock();response.__enter__.return_value=response
    response.raise_for_status.side_effect=requests.HTTPError('403 browser verification')
    scraper.session.get=MagicMock(return_value=response)
    meeting=ScrapedMeeting(date(2026,1,1),'Council',documents=[ScrapedDocument('Agenda','https://example.org/file','Agenda','pdf')],meta={'escribe_meeting':{'MeetingLinks':[{'Type':'Agenda','Format':'HTML','Url':'/Meeting.aspx?Agenda=Agenda'}]}})
    paths=scraper.download_documents(meeting,str(tmp_path))
    assert paths==[str(folder/'Agenda.html')]
    assert not list(folder.glob('*.pdf'))
    assert len(list(folder.glob('*.pdf.invalid-*')))==1
    assert list(folder.glob('*.pdf.invalid-*'))[0].read_text()==old_content
