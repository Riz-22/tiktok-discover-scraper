thonimport csv
import json
import logging
from html import escape as html_escape
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value, ensure_ascii=False)
        else:
            flat[key] = value
    return flat

def export_json(data: List[Dict[str, Any]], path: Path, logger: logging.Logger) -> None:
    ensure_output_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Exported %d records to JSON: %s", len(data), path)

def export_csv(data: List[Dict[str, Any]], path: Path, logger: logging.Logger) -> None:
    if not data:
        logger.warning("No data to export to CSV at %s", path)
        return

    ensure_output_dir(path.parent)
    normalized = [normalize_record(rec) for rec in data]
    fieldnames = sorted({key for rec in normalized for key in rec.keys()})

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in normalized:
            writer.writerow(rec)

    logger.info("Exported %d records to CSV: %s", len(data), path)

def export_excel(data: List[Dict[str, Any]], path: Path, logger: logging.Logger) -> None:
    if not data:
        logger.warning("No data to export to Excel at %s", path)
        return

    ensure_output_dir(path.parent)
    normalized = [normalize_record(rec) for rec in data]
    df = pd.DataFrame.from_records(normalized)
    df.to_excel(path, index=False, engine="openpyxl")
    logger.info("Exported %d records to Excel: %s", len(data), path)

def export_xml(data: List[Dict[str, Any]], path: Path, logger: logging.Logger) -> None:
    from xml.etree.ElementTree import Element, SubElement, ElementTree

    root = Element("videos")

    for rec in data:
        video_el = SubElement(root, "video")
        for key, value in rec.items():
            child = SubElement(video_el, key)
            if isinstance(value, (dict, list)):
                child.text = json.dumps(value, ensure_ascii=False)
            else:
                child.text = "" if value is None else str(value)

    ensure_output_dir(path.parent)
    tree = ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    logger.info("Exported %d records to XML: %s", len(data), path)

def export_html(data: List[Dict[str, Any]], path: Path, logger: logging.Logger) -> None:
    ensure_output_dir(path.parent)

    if not data:
        html = "<html><head><meta charset='utf-8'><title>TikTok Discover Export</title></head>" \
               "<body><h1>No data available</h1></body></html>"
        path.write_text(html, encoding="utf-8")
        logger.warning("No data to export to HTML at %s", path)
        return

    normalized = [normalize_record(rec) for rec in data]
    fieldnames = sorted({key for rec in normalized for key in rec.keys()})

    head = (
        "<html><head><meta charset='utf-8'>"
        "<title>TikTok Discover Export</title>"
        "<style>"
        "body{font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222;}"
        "table{border-collapse:collapse;width:100%;}"
        "th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top;}"
        "th{background:#f5f5f5;}"
        "tr:nth-child(even){background:#fafafa;}"
        "</style>"
        "</head><body><h1>TikTok Discover Export</h1>"
    )

    table_headers = "".join(f"<th>{html_escape(col)}</th>" for col in fieldnames)
    rows_html: List[str] = []
    for rec in normalized:
        cells: Iterable[str] = []
        for col in fieldnames:
            value = rec.get(col, "")
            if value is None:
                value = ""
            cells = list(cells) + [f"<td>{html_escape(str(value))}</td>"]
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    table = "<table><thead><tr>" + table_headers + "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"
    tail = "</body></html>"

    path.write_text(head + table + tail, encoding="utf-8")
    logger.info("Exported %d records to HTML: %s", len(data), path)

def export_all(
    data: List[Dict[str, Any]],
    output_dir: Path,
    formats: List[str],
    logger: logging.Logger,
) -> None:
    ensure_output_dir(output_dir)
    base_path = output_dir / "tiktok_discover_export"

    logger.info("Exporting data in formats: %s", ", ".join(formats))

    if "json" in formats:
        export_json(data, base_path.with_suffix(".json"), logger)
    if "csv" in formats:
        export_csv(data, base_path.with_suffix(".csv"), logger)
    if "excel" in formats:
        export_excel(data, base_path.with_suffix(".xlsx"), logger)
    if "xml" in formats:
        export_xml(data, base_path.with_suffix(".xml"), logger)
    if "html" in formats:
        export_html(data, base_path.with_suffix(".html"), logger)