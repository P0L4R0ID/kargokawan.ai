# KargoKawan AI — 36-hour MVP

**Goal:** Nationwide multi-order logistics decision agent for Malaysian SMEs.

This proof-of-concept autonomously validates shipment data, creates permitted individual and grouped shipping strategies, solves a minimum-cost set-partition optimisation problem, and replans when orders, deadlines, or carrier availability change.

**Important:** All providers, cost curves, transit times, limits, and freight networks are fictional. Output is a *proposal*, not a booking or confirmed real-world saving.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Demo walkthrough (2 minutes)

1. Click **Run autonomous planning** with 15 sample orders across KL, Penang, Johor Bahru, Kota Kinabalu, Kuching and Sandakan.
2. Show the independent-shipment baseline versus selected multi-stop / consolidation plans, and download the manifest.
3. Change `KK001` deadline from `10` to `3` days. Click run; watch the route assignment and total change.
4. Simulate another disruption by disabling `Demo Consolidated Freight`; rerun and inspect the new plan and audit trail.

## Input CSV schema

`order_id,origin,destination,weight_kg,length_cm,width_cm,height_cm,deadline_days`

City names are listed in `engine.py` and the app. Deadline days are integers from the current planning date.

## Architecture

- **Validation tool**: rejects unsupported locations and invalid order data.
- **Option generation tool**: models eligible economy/express/freight options, chargeable volumetric weight and possible groupings.
- **Optimisation tool**: uses SciPy Mixed Integer Linear Programming to select disjoint groups that cover every order once and minimise assumed total cost under deadlines.
- **Policy agent/orchestrator**: triggers these tools, tracks the decision trace, and automatically replans after simulated events.
- **Review gate**: exports a proposed manifest; cannot purchase transportation.

This is a transparent decision/optimisation agent rather than an LLM-powered chatbot. An LLM can later add natural-language command interpretation, but cannot replace deterministic cost calculations.

## Explicit limitations

- Consolidation only groups **same-origin and same-destination-city** orders. Do not group separate customer destinations if there is no legitimate distribution network.
- Same-city multi-stop vans are assumed only when a source and destination are in the same city.
- Actual quotes, public road/sea network, capacity, prohibited goods, insurance, fuel surcharges, taxes and booking API permissions are not verified.
- Do not claim a certain percentage saving unless tested with real anonymised SME orders and real carrier quotations.

## GitHub + Codex cloud workflow

1. Create a private GitHub repository called `kargokawan-ai` and upload/commit this project at its root.
2. In Codex, choose the GitHub-connected repository and create a cloud environment.
3. Set environment setup command to `bash scripts/setup.sh` (or install `requirements.txt` and `requirements-dev.txt`).
4. Ask Codex to run `python -m pytest -q` and implement a specific task following `AGENTS.md`.
5. Start Streamlit on port 8501 for a preview when the cloud interface supports port forwarding.

No API key is necessary for the initial optimizer. All quote data is fabricated for demonstration.

## Codex cloud dashboard workflow

From the existing checkout (no additional worktree needed):

```bash
cd /workspace/kargokawan.ai
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Use the sample CSV download as the import template. Required columns are
`order_id,origin,destination,weight_kg,length_cm,width_cm,height_cm,deadline_days`.
Up to 20 orders across the 12 configured Malaysian cities are supported.
Click **Plan shipments** once; subsequent committed table edits (including deadlines)
and fictional provider availability changes automatically replan. Invalid or
infeasible changes remove the current manifest until corrected. CSV imports are
applied once per file content; invalid imports retain existing orders.

The dashboard includes selected strategies, a standalone cost comparison,
per-group assumptions, timestamped decision history with input snapshots, and
CSV manifest export explicitly labelled simulated/fictional. All providers,
rates and ETAs are fictional; no bookings, payments or external carrier calls occur.

Limitations: audit history is in Streamlit session memory and is lost when the
session is reset; it is not a durable compliance log. ETAs are model assumptions,
not live tracking. The existing solver retains its 8-second and 1% gap limits;
results are feasible plans, not guarantees of exact optimality or real savings.
Explanations describe deterministic constraints and selected groups, not a full
counterfactual analysis of every rejected candidate. Dependencies have minimum
versions rather than a reproducible lockfile. The optimization engine is unchanged.
