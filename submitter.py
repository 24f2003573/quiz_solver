from typing import Any, Dict
import requests


def submit_answer(
    email: str,
    secret: str,
    quiz_url: str,
    submit_url: str,
    answer: Any,
    timeout: int = 60,
) -> Dict[str, Any]:
    payload = {
        "email": email,
        "secret": secret,
        "url": quiz_url,
        "answer": answer,
    }
    try:
        r = requests.post(submit_url, json=payload, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Submit to {submit_url} failed: {e}, payload={payload}")
    return r.json()
