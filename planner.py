# planner.py
import os
import json
import re
from typing import Dict, Any, List
import requests
import pandas as pd
import numpy as np
from urllib.parse import urlparse, parse_qs
from openai import OpenAI
from browser import fetch_quiz_page

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def analyze_quiz_page(page: Dict[str, Any]) -> Dict[str, Any]:
    body_text = page["body_text"]
    links = page["links"]

    links_text = "\n".join(
        f"- text: {l.get('text', '').strip()} | href: {l.get('href', '')}"
        for l in links
    )

    system_msg = (
    "You only describe what should go in the 'answer' field of the POST payload. "
    "Do NOT include email, secret, or url inside the answer. "
    "Only include data needed to compute the answer itself. "
    "Choose answer_type strictly based on what the task asks: "
    "'number', 'string', 'boolean', 'object', or 'file_base64'. "
    "Use data_sources ONLY for files explicitly required by the question. "
    "Extract the correct submit_url from phrases like 'Post your answer to'. "
    "Be precise and avoid inventing extra steps or parameters."
)


    user_msg = f"""
Page text:
\"\"\"{body_text}\"\"\"

Links:
{links_text}

Return JSON like:
{{
  "question_summary": "...",
  "submit_url": "https://...",
  "data_sources": [
    {{
      "type": "file",
      "url": "https://...",
      "format": "pdf"
    }}
  ],
  "answer_type": "number | string | boolean | object | file_base64",
  "answer_instructions": "Step-by-step description of what to compute."
}}
"""

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
    )

    # Extract the text from the Responses API output
    content = resp.output[0].content[0].text.strip()

    # In case the model wraps JSON in ```json ... ``` or extra text
    if content.startswith("```"):
        lines = [ln for ln in content.splitlines() if not ln.strip().startswith("```")]
        content = "\n".join(lines).strip()

    # Best-effort: if there's extra text, try to pull out the first {...} block
    if not (content.strip().startswith("{") and content.strip().endswith("}")):
        import re
        m = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if m:
            content = m.group(0).strip()

    try:
        plan = json.loads(content)
    except Exception as e:
        raise RuntimeError(f"Failed to parse planner JSON: {e}\nRaw: {content}")

    return plan



def _extract_secret_code_from_html(html_bytes: bytes) -> str:
    try:
        html_text = html_bytes.decode("utf-8", errors="ignore")
    except Exception:
        html_text = str(html_bytes)

    # Strip tags → plain-ish text
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text).strip()

    # More robust: "secret code" optionally followed by "is", then non-alnum, then the code
    m = re.search(
        r"(?i)secret\s+code(?:\s+is)?[^A-Za-z0-9]+([A-Za-z0-9_-]{4,})",
        text,
    )
    if m:
        return m.group(1).strip(" .,:;\"'")

    # Fallback: last alphanumeric-like token (not ideal, but prevents total failure)
    tokens = re.findall(r"[A-Za-z0-9_-]+", text)
    if tokens:
        return tokens[-1].strip(" .,:;\"'")

    return "UNKNOWN_CODE"


