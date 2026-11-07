# KargoKawan AI — Codex instructions

This repository is a **36-hour competition proof of concept** for an autonomous, nationwide Malaysian SME logistics decision agent. Prioritise a reliable end-to-end demo over feature sprawl.

## Commands
- Install: `bash scripts/setup.sh`
- Unit tests: `python -m pytest -q`
- Start demo: `streamlit run app.py --server.address 0.0.0.0 --server.port 8501`

## Requirements
- Keep simulated carrier names and shipping rates explicitly labeled **fictional** across UI, tests and docs. Never represent model outputs as genuine courier quotations or guaranteed savings.
- Support any route among configured Malaysian cities; do not assume Peninsular-East Malaysia is the only shipment pattern.
- Compare standalone parcels, eligible same-city multi-stop, and eligible consolidated freight; charge for handling and last mile as assumptions where applicable.
- Preserve validation for unique orders, positive dimensions and weights, and whole-number positive deadlines.
- Never merge different delivery destination cities into a freight consignment without modelling a real supported onward distribution method.
- Use deterministic Python for cost, constraints and optimization; an LLM agent may call these tools but must not invent prices, routes or ETAs.
- Do not book transportation, send payments, upload personal information, or send external messages without explicit user approval and genuine supported integration.
- Every optimization plan must cover every order exactly once, meet its deadline, and provide an audit trail.
- Prefer adding tests before changing the optimization engine.

## Definition of done for v1
A user can import CSV shipment orders, run the planner, view standalone vs optimized simulated costs, change a delivery deadline or disable a provider, see a newly computed plan with an audit trail, and export a CSV manifest.

## Recommended next improvements
1. Add structured `AgentEvent` / decision history persisted in SQLite.
2. Show **why** a shipping option was chosen, rejected or infeasible.
3. Add a real quote-input CSV (user-supplied, not scraped).
4. Improve the same-city multi-stop model so it uses actual pickup/drop-off locations and route distance when available.
5. Only then add a tool-calling LLM for intent and exception handling, keeping the solver authoritative.
