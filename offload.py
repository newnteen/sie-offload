"""Route routine coding-agent calls to small task models on SIE.

Three commands: summarize (diff -> text), classify (text -> labels),
extract (document -> typed JSON fields).
"""

import argparse
import json
import os
import pathlib
import time

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("SIE_BASE_URL", "https://api.superlinked.com")
API_KEY = os.environ.get("SIE_API_KEY")
if not API_KEY:
    raise SystemExit(
        "SIE_API_KEY is not set. Copy .env.example to .env and put your sk-sie- key in it."
    )
CHAT_MODEL = os.environ.get("SIE_CHAT_MODEL", "Qwen/Qwen3.8-27B-FP8")
CLASSIFIER = os.environ.get("SIE_CLASSIFIER", "fastino/GLiNER2.5-Decide")


def _post(path: str, payload: dict, retries: int = 5) -> dict:
    for attempt in range(retries):
        resp = requests.post(
            f"{BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                # SIE defaults to msgpack; ask for JSON so resp.json() works.
                "Accept": "application/json",
            },
            json=payload,
            timeout=120,
        )
        # Serverless returns 503 while a model cold-starts. Back off and retry.
        if resp.status_code in (429, 503) and attempt < retries - 1:
            try:
                delay = float(resp.headers.get("Retry-After", ""))
            except ValueError:
                delay = 2**attempt
            time.sleep(min(delay, 30))
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("unreachable")  # loop always returns or raises


def summarize(diff_text: str) -> str:
    out = _post(
        "/v1/chat/completions",
        {
            "model": CHAT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "Summarize a code diff in two sentences. Say what changed and whether behaviour changes.",
                },
                {"role": "user", "content": diff_text},
            ],
            "max_completion_tokens": 200,
            "temperature": 0,
        },
    )
    return out["choices"][0]["message"]["content"].strip()


def classify(text: str, labels: list[str]) -> dict:
    out = _post(
        f"/v1/extract/{CLASSIFIER}",
        {"items": [{"text": text}], "params": {"labels": labels}},
    )
    item = out["items"][0]
    return {
        c["label"]: round(float(c["score"]), 3)
        for c in item.get("classifications", [])
    }


SCHEMA = {
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string"},
        "total": {"type": "number"},
        "currency": {"type": "string"},
        "due": {"type": "string"},
    },
    "required": ["invoice_number", "total", "currency", "due"],
}


def extract(document: str) -> dict:
    instruction = (
        "Extract the fields described by the JSON schema from the document. "
        "Use null when the document does not state a value."
    )
    out = _post(
        "/v1/chat/completions",
        {
            "model": CHAT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": f"{instruction}\n\nRequired JSON schema:\n{json.dumps(SCHEMA, indent=2)}",
                },
                {"role": "user", "content": document},
            ],
            "max_completion_tokens": 512,
            "temperature": 0,
            "presence_penalty": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "invoice", "strict": True, "schema": SCHEMA},
            },
        },
    )
    return json.loads(out["choices"][0]["message"]["content"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sum = sub.add_parser("summarize")
    p_sum.add_argument("path", type=pathlib.Path)

    p_cls = sub.add_parser("classify")
    p_cls.add_argument("text")

    p_ext = sub.add_parser("extract")
    p_ext.add_argument("path", type=pathlib.Path)

    args = parser.parse_args()

    if args.cmd == "summarize":
        print(summarize(args.path.read_text(encoding="utf-8")))
    elif args.cmd == "classify":
        labels = ["bug report", "feature request", "billing", "account access"]
        for label, score in sorted(classify(args.text, labels).items(), key=lambda kv: -kv[1]):
            print(f"{label}  {score}")
    elif args.cmd == "extract":
        print(json.dumps(extract(args.path.read_text(encoding="utf-8")), ensure_ascii=False))


if __name__ == "__main__":
    main()
