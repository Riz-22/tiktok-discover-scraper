thonimport json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .utils import convert_unix_to_iso, normalize_hashtag

@dataclass
class TikTokDiscoverParser:
    session: requests.Session
    base_url: str
    logger: logging.Logger
    timeout: int = 20

    def _discover_url(self, hashtag: str) -> str:
        tag = normalize_hashtag(hashtag)
        return f"{self.base_url}/{tag}"

    def fetch_discover_page(self, hashtag: str) -> str:
        url = self._discover_url(hashtag)
        self.logger.info("Fetching TikTok Discover page: %s", url)
        resp = self.session.get(url, timeout=self.timeout)
        if not resp.ok:
            self.logger.error("TikTok responded with status %s for %s", resp.status_code, url)
            resp.raise_for_status()
        self.logger.debug("Fetched %d bytes for %s", len(resp.text), url)
        return resp.text

    def parse_videos_from_html(self, html: str, source_hashtag: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        script_tag = soup.find("script", id="SIGI_STATE")

        if not script_tag or not script_tag.string:
            self.logger.warning("Could not find SIGI_STATE JSON in page; returning empty result set.")
            return []

        try:
            state = json.loads(script_tag.string)
        except json.JSONDecodeError as exc:
            self.logger.error("Failed to parse SIGI_STATE JSON: %s", exc)
            return []

        item_module = state.get("ItemModule", {})
        if not isinstance(item_module, dict) or not item_module:
            self.logger.warning("SIGI_STATE.ItemModule missing or empty; no videos found.")
            return []

        music_module = state.get("MusicModule", {}).get("music", {})
        user_module = state.get("UserModule", {})

        videos: List[Dict[str, Any]] = []
        for video_id, item in item_module.items():
            try:
                record = self._build_video_record(
                    video_id=video_id,
                    item=item,
                    music_module=music_module,
                    user_module=user_module,
                    source_hashtag=source_hashtag,
                )
                videos.append(record)
            except Exception as exc:
                self.logger.debug("Failed to build record for video %s: %s", video_id, exc)

        return videos

    def _build_video_record(
        self,
        video_id: str,
        item: Dict[str, Any],
        music_module: Dict[str, Any],
        user_module: Dict[str, Any],
        source_hashtag: str,
    ) -> Dict[str, Any]:
        stats = item.get("stats", {}) or {}
        create_time_raw: Optional[int] = None
        try:
            create_time_raw = int(item.get("createTime", 0))
        except (TypeError, ValueError):
            create_time_raw = None

        author_name = item.get("author") or ""
        author_stats = (user_module.get("stats") or {}).get(author_name, {}) or {}

        author_meta = {
            "id": author_name,
            "name": author_name,
            "nickname": (user_module.get("user") or {}).get(author_name, {}).get("nickname"),
            "followers": author_stats.get("followerCount", 0),
            "following": author_stats.get("followingCount", 0),
            "likes": author_stats.get("heartCount", 0),
            "videos": author_stats.get("videoCount", 0),
        }

        music_id = item.get("musicId") or item.get("music", "")
        music_data = music_module.get(music_id, {}) if isinstance(music_module, dict) else {}
        music_meta = {
            "musicId": music_id,
            "musicName": music_data.get("title") or music_data.get("name"),
            "musicAuthor": music_data.get("authorName") or music_data.get("author"),
            "coverThumb": music_data.get("coverThumb"),
            "coverMedium": music_data.get("coverMedium"),
            "coverLarge": music_data.get("coverLarge"),
        }

        hashtags = []
        for tag in item.get("textExtra", []) or []:
            if isinstance(tag, dict):
                name = tag.get("hashtagName")
                if name:
                    hashtags.append(name)

        play_count = self._safe_int(stats.get("playCount"))
        share_count = self._safe_int(stats.get("shareCount"))
        digg_count = self._safe_int(stats.get("diggCount"))
        comment_count = self._safe_int(stats.get("commentCount"))
        collect_count = self._safe_int(stats.get("collectCount"))

        is_ad = bool(item.get("isAd", False))

        web_video_url = item.get("shareUrl")
        if not web_video_url and author_name:
            web_video_url = f"https://www.tiktok.com/@{author_name}/video/{video_id}"

        video_meta = {
            "width": self._safe_int(item.get("video", {}).get("width")),
            "height": self._safe_int(item.get("video", {}).get("height")),
            "duration": self._safe_int(item.get("video", {}).get("duration")),
            "ratio": item.get("video", {}).get("ratio"),
            "format": item.get("video", {}).get("format"),
        }

        media_urls = []
        play_addr = item.get("video", {}).get("playAddr")
        if isinstance(play_addr, str):
            media_urls.append(play_addr)
        download_addr = item.get("video", {}).get("downloadAddr")
        if isinstance(download_addr, str) and download_addr not in media_urls:
            media_urls.append(download_addr)

        discovery_info = {
            "source": "discover",
            "sourceHashtag": normalize_hashtag(source_hashtag),
            "breadcrumb": item.get("suggestedWords") or None,
        }

        record: Dict[str, Any] = {
            "id": video_id,
            "text": item.get("desc"),
            "createTime": create_time_raw,
            "createTimeISO": convert_unix_to_iso(create_time_raw) if create_time_raw is not None else None,
            "isAd": is_ad,
            "authorMeta": author_meta,
            "musicMeta": music_meta,
            "webVideoUrl": web_video_url,
            "mediaUrls": media_urls,
            "videoMeta": video_meta,
            "diggCount": digg_count,
            "shareCount": share_count,
            "playCount": play_count,
            "collectCount": collect_count,
            "commentCount": comment_count,
            "hashtags": hashtags,
            "discoveryInfo": discovery_info,
        }

        return record

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default