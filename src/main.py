thonimport argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests

from extractors.utils import load_settings, setup_logger, convert_unix_to_iso
from extractors.tiktok_discover_parser import TikTokDiscoverParser
from outputs.exporters import export_all

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TikTok Discover Scraper - scrape Discover page videos for one or more hashtags."
    )
    parser.add_argument(
        "--hashtags",
        nargs="*",
        help="One or more hashtags to scrape from TikTok Discover (without #). Example: travel tiktok",
    )
    parser.add_argument(
        "--input-file",
        type=str,
        help="Optional path to a JSON file containing pre-scraped TikTok video data "
             "(list of objects). If provided, network scraping is skipped.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory where exported files will be written. Defaults to <project_root>/data.",
    )
    parser.add_argument(
        "--formats",
        nargs="*",
        choices=["json", "csv", "excel", "xml", "html"],
        help="Output formats. Overrides config if provided.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of videos per hashtag.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds for TikTok requests.",
    )
    return parser.parse_args()

def resolve_paths() -> Dict[str, Path]:
    base_dir = Path(__file__).resolve().parent
    project_root = base_dir.parent
    config_path = base_dir / "config" / "settings.json"
    data_dir = project_root / "data"
    return {
        "base_dir": base_dir,
        "project_root": project_root,
        "config_path": config_path,
        "data_dir": data_dir,
    }

def load_input_file(path: Path, logger) -> List[Dict[str, Any]]:
    if not path.exists():
        logger.error("Input file %s does not exist.", path)
        raise FileNotFoundError(f"Input file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from %s: %s", path, exc)
        raise

    if not isinstance(data, list):
        logger.error("Input file %s must contain a JSON list of video objects.", path)
        raise ValueError("Input JSON must be a list of video objects.")

    logger.info("Loaded %d video records from %s", len(data), path)
    return data

def enrich_records(records: List[Dict[str, Any]], hashtag: Optional[str], logger) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []

    for record in records:
        rec = dict(record)  # shallow copy

        # Ensure createTimeISO is present if createTime is provided
        if "createTime" in rec and "createTimeISO" not in rec:
            try:
                rec["createTimeISO"] = convert_unix_to_iso(int(rec["createTime"]))
            except Exception as exc:
                logger.debug("Unable to convert createTime for record %s: %s", rec.get("id"), exc)

        # Add discoveryInfo if missing
        discovery_info = rec.get("discoveryInfo") or {}
        if hashtag:
            discovery_info.setdefault("sourceHashtag", hashtag)
        rec["discoveryInfo"] = discovery_info

        enriched.append(rec)

    return enriched

def main() -> None:
    args = parse_args()
    paths = resolve_paths()

    logger = setup_logger("tiktok_discover_scraper")

    try:
        settings = load_settings(paths["config_path"])
    except Exception as exc:
        logger.error("Unable to load settings: %s", exc)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else paths["data_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    formats = args.formats if args.formats else settings.get("output_formats", ["json", "csv"])
    base_url = settings.get("base_url", "https://www.tiktok.com/tag")
    user_agent = settings.get(
        "user_agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36",
    )

    if not args.hashtags and not args.input_file:
        logger.error("You must provide at least one hashtag or an --input-file.")
        sys.exit(1)

    all_records: List[Dict[str, Any]] = []

    if args.input_file:
        input_path = Path(args.input_file)
        raw_records = load_input_file(input_path, logger)
        # We don't know the hashtag origin; mark as "from_input_file".
        enriched = enrich_records(raw_records, hashtag="from_input_file", logger=logger)
        all_records.extend(enriched)
    else:
        session = requests.Session()
        session.headers.update({"User-Agent": user_agent})

        parser = TikTokDiscoverParser(
            session=session,
            base_url=base_url,
            logger=logger,
            timeout=args.timeout,
        )

        hashtags: List[str] = args.hashtags or []
        for tag in hashtags:
            normalized_tag = tag.lstrip("#").strip()
            if not normalized_tag:
                logger.warning("Skipping empty hashtag value: %r", tag)
                continue

            logger.info("Processing hashtag: #%s", normalized_tag)
            try:
                html = parser.fetch_discover_page(normalized_tag)
            except Exception as exc:
                logger.error("Failed to fetch Discover page for #%s: %s", normalized_tag, exc)
                continue

            try:
                videos = parser.parse_videos_from_html(html, source_hashtag=normalized_tag)
            except Exception as exc:
                logger.error("Failed to parse videos for #%s: %s", normalized_tag, exc)
                continue

            if args.limit is not None and len(videos) > args.limit:
                videos = videos[: args.limit]

            logger.info("Parsed %d videos for #%s", len(videos), normalized_tag)
            all_records.extend(videos)

    if not all_records:
        logger.warning("No video records collected; nothing to export.")
        sys.exit(0)

    try:
        export_all(all_records, output_dir=output_dir, formats=formats, logger=logger)
    except Exception as exc:
        logger.error("Failed to export data: %s", exc)
        sys.exit(1)

    logger.info("TikTok Discover scraping and export completed successfully.")

if __name__ == "__main__":
    main()