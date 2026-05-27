"""eSCRIBE published meetings scraper."""

from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlparse

import requests

from pipeline import config, utils
from pipeline.scrapers.base import BaseScraper, MunicipalityConfig, ScrapedDocument, ScrapedMeeting


class EscribeScraper(BaseScraper):
    """Scraper for eSCRIBE public meeting portals.

    Expected source_config:
        {
            "type": "escribe",
            "base_url": "https://pub-langford.escribemeetings.com",
            "verify_ssl": false,
            "meeting_types": ["Council Meeting", "Special Council Meeting"],
            "video_source": {"type": "isilive", "client_id": "langford"}
        }
    """

    def __init__(self, municipality: MunicipalityConfig):
        super().__init__(municipality)
        self.base_url = self.source_config["base_url"].rstrip("/")
        self.meeting_types = self.source_config.get("meeting_types") or ["Council Meeting"]
        self.verify_ssl = self.source_config.get("verify_ssl", True)
        self.session = requests.Session()
        self.session.verify = self.verify_ssl
        self.session.headers.update(
            {
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
            }
        )

    def discover_meetings(self, since_date: date | None = None) -> list[ScrapedMeeting]:
        meetings: list[ScrapedMeeting] = []
        seen: set[str] = set()

        for meeting_type in self.meeting_types:
            for raw in self._fetch_meetings_for_type(meeting_type):
                meeting_id = raw.get("Id")
                if not meeting_id or meeting_id in seen:
                    continue
                seen.add(meeting_id)

                meeting_date = self._parse_meeting_date(raw)
                if not meeting_date:
                    continue
                if since_date and meeting_date < since_date:
                    continue

                links = raw.get("MeetingLinks") or []
                documents: list[ScrapedDocument] = []
                agenda_url = None
                minutes_url = None

                for link in links:
                    link_url = link.get("Url")
                    if not link_url or (link.get("Format") or "").lower() != ".pdf":
                        continue

                    category = self._document_category(link)
                    title = self._clean_title(link.get("Title") or category or "Document")
                    full_url = urljoin(f"{self.base_url}/", link_url)

                    if category == "Agenda" and not agenda_url and link.get("Type") == "Agenda":
                        agenda_url = full_url
                    if category == "Minutes" and not minutes_url:
                        minutes_url = full_url

                    documents.append(
                        ScrapedDocument(
                            title=title,
                            url=full_url,
                            category=category,
                            file_format="pdf",
                        )
                    )

                title = raw.get("MeetingType") or meeting_type
                video_url = raw.get("VideoUrl")
                if video_url:
                    video_url = urljoin(f"{self.base_url}/", video_url)

                meetings.append(
                    ScrapedMeeting(
                        date=meeting_date,
                        title=title,
                        meeting_type=utils.infer_meeting_type(title),
                        organization_name=self.municipality.name,
                        agenda_url=agenda_url,
                        minutes_url=minutes_url,
                        video_url=video_url,
                        source_id=meeting_id,
                        documents=documents,
                        meta={"escribe_meeting": raw},
                    )
                )

        meetings.sort(key=lambda m: m.date, reverse=True)
        print(f"  [eSCRIBE] Discovered {len(meetings)} meeting(s)")
        return meetings

    def download_documents(self, meeting: ScrapedMeeting, target_dir: str) -> list[str]:
        os.makedirs(target_dir, exist_ok=True)
        downloaded: list[str] = []

        if meeting.video_url:
            video_dir = os.path.join(target_dir, "Video")
            os.makedirs(video_dir, exist_ok=True)
            with open(os.path.join(video_dir, "player.url"), "w", encoding="utf-8") as f:
                f.write(meeting.video_url)

        for doc in meeting.documents:
            if not doc.url:
                continue

            category = doc.category or "Other Documents"
            subfolder = os.path.join(target_dir, category)
            os.makedirs(subfolder, exist_ok=True)

            filename = self._filename_for_document(doc)
            file_path = os.path.join(subfolder, filename)

            if os.path.exists(file_path):
                downloaded.append(file_path)
                continue

            try:
                with self.session.get(doc.url, stream=True, timeout=config.REQUEST_TIMEOUT) as resp:
                    resp.raise_for_status()
                    with open(file_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                with open(f"{file_path}.url", "w", encoding="utf-8") as f:
                    f.write(doc.url)
                print(f"  [+] Downloaded: {filename}")
                downloaded.append(file_path)
                time.sleep(config.DELAY_BETWEEN_REQUESTS)
            except requests.RequestException as e:
                print(f"  [!] Failed to download {doc.title}: {e}")

        return downloaded

    def _fetch_meetings_for_type(self, meeting_type: str) -> list[dict]:
        endpoint = f"{self.base_url}/MeetingsCalendarView.aspx/PastMeetings"
        meetings: list[dict] = []
        page = 1

        # Prime ASP.NET session/cookies. The JSON endpoint is public, but this
        # mirrors browser behavior and avoids brittle anti-CSRF assumptions.
        try:
            self.session.get(
                f"{self.base_url}/meetingscalendarview.aspx",
                params={"Expanded": meeting_type, "fillWidth": "1"},
                timeout=config.REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            pass

        while True:
            resp = self.session.post(
                endpoint,
                params={"Expanded": meeting_type, "fillWidth": "1"},
                json={"type": meeting_type, "pageNumber": page},
                headers={
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json().get("d") or {}
            batch = payload.get("Meetings") or []
            meetings.extend(batch)

            total = int(payload.get("TotalCount") or len(meetings))
            if len(meetings) >= total or not batch:
                break
            page += 1
            time.sleep(config.DELAY_BETWEEN_REQUESTS)

        return meetings

    @staticmethod
    def _parse_meeting_date(raw: dict) -> date | None:
        start = raw.get("Start") or ""
        match = re.search(r"/Date\((-?\d+)\)/", start)
        if match:
            return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).date()

        for key in ("DateMedium", "MeetingDate", "DateShort"):
            value = raw.get(key)
            if not value:
                continue
            for fmt in ("%b %d, %Y", "%B %d, %Y"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
        return None

    @staticmethod
    def _document_category(link: dict) -> str:
        link_type = link.get("Type") or ""
        title = (link.get("Title") or "").lower()
        if link_type in {"Agenda", "AgendaCover"} or "agenda" in title:
            return "Agenda"
        if link_type == "PostMinutes" or "minutes" in title:
            return "Minutes"
        return "Other Documents"

    @staticmethod
    def _clean_title(title: str) -> str:
        return re.sub(r"\s*\((PDF|HTML)\)\s*$", "", title, flags=re.IGNORECASE).strip()

    @staticmethod
    def _filename_for_document(doc: ScrapedDocument) -> str:
        parsed_name = os.path.basename(urlparse(doc.url).path)
        if parsed_name and parsed_name.lower().endswith(".pdf"):
            return utils.sanitize_filename(parsed_name)
        return f"{utils.sanitize_filename(doc.title)}.pdf"
