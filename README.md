# sie-offload

Move the boring parts of a coding agent off frontier models.

A coding agent spends most of its calls on work that doesn't need a frontier model:
summarizing diffs, tagging issues, pulling fields out of documents. This repo routes
those calls to small, task-specific models on SIE (Superlinked Inference Engine) and
keeps the expensive model for the hard reasoning.

## What it does

| Task | Where it goes |
| --- | --- |
| Summarize a git diff | `Qwen/Qwen3.8-27B-FP8` via `/v1/chat/completions` |
| Tag an issue / request | `/v1/extract` with `fastino/GLiNER2.5-Decide` |
| Pull structured fields from a doc | `/v1/chat/completions` with a JSON schema |

## Why SIE

One OpenAI-compatible endpoint for all three, so the client code doesn't change and
the whole thing can move to a self-hosted SIE Cluster later.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # then put your sk-sie- key in .env
```

## Run

```bash
python offload.py summarize sample_diff.txt
python offload.py classify "the export button does nothing on Safari"
python offload.py extract sample_doc.md
```

## Example output

```
$ python offload.py summarize sample_diff.txt
The `embed` method in `client.py` was updated to include a retry mechanism with
exponential backoff and a 30-second timeout, replacing the previous single-attempt
implementation. A new test file, `tests/test_client.py`, was added to verify that
the client correctly retries on transient failures like timeouts.

$ python offload.py classify "the export button does nothing on Safari"
bug report  0.696
feature request  0.12
account access  0.097
billing  0.088

$ python offload.py extract sample_doc.md
{"invoice_number": "INV-2041", "total": 128.5, "currency": "EUR", "due": "2026-12-01"}
```

## Notes

- Written against SIE Serverless (`https://api.superlinked.com`). Point `SIE_BASE_URL`
  at a local server or your own cluster and the same code works.
- The extraction step uses a strict JSON schema, so the caller gets typed fields
  instead of prose.

## License

MIT
