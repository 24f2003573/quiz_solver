import io
from typing import Dict, Any, List, Optional

import requests
import pandas as pd
import pdfplumber
from urllib.parse import urljoin
import json


def download_binary(url: str, timeout: int = 60, headers: Dict[str, str] | None = None) -> bytes:
    r = requests.get(url, timeout=timeout, headers=headers)
    r.raise_for_status()
    return r.content


def load_pdf_tables_from_bytes(pdf_bytes: bytes) -> List[pd.DataFrame]:
    tables: List[pd.DataFrame] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables() or []
            for t in page_tables:
                if not t:
                    continue
                df = pd.DataFrame(t[1:], columns=t[0])
                tables.append(df)
    return tables


def load_csv_from_bytes(csv_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(csv_bytes))


def prepare_data_sources(
    data_sources: List[Dict[str, Any]],
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Download and parse all referenced data sources.

    Returns dict with:
      - pdf_tables: list[pd.DataFrame]
      - csv_tables: list[pd.DataFrame]
      - raw: list[{"url", "format", "bytes"}]
      - api_results: list[dict] (parsed JSON from API / JSON URLs)

    base_url is used to resolve relative URLs.
    """
    pdf_tables_all: List[pd.DataFrame] = []
    csv_tables_all: List[pd.DataFrame] = []
    raw_files: List[Dict[str, Any]] = []
    api_results: List[Any] = []

    for ds in data_sources:
        url = ds.get("url")
        fmt = (ds.get("format") or "").lower()
        ds_type = (ds.get("type") or "").lower()
        headers = ds.get("headers") or None

        if not url:
            continue

        # Resolve relative URLs if base_url provided
        if base_url is not None:
            url = urljoin(base_url, url)

        # API / JSON
        if ds_type == "api" or fmt in ("json", "application/json"):
            blob = download_binary(url, headers=headers)
            raw_files.append({"url": url, "format": fmt or "json", "bytes": blob})
            try:
                api_results.append(json.loads(blob.decode("utf-8")))
            except Exception:
                # If JSON parse fails, just keep raw blob
                pass
            continue

        # PDF / CSV / generic
        blob = download_binary(url, headers=headers)
        raw_files.append({"url": url, "format": fmt, "bytes": blob})

        if fmt == "pdf":
            pdf_tables_all.extend(load_pdf_tables_from_bytes(blob))
        elif fmt in ("csv", "text/csv"):
            csv_tables_all.append(load_csv_from_bytes(blob))

    return {
        "pdf_tables": pdf_tables_all,
        "csv_tables": csv_tables_all,
        "raw": raw_files,
        "api_results": api_results,
    }
