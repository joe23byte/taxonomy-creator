# Intent Studio — Local AI Taxonomy Discovery

Intent Studio turns customer-service transcripts into a traceable **L1 → L2 → L3 → L4 intent taxonomy**.
L1/L2 are predefined and fixed; L3/L4 are discovered from the data with a local LLM (Ollama), semantic
embeddings and density-based clustering. Every step is persisted, streamed live to the UI, reviewable and exportable.

```
Transcript ──► LLM extraction (qwen3:8b, JSON schema) ──► atomic intents + evidence + L2
          ──► embeddings (qwen3-embedding:0.6b, cached) ──► match existing L4 (cosine ≥ threshold)
                                                         └─► otherwise: open candidate
every N interactions (batch) ──► HDBSCAN per L2 ──► LLM names clusters ──► L3/L4 proposals
                                                  ──► overlap / split detection ──► merge/split proposals
end of run ──► LLM places rare intents (outliers) or leaves them for human review
```

## Quick start

Requirements: Python 3.11+, Node 18+, an Ollama server with `qwen3:8b` and `qwen3-embedding:0.6b`.

```bash
# 1. configuration
cp .env.example .env            # set OLLAMA_URL=http://<gaming-pc>:11434

# 2. backend (FastAPI on http://127.0.0.1:8000)
cd backend
uv venv --python 3.12 .venv     # or: python3.12 -m venv .venv
uv pip install --python .venv/bin/python -r requirements.txt   # or: .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app

# 3. frontend (Vite on http://127.0.0.1:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173**, check the connection indicator in the header (Settings → *Test connection*
runs a real inference and embedding request), click **Load 100 Sample Interactions**, then **Start Analysis**.

Single-process alternative: `cd frontend && npm run build`, then start only the backend and open http://127.0.0.1:8000.

Tests: `cd backend && .venv/bin/python -m pytest` (uses a deterministic fake Ollama; no network).
Regenerate the synthetic dataset: `cd backend && .venv/bin/python scripts/generate_sample_data.py`.

## Demo walkthrough (acceptance test)

1. Header shows **Ollama connected**; Settings → Test connection shows inference + 1024-dim embeddings.
2. Workspace → **Load 100 Sample Interactions** → the Taxonomy tab shows the 4 L1 / 14 L2 fixed categories.
3. **Start Analysis**. The activity feed (SSE) shows each step per interaction; L2 nodes show growing
   "open" candidate counts; after each batch of 25, new L3/L4 nodes slide in (blue, sparkle icon), counts bump,
   touched nodes are highlighted, merges/splits are flagged in amber.
4. Click an L4 node → description, supporting customer quotes, creation/revision history.
5. Click a quote or open *Interactions* → full transcript with highlighted evidence, extracted intents, taxonomy
   path, cosine similarity, method, AI reasoning, alternative categories.
6. **Correct** an assignment (cascading L1–L4 selects) or Confirm / Unclassified / Flag; add notes.
7. Taxonomy → *Proposals* tab → approve or reject merges, splits and conflicting new categories.
8. **Export Results** → Excel (4 sheets), CSV or JSON.
9. Stop the backend and start it again: everything is in SQLite; an interrupted run shows **Resume**.

Processing time with qwen3:8b on a consumer GPU is roughly 4–7 s per interaction (≈10–15 min for 100).

## Project structure

```
backend/
  app/
    main.py              FastAPI routes, SSE endpoint, error handling, optional static frontend
    config.py            env defaults + sensitivity presets (UI settings stored in SQLite override them)
    db.py                SQLite connection, migrations runner, crash recovery, settings
    migrations/          versioned SQL schema (applied automatically at startup)
    ollama_client.py     /api/tags, /api/chat (JSON schema, think:false), /api/embed, retries, connection test
    importers.py         JSON / CSV / Excel / TXT → canonical records, column mapping, validation
    extraction.py        intent extraction prompt + schema, evidence verification
    embeddings.py        embedding cache (SQLite BLOBs keyed by model + text hash), centroids
    clustering.py        cosine similarity, HDBSCAN, agglomerative fallback, split detection
    taxonomy.py          nodes, proposals, accept/reject, merge/split/refine, versions, manual edits
    taxonomy_builder.py  LLM prompts for cluster naming, outlier placement, refinement, split labels
    assignments.py       many-to-many assignments, review actions, audit history
    pipeline.py          per-interaction processing and batch refinement
    worker.py            single background worker: start / pause / stop / resume / re-cluster
    events.py            persisted event log + SSE tailing (replayable)
    interactions.py      read models for the review UI
    insights.py          progress metrics and discovery curve
    evaluation.py        optional ground-truth comparison (Insights only, never used by the pipeline)
    export.py            Excel / CSV / JSON exports
  data/
    taxonomy_seed.json   editable predefined L1/L2 taxonomy
    sample/              sample_transcripts.json/.csv, sample_ground_truth.json, import_template.csv
  scripts/generate_sample_data.py   reproducible synthetic dataset (fixed seed)
  tests/                 pytest suite with a fake Ollama transport
frontend/
  src/views/             Workspace, TaxonomyView, InteractionsView, InsightsView
  src/components/        taxonomy tree & detail, activity feed, interaction detail, dialogs, ui primitives
  src/lib/               API client, live SSE provider
```

## How the taxonomy is built

**Extraction.** Each transcript is sent with the active L2 list to `qwen3:8b` (`think: false`, temperature 0,
`format` = JSON schema whose `category_id` is an enum of valid L2 ids + `UNMATCHED`). The output is validated with
Pydantic; malformed answers are retried with feedback, then the interaction is marked *failed* without touching the
taxonomy. Each intent has a normalized description, an L2, a verbatim customer quote (checked against the transcript:
*verbatim / approx. / not found*) and a one-sentence reasoning. `UNMATCHED` intents get no L1/L2 and are queued for review
— the system never invents L1/L2 categories.

**Matching.** Intent texts are embedded once (cache in SQLite). A candidate joins an existing L4 only if its cosine
similarity to that category's centroid exceeds the *match* threshold; the closest categories are stored as alternatives.
Everything else stays an open candidate (L1/L2 only).

**Batch refinement** (every `batch_size` interactions, default 25): per L2, open candidates are clustered with
HDBSCAN on cosine distance (agglomerative average-linkage fallback for < 5 points or all-noise results; every cluster
must meet the cohesion threshold, loose clusters are re-split). For each cluster the LLM sees the existing L3/L4 nodes
of that L2 and either maps the cluster to an existing L4 or proposes a new L4 under an existing or new L3 (ids are
enum-constrained). If the LLM maps a cluster to an existing L4 whose centroid is semantically distant (below the *match*
threshold), it is asked again without that category, and the alternative goes to human review. This keeps a generic
category from absorbing a related but different intent (e.g. roaming charges vs. duplicate charges). Proposals with a conflict (very similar centroid to an existing category, duplicate label elsewhere)
are never auto-accepted. Afterwards: re-matching of open candidates, overlap detection (L4 and L3 centroid similarity →
merge proposals), description refinement when a category's support doubles, split detection (separated sub-clusters).
At the end of a run, rare intents that never clustered are placed by the LLM (existing L4, new low-support L4 flagged for
review, or left unclassified for a human).

**Calibration.** On `qwen3-embedding:0.6b`, pairs of real extracted statements of the same intent have a median cosine of
≈0.85, while distinct intents in the same L2 have a median of ≈0.66 but their top 5 % reach ≈0.78. Embeddings alone
cannot separate near-synonyms, so they only auto-match at high similarity and the
LLM makes the semantic decisions at batch boundaries. Sensitivity presets (Settings) shift all thresholds.

**Governance.**
- New, non-conflicting L3/L4 nodes are auto-accepted when *Auto-accept* is on (default); otherwise they appear as dashed
  *proposed* nodes until approved. Merges and splits always require approval. Nothing is deleted: merged/split/retired
  nodes keep their id and history (toggle *Show merged & retired*).
- Every applied change bumps the taxonomy version and is recorded in `taxonomy_changes` (Sheet 4 of the export).
- Human-reviewed assignments (confirmed / corrected / unclassified) are never changed by AI or restructuring; when their
  category is merged/split/retired they are flagged for re-review instead. Unreviewed assignments are recalculated.
- Every assignment keeps its latest AI assignment (`ai_original`) and a full audit trail.
- No confidence percentages are shown. The UI shows cosine similarity (labelled as such), the method, and *Needs review*.

**Durability.** Each interaction's intents, assignments and status are committed in one transaction; each cluster decision
is committed separately. On restart, runs that were *running* become *interrupted* and half-processed interactions are
rolled back to *pending*, so **Resume** never processes an interaction twice. Embeddings are never recomputed for known texts.
Importing more data later and pressing Start processes only the new interactions and refines the existing structure.

## Import format

Canonical JSON (one object per conversation):

```json
[{"conversation_id": "TELCO-0001", "channel": "voice", "segment": "prepaid", "language": "en",
  "timestamp": "2026-10-20T10:00:00Z", "queue": "Prepaid Support",
  "turns": [{"speaker": "customer", "text": "I topped up yesterday, but the credit is still missing."},
            {"speaker": "agent", "text": "I can check the transaction for you."}]}]
```

- **CSV / Excel**: either one row per conversation with a `transcript` column (`Customer: … / Agent: …` lines) or one
  row per message (conversation id + speaker + text columns). Columns are auto-detected and can be re-mapped in the
  import dialog. Template: `backend/data/sample/import_template.csv`.
- **TXT**: each file is one interaction (optional separator to split one file into several).
- Missing metadata is allowed; missing IDs are generated; already-imported conversation IDs are skipped.
- The canonical structure mirrors what can be derived from Genesys Cloud conversation exports, so an API connector can
  be added later by producing the same records (no Genesys OAuth in this MVP).

## Synthetic dataset

`scripts/generate_sample_data.py` (seed `20261020`) produces 100 English conversations (4–12 turns) across prepaid voice,
postpaid voice, WhatsApp, web messaging and social media with 22 underlying intent types in a long-tail distribution
(11 occurrences down to 1), 14 multi-intent conversations, 6 deliberately ambiguous ones, 12 with small talk and several
near-synonym pairs (lost SIM / SIM swap / SIM activation, tariff upgrade / downgrade, roaming / overage / duplicate charges,
password reset / account locked). Labels live only in `sample_ground_truth.json`, which is read exclusively by the
Insights comparison (a test asserts that pipeline modules never reference it).

## Privacy & security

- Local-first: data is stored in `backend/var/intent_studio.db` on this computer. No cloud AI APIs, no telemetry, no
  third-party storage; fonts are bundled locally.
- **The configured Ollama server receives transcript text for inference.** If it runs on another machine (e.g. the
  gaming PC), transcripts travel over your network. Use synthetic data for demos; for real customer data use only an
  approved, secured network connection (e.g. VPN / encrypted tunnel) and an approved machine.
- Logs contain no transcript content; unhandled errors return only the exception type; Ollama errors never echo prompts.
- The web server binds to `127.0.0.1` by default (`INTENT_STUDIO_HOST`). `.env` and the database are git-ignored.

## What is (not) in Git

Committed: source code, the predefined taxonomy, the synthetic sample dataset and the tests.
Never committed (see `.gitignore`): `.env` (Ollama URL and model settings), the SQLite database in `backend/var/`
(transcripts, embeddings, reviews), exported result files, `node_modules/`, `.venv/` and build output.

After cloning on another computer:

```bash
git clone https://github.com/joe23byte/taxonomy-creator.git && cd taxonomy-creator
cp .env.example .env            # set OLLAMA_URL
cd backend && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cd ../frontend && npm install
```

The workspace (imports, taxonomy, reviews) lives only in the local database. To move it to another computer, copy
`backend/var/intent_studio.db` while the backend is stopped, or use the JSON export.

## Limitations

- 100 interactions are not enough to claim a complete taxonomy; the discovery curve shows saturation for this dataset only.
- Automatic L2 choice by the LLM can differ for borderline intents (e.g. data usage vs. mobile data); reviewers can correct it.
- One analysis job runs at a time; the app is single-user by design.
