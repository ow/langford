"""Video source clients."""

from pipeline.video.isilive import ISILiveClient
from pipeline.video.vimeo import VimeoClient


class YouTubeClient:
    """Stub for YouTube video source. To be implemented for municipalities
    that publish meeting recordings on YouTube (e.g. RDOS).

    Expected source_config.video_source:
        {"type": "youtube", "channel": "RDOS"}
    """

    def __init__(self, channel: str = ""):
        self.channel = channel

    def get_video_map(self, limit=None):
        print(f"  [YouTube] Video sync not yet implemented (channel: {self.channel})")
        return {}

    def download_video(self, video_data, output_folder, **kwargs):
        print("  [YouTube] Video download not yet implemented")
        return None


def get_video_client(municipality=None):
    """Create a video client from municipality.source_config.video_source."""
    if municipality is None:
        return VimeoClient()

    source_config = municipality.source_config or {}
    video_config = source_config.get("video_source") or {}
    video_type = video_config.get("type", "vimeo")

    if video_type == "vimeo":
        return VimeoClient(vimeo_user=video_config.get("user", "viewroyal"))
    if video_type == "isilive":
        base_url = video_config.get("base_url") or source_config.get("base_url")
        client_id = video_config.get("client_id")
        if not base_url or not client_id:
            raise ValueError("ISI Live video source requires base_url and client_id")
        return ISILiveClient(
            base_url=base_url,
            client_id=client_id,
            meeting_types=source_config.get("meeting_types"),
            verify_ssl=source_config.get("verify_ssl", True),
        )
    if video_type == "youtube":
        return YouTubeClient(channel=video_config.get("channel", ""))

    raise ValueError(f"No video client registered for source type: {video_type}")
