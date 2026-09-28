from datetime import date

from pipeline.ops import source_document_status
from pipeline.scrapers.base import ScrapedDocument, ScrapedMeeting


def _meeting(*documents: ScrapedDocument) -> ScrapedMeeting:
    return ScrapedMeeting(
        date=date(2026, 5, 4),
        title="Council Meeting",
        documents=list(documents),
    )


def test_cancellation_notice_does_not_enter_ingestion_queue():
    meeting = _meeting(
        ScrapedDocument(
            title="Council Meeting Cancellation Notice",
            url="https://example.com/notice.pdf",
            category="Other Documents",
        )
    )

    assert source_document_status(meeting, "documents_downloaded") == "cancelled"


def test_postponement_notice_does_not_enter_ingestion_queue():
    meeting = _meeting(
        ScrapedDocument(
            title="Meeting Postponement Notice",
            url="https://example.com/notice.pdf",
            category="Other Documents",
        )
    )

    assert source_document_status(meeting, "discovered") == "postponed"


def test_real_agenda_takes_precedence_over_old_notice():
    meeting = _meeting(
        ScrapedDocument(
            title="Meeting Cancellation Notice",
            url="https://example.com/notice.pdf",
            category="Other Documents",
        ),
        ScrapedDocument(
            title="Agenda",
            url="https://example.com/agenda.pdf",
            category="Agenda",
        ),
    )

    assert source_document_status(meeting, "documents_downloaded") == "documents_downloaded"
