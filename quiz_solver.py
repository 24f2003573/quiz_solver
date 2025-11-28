import time
from typing import Any, Dict, List, Optional

from browser import fetch_quiz_page
from planner import analyze_quiz_page, compute_answer_from_data
from data_utils import prepare_data_sources
from submitter import submit_answer


def solve_quiz_sequence(
    email: str,
    secret: str,
    first_url: str,
    start_ts: float,
    time_limit: float = 180.0,
) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    current_url: Optional[str] = first_url

    def time_left() -> float:
        return time_limit - (time.time() - start_ts)

    while current_url and time_left() > 0:
        page = fetch_quiz_page(current_url)

        try:
            plan = analyze_quiz_page(page)
        except Exception as e:
            history.append(
                {
                    "quiz_url": current_url,
                    "error": f"analyze_quiz_page failed: {e}",
                }
            )
            break

        submit_url = plan.get("submit_url")
        data_sources = plan.get("data_sources", [])

        if not submit_url:
            history.append(
                {
                    "quiz_url": current_url,
                    "error": "No submit_url in plan",
                    "plan": plan,
                }
            )
            break

        # Use current_url as base to resolve relative data source URLs
        data_context = prepare_data_sources(data_sources, base_url=current_url)

        try:
            meta = {
                "email": email,
                "secret": secret,
                "quiz_url": current_url,
            }
            answer = compute_answer_from_data(
                plan,
                data_context,
                page_text=page["body_text"],
                meta=meta,
            )
        except Exception as e:
            history.append(
                {
                    "quiz_url": current_url,
                    "error": f"compute_answer_from_data failed: {e}",
                    "plan": plan,
                }
            )
            break

        try:
            resp = submit_answer(
                email=email,
                secret=secret,
                quiz_url=current_url,
                submit_url=submit_url,
                answer=answer,
            )
        except Exception as e:
            history.append(
                {
                    "quiz_url": current_url,
                    "answer": answer,
                    "error": f"submit failed: {e}",
                    "plan": plan,
                }
            )
            break

        history.append(
            {
                "quiz_url": current_url,
                "answer": answer,
                "response": resp,
                "plan": plan,
            }
        )

        correct = bool(resp.get("correct"))
        next_url = resp.get("url")

        # If there is a next URL, follow it; otherwise stop
        if next_url:
            current_url = next_url
        else:
            break

        if time_left() <= 0:
            break

    return history
