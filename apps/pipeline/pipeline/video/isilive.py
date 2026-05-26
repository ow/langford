"""ISI Live video client used by eSCRIBE portals."""

from __future__ import annotations

import glob
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import requests
import yt_dlp

from pipeline import config, utils


class ISILiveClient:
    """Fetch and download recordings from ISI Live/eSCRIBE player links."""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        meeting_types: list[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.meeting_types = meeting_types or ["Council Meeting"]
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})

    def get_video_map(self, limit=None):
        print("\n--- Fetching Video Metadata (ISI Live/eSCRIBE) ---")
        video_map: dict[str, list[dict]] = {}
        count = 0

        for meeting_type in self.meeting_types:
            for meeting in self._fetch_meetings_for_type(meeting_type):
                if limit and count >= limit:
                    break

                video_url = meeting.get("VideoUrl")
                if not video_url:
                    continue

                date_key = self._meeting_date_key(meeting)
                if not date_key:
                    continue

                player_url = urljoin(f"{self.base_url}/", video_url)
                title = f"{date_key} {meeting.get('MeetingType') or meeting_type}"
                video_map.setdefault(date_key, []).append(
                    {
                        "url": player_url,
                        "title": title,
                        "uri": meeting.get("Id"),
                        "duration": 0,
                        "client_id": self.client_id,
                    }
                )
                count += 1

            if limit and count >= limit:
                break

        print(f"[*] Found {len(video_map)} video date(s).")
        return video_map

    def search_video(self, date_str, title_hint=None):
        videos = self.get_video_map()
        matches = videos.get(date_str) or []
        if not matches:
            return None
        if len(matches) == 1 or not title_hint:
            return matches[0]

        hint = title_hint.lower()
        return next((v for v in matches if self._matches_hint(v["title"], hint)), None)

    def download_video(
        self,
        video_data,
        output_folder,
        include_video=False,
        download_audio=False,
    ):
        os.makedirs(output_folder, exist_ok=True)

        if include_video and glob.glob(os.path.join(output_folder, "*.mp4")):
            include_video = False
        if download_audio and (
            glob.glob(os.path.join(output_folder, "*.mp3"))
            or glob.glob(os.path.join(output_folder, "*.m4a"))
            or glob.glob(os.path.join(output_folder, "*.wav"))
        ):
            download_audio = False

        media_url = self._resolve_media_url(video_data)
        if not media_url:
            print(f"  [!] Could not resolve ISI media URL for {video_data.get('title')}")
            return None

        if include_video:
            self._download_ytdlp(media_url, output_folder, audio_only=False)

        if download_audio:
            self._download_ytdlp(media_url, output_folder, audio_only=True)
            files = (
                glob.glob(os.path.join(output_folder, "*.mp3"))
                + glob.glob(os.path.join(output_folder, "*.m4a"))
                + glob.glob(os.path.join(output_folder, "*.wav"))
            )
            if files:
                return max(files, key=os.path.getctime)

        return None

    def _resolve_media_url(self, video_data: dict) -> str | None:
        player_url = video_data.get("url")
        if not player_url:
            return None

        try:
            resp = self.session.get(player_url, timeout=config.REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [!] Failed to fetch ISI player: {e}")
            return None

        client_id = self._extract_attr(resp.text, "data-client_id") or video_data.get("client_id") or self.client_id
        file_name = self._extract_attr(resp.text, "data-file_name")
        if not file_name:
            return None

        return f"https://video.isilive.ca/{quote(client_id)}/{quote(file_name)}"

    def _download_ytdlp(self, media_url: str, output_folder: str, audio_only: bool):
        opts = {
            "outtmpl": os.path.join(output_folder, "%(title)s.%(ext)s"),
            "quiet": False,
            "no_warnings": True,
        }
        if audio_only:
            opts.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    ],
                }
            )
        else:
            opts["format"] = "bestvideo+bestaudio/best"

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([media_url])

    def _fetch_meetings_for_type(self, meeting_type: str) -> list[dict]:
        endpoint = f"{self.base_url}/MeetingsCalendarView.aspx/PastMeetings"
        meetings: list[dict] = []
        page = 1

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
    def _meeting_date_key(raw: dict) -> str | None:
        start = raw.get("Start") or ""
        match = re.search(r"/Date\((-?\d+)\)/", start)
        if match:
            return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).date().isoformat()
        return utils.extract_date_from_string(raw.get("FormattedStart") or "")

    @staticmethod
    def _extract_attr(html: str, attr: str) -> str | None:
        match = re.search(rf'{re.escape(attr)}=["\']([^"\']+)["\']', html)
        return match.group(1) if match else None

    @staticmethod
    def _matches_hint(title: str, hint: str) -> bool:
        title = title.lower()
        if "public hearing" in hint:
            return "public hearing" in title
        if "committee" in hint or "cow" in hint:
            return "committee" in title or "cow" in title
        if "council" in hint:
            return "council" in title and "public hearing" not in title
        return False