def compute_answer_from_data(
    plan: Dict[str, Any],
    context: Dict[str, Any],
    page_text: str,
    meta: Dict[str, Any],
):
    """
    Handles:
    1) Demo '/demo' tasks: any string/object answer.
    2) HTML 'secret code' scrape.
    3) Generic CSV/PDF/API/text analysis via LLM-generated Python code.
    Supports numbers, strings, booleans, objects, and file_base64 (for charts/files).
    """
    answer_type = str(plan.get("answer_type", "")).lower()
    instructions = str(plan.get("answer_instructions", "")).lower()
    data_sources = plan.get("data_sources", [])
    pdf_tables: List[pd.DataFrame] = context.get("pdf_tables", [])
    csv_tables: List[pd.DataFrame] = context.get("csv_tables", [])
    raw_files = context.get("raw", [])
    api_results = context.get("api_results", [])

    quiz_url = meta.get("quiz_url", "")
    if "demo-audio" in quiz_url:
        # Whatever the planner says, treat the answer as a simple number/string.
        # Let the LLM compute a scalar and return that as answer.
        if answer_type == "object":
            answer_type = "number"

    # ---------- Case 1: demo '/demo' tasks (any string/object is fine) ----------
    path = urlparse(quiz_url).path
    if path == "/demo" and "secret code" not in instructions:
        # STRING answers
        if answer_type == "string":
            return "demo-answer-from-bot"

        # OBJECT demo answers like "keys 'email', 'secret', 'url', 'answer'"
        if answer_type == "object" and "email" in instructions and "secret" in instructions:
            return {
                "email": meta.get("email"),
                "secret": meta.get("secret"),
                "url": quiz_url,
                "answer": "demo-answer-from-bot",
            }

        # ---------- Case 2: HTML 'secret code' scrape ----------
    if "secret code" in instructions:
        scraped_url = None

        # Prefer deriving the scrape URL from quiz_url to preserve all params (email + id)
        parsed_quiz = urlparse(quiz_url)
        if "demo-scrape" in parsed_quiz.path:
            new_path = parsed_quiz.path.replace("demo-scrape", "demo-scrape-data")
            scraped_url = parsed_quiz._replace(path=new_path).geturl()

        # If we still don't have a URL, fall back to planner data_sources
        if scraped_url is None:
            if data_sources:
                scraped_url = data_sources[0].get("url")
            else:
                scraped_url = quiz_url

        # Use Playwright to render the page and get text
        scrape_page = fetch_quiz_page(scraped_url)
        body_text = scrape_page["body_text"]

        # Reuse extractor, but now from rendered text
        code = _extract_secret_code_from_html(body_text.encode("utf-8"))

        # For these tasks, the platform expects the raw code string
        return code


    # ---------- Case 3: generic data / API / PDF / CSV / viz via LLM code ----------

    def preview_tables(pdf_tables: List[pd.DataFrame], csv_tables: List[pd.DataFrame]) -> str:
        parts: List[str] = []
        for i, df in enumerate(pdf_tables):
            parts.append(f"PDF table {i} columns: {list(df.columns)}")
            parts.append(df.head(5).to_csv(index=False))
        for i, df in enumerate(csv_tables):
            parts.append(f"CSV table {i} columns: {list(df.columns)}")
            parts.append(df.head(5).to_csv(index=False))
        return "\n\n".join(parts)

    tables_preview = preview_tables(pdf_tables, csv_tables)[:4000]
    page_trunc = page_text[:4000]

    system_msg = (
    "You write pure Python code (no markdown) to compute the quiz answer EXACTLY "
    "as described in page_text.\n"
    "The grading server knows the correct answer and will reject approximations.\n\n"
    "STRICT RULES:\n"
    "1) Use the actual data in pdf_tables, csv_tables, api_results, raw_files, or "
    "   page_text. DO NOT invent example numbers or lists.\n"
    "   - If a CSV file is involved, you MUST read from csv_tables (or data loaded "
    "     from raw_files) and derive all numeric values from it.\n"
    "2) Do NOT hard-code arbitrary numeric arrays like values = [1, 2, 3, ...].\n"
    "   Any list of numbers must be derived from the real tables.\n"
    "3) If the text says 'sum', compute the exact numeric sum of the specified field.\n"
    "   If it says 'count', compute the exact count, etc.\n"
    "4) If there is a cutoff mentioned (e.g. 'Cutoff: 47170'), parse it from "
    "   page_text and apply it exactly as described.\n"
    "5) Use real column names from the DataFrames (case-insensitive matching is OK).\n"
    "   Never guess column names that are not present.\n"
    "6) Store only the final result in a variable named `answer`.\n"
    "   No prints, no imports.\n"
    "If answer_type is 'file_base64', create the file in-memory and base64-encode "
    "it as a data: URI string."
)



    user_msg = f"""
answer_type: {answer_type}

Quiz instructions:
{plan.get("answer_instructions", "")}

Question summary:
{plan.get("question_summary", "")}

Page text (truncated):
\"\"\"{page_trunc}\"\"\"

Sample of available tables (truncated):
\"\"\"{tables_preview}\"\"\"

Write ONLY Python code (no backticks, no comments) that:
- Uses pdf_tables / csv_tables / api_results / raw_files / page_text / meta as needed.
- Computes the answer as specified.
- Sets variable `answer` to:
  - number, if answer_type is 'number'
  - string, if answer_type is 'string'
  - bool, if answer_type is 'boolean'
  - dict, if answer_type is 'object'
  - base64 data URI string, if answer_type is 'file_base64'.
"""

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
    )

    code = resp.output[0].content[0].text.strip()
    # Strip accidental ``` wrappers
    if code.startswith("```"):
        lines = [ln for ln in code.splitlines() if not ln.strip().startswith("```")]
        code = "\n".join(lines).strip()

    if csv_tables and "csv_tables" not in code and "pd.read_csv" not in code:
      print("WARNING: generated code does not use CSV tables:\n")
    import json as _json
    import base64 as _base64
    import io as _io

    env: Dict[str, Any] = {
        "pdf_tables": pdf_tables,
        "csv_tables": csv_tables,
        "api_results": api_results,
        "raw_files": raw_files,
        "page_text": page_text,
        "meta": meta,
        "pd": pd,
        "np": np,
        "json": _json,
        "base64": _base64,
        "io": _io,
        "answer": None,
    }

    try:
        # Use the same dict for globals and locals for predictable behavior
        print("\n======= GENERATED CODE START =======\n")
        print(code)
        print("\n======= GENERATED CODE END =======\n")
        exec(code, env, env)
    except Exception as e:
        raise RuntimeError(f"Error executing generated code: {e}\nCode:\n{code}")

    if "answer" not in env or env["answer"] is None:
        raise RuntimeError(f"Generated code did not set 'answer'. Code:\n{code}")

    return env["answer"]
