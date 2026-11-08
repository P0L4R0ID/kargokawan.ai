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

Phase 2 adds optional OpenAI tool orchestration over the deterministic solver. Computed tool output remains authoritative; model-written prose is not displayed.

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


## Phase 2: AI Logistics Assistant

Install the updated requirements using the cloud commands above. Configure the
primary provider through secure environment settings:

- `AI_PROVIDER=deepseek`
- `DEEPSEEK_API_KEY`: enter a fresh key securely, never in chat or source files.
- `DEEPSEEK_MODEL=deepseek-flash` (default; override for an account-supported model).
- Permit outbound HTTPS to `api.deepseek.com`.

The OpenAI-compatible SDK uses `https://api.deepseek.com` and Chat Completions
function tools (`tools`, assistant `tool_calls`, and tool replies with `tool_call_id`).
Strict mode is not enabled: every argument is locally schema-validated. Model
availability is account-dependent; this default is user-requested, not live-verified.
Optional OpenAI mode uses `AI_PROVIDER=openai`, `OPENAI_API_KEY`, and
`OPENAI_MODEL` (default `gpt-4o-mini`). With no explicit provider, DeepSeek is the
default, except legacy installations with only an OpenAI key retain OpenAI mode.
No secrets are required for deterministic fallback. `.env.example` contains names
only; the app does not load `.env` files. Never send customer personal data: use
fictional/anonymized shipments, as requests/tool results go to the selected provider.

Click **Test AI connection** to make exactly one minimal API request using fictional
samples. Success requires a model-generated `inspect_orders` call with locally
validated arguments and actual execution of that KargoKawan tool; it is not just
an HTTP ping. No second API request sends the result back. The test never runs on
ordinary rerenders. The UI shows configured provider/model, connection result,
and the actual live/fallback mode of each assistant request. Key presence alone
does not prove live connectivity.

`agent.py` exposes six schema-validated tools: `inspect_orders`,
`inspect_shipping_options`, `optimise_shipments`, `explain_plan`,
`simulate_disruption`, and `compare_plans`. The LLM chooses tools and receives
computed results in a bounded loop. There are at most six calls, including rejected
calls, per request. API requests have a 12-second timeout and no retries; the loop
stops scheduling requests after 45 seconds. An in-flight tool may finish afterward;
the existing solver retains its 8-second limit per solve. No model-generated code
is executed. All prices and ETAs originate from the engine; cost differences are
arithmetic over engine totals. Explanations are templates plus engine assumptions.

The fallback recognizes optimisation/explanation requests, deadline questions,
shipping-option questions, named fictional-provider availability changes, and
requests such as `Change KK001 deadline to 3 days`. It is not general natural-language
understanding; unfamiliar requests show validated orders. Missing keys and API errors
use this fallback. Invalid model tool calls are visibly rejected. Tests mock the SDK
and make no paid calls. Live API operation has not been validated: no runtime key was configured and the cloud proxy denied the DeepSeek destination (HTTP 403).

### Demonstration with Malaysian sample orders

1. Ask `Optimise these orders and explain why this plan is cheaper.` Review the
   tool sequence, computed plan, baseline and engine assumptions.
2. Ask `Which shipments have the tightest deadlines?` The read-only result sorts
   the sample orders by deadline (the KL local shipments have two-day deadlines).
3. Ask `What if Demo Consolidated Freight is unavailable?` Compare the simulated
   before/after costs, provider sets, groups and per-order ETA/deadline slack.
4. Choose **Discard** to keep current state, or **Apply proposed change** to apply
   and replan. Changed inputs invalidate old approvals and require a fresh preview.
5. Ask `Change KK001 deadline to 3 days` for a deadline preview, then approve it
   and export the dashboard manifest.

Previews never modify current orders or availability. Only deadline and fictional
provider availability changes are supported; city/weight edits remain in the
validated shipment editor. Infeasible previews are rejected, not applied. Audit
history and proposals are session-local; no durable database or booking/payment
integration is included. The displayed assistant answer is computed structured data,
not free-form LLM prose. The existing optimization engine and its assumptions remain
unchanged. The main dashboard and assistant have separate plan views until an
approved disruption is applied; ordinary assistant optimisation is read-only.


### Provider reliability pass

On partial API failure, timeout or rejected tools, all partial computed results and
proposals are discarded. Trace entries are marked discarded/rejected without old
result payloads, then fallback operates on the unchanged input snapshot. Attempted
calls still count toward the shared six-call limit; if exhausted, a new request is
required. Invalid disruption arguments also clear earlier proposals. Approval
requires an unchanged orders/availability fingerprint. Raw provider errors and
credentials are never displayed. Provider selection does not enable real shipping.

Validation: 41 tests passed, including mocked DeepSeek/OpenAI SDK configuration,
tool protocol, timeout redaction, missing keys, partial-failure rollback, budget
exhaustion, approval/staleness, and click-only connection testing. The deterministic
engine remains unchanged. Live DeepSeek/model compatibility remains unverified
until a fresh secret and outbound access are configured. The public documentation
fetch was also blocked (HTTP 403); standard non-strict Chat Completions tool format
is used. Audit/proposals remain session-local and fallback uses limited matching.

## Real quote import (experimental)

The separate imported quote model in `quotes.py` accepts user-obtained carrier
quotations. Download its CSV header with `quotes.template()`. Each quote needs an
ID, source reference, retrieval and expiry times with time zones, five-digit
Malaysian postcodes, route cities and states, weight and dimension limits, a MYR
total, component charges, transit time, covered shipment IDs and conditions.
Multiple shipment IDs use semicolons. All prices use decimal arithmetic.

Imported quotations are **user supplied and not independently authenticated by
KargoKawan**. The optimiser uses only eligible, unexpired quotations matching the
shipment postcode, city, dimensions and deadline. Group discounts require an
explicit group quotation. Where complete quote coverage is absent, the result is
`NOT QUOTED / UNKNOWN`. The baseline uses eligible single-shipment quotations
from the same import. No booking or payment occurs.

Live carrier quoting remains disabled. `carrier_adapters.py` defines an adapter
boundary for EasyParcel and Lalamove, but no endpoint or authentication format
has been verified against official documentation. Configure and verify a carrier
account and its production or sandbox credentials before implementing a live
adapter. Sandbox responses must remain labelled sandbox test data.

### Imported quotation demo

1. Select **Imported quotations** below the simulated dashboard. The two price
   sources are kept separate. Enter each origin and destination as an exact
   five-digit postcode; leading zeros are required. **Load fictional demo
   postcodes** fills synthetic sample values for the 15 demo orders only.
2. Download the quotation CSV template. It contains these required columns:
   `quote_id,provider,service,currency,source_reference,retrieved_at,valid_until,origin_postcode,destination_postcode,origin_city,destination_city,origin_state,destination_state,physical_weight_kg,volumetric_weight_kg,max_weight_kg,max_length_cm,max_width_cm,max_height_cm,eligible,restrictions,transport_method,total_myr,tax_myr,surcharge_myr,handling_myr,last_mile_myr,transit_days,transit_guaranteed,shipment_ids,conditions`.
   Use `MYR`, ISO 8601 timestamps with time zones, `true`/`false` booleans,
   decimal MYR with at most two places, and semicolon-separated shipment IDs
   for an explicitly quoted group consignment. The provider's quote reference
   belongs in `source_reference`; the app does not authenticate it.
3. Upload user-obtained quotes and select **Plan with imported quotations**.
   Review supporting quote IDs, provider, service, amount, source reference and
   validity. The baseline uses only eligible individual quotes from the same
   upload. Missing coverage displays `NOT QUOTED / UNKNOWN`.
4. Select **Apply imported proposal** to enable the proposed CSV manifest, or
   **Discard imported proposal**. Changes to orders, uploaded quotes or provider
   availability invalidate a pending preview or approved manifest. Export does
   not book transportation or pay carriers.

The imported route model requires exact postcode and city matches. It does not
verify that a postcode belongs to a city or state, authenticate a user-uploaded
quote with a carrier, implement special service restrictions beyond the explicit
eligibility flag and size/weight/deadline limits, or infer group discounts.
Live EasyParcel and Lalamove adapters remain disabled pending documented API
configuration and verification. Tests use synthetic fixtures; no paid API calls.
Validation: **50 tests passed** and Streamlit health endpoint returned HTTP 200.
Streamlit AppTest cannot operate the file uploader directly; the UI interaction
test injects an uploaded CSV fixture and the parser is tested separately.

## Focused provider comparison

The separate EasyParcel and Lalamove CSV templates in
`data/focused/templates/` use the research quote schema. EasyParcel rows require
`transport_method=parcel_courier`; Lalamove rows require
`transport_method=multi_stop_vehicle` and ordered JSON `dropoff_locations` with
`shipment_id`, five-digit `postcode`, and `sequence` starting at 1. A complete
comparison requires one eligible courier quote per order and a single full vehicle
fare covering exactly the same orders. Capacity, pickup postcode, each destination
postcode, deadline, final MYR cost, included taxes/surcharges and expiry are
checked. Public starting prices, synthetic fixtures and incomplete prices are
shown in the review table but excluded from real comparisons. Unspecified
restrictions require review. Apply approves a comparison for review only; it
never books or pays for transport. Edited inputs clear the approval.

All three adapter interfaces (EasyParcel, Lalamove and Pos Malaysia) report
`NOT_CONNECTED`: no authorized credentials or verified endpoint configuration
are present, and no live call is made. This path does not replace the existing
single-destination imported quote optimizer. It evaluates the explicit
courier-versus-vehicle batch comparison separately from deterministic planning.

## Mixed-method quote optimization

The mixed-method view uses a bounded deterministic exact-cover solver over the
uploaded EasyParcel courier and Lalamove multi-stop quotes. At most 20 orders
and 500 quotes are accepted. Every selected quote covers an explicit subset;
every order must be covered once. Vehicle quotes retain their own complete
ordered stop list, capacity, dimensions, deadline, validity and full MYR fare.
No subset price is derived from a larger route. Ineligible, expired, public
reference and synthetic records are excluded. The standalone baseline uses only
the cheapest eligible courier quote for each order; it displays `NOT AVAILABLE`
when incomplete. Costs remain labelled USER_IMPORTED_UNVERIFIED unless provider
authentication is independently established. The plan requires preview and
explicit approval; changed orders, quotes or provider availability invalidate
approval. No shipment is booked. The simulated and prior imported-quote planners
remain separate.

## Delivery operations jobs

`delivery_operations.py` stores job state and audit events in local SQLite under
`.data/delivery_jobs.sqlite` (ignored by Git). It validates intake, proposes
plans from the mixed-method quote solver, requires explicit approval, exports
an order-level handoff manifest, and records externally confirmed booking,
transit and delivery only with user-supplied evidence. Booked jobs cannot be
silently replanned. The operations screen also lists missing intake actions and
lifecycle status counts. See `docs/operations_demo_script.md` for the 2–3 minute
walkthrough. The free-text goal field does not create orders or invent details.
No live booking, payment or tracking connector is implemented.

## Integrated operations and competition demo

`feature/integrated-operations` preserves the synthetic competition demo and
persistent SQLite delivery jobs. See `docs/integrated_demo_script.md` for the
single 2–3 minute walkthrough. Synthetic demo quotes remain isolated from real
jobs. A real manually imported mixed quote plan can seed a delivery job only
after quote-plan approval, complete recipient intake and matching order IDs; the
job then requires its own explicit approval. Source labels on manual quotes are
not independent provider authentication. The handoff creates no booking.

## Guided conversational intake

Use **Tell KargoKawan what you need delivered** to enter one line per explicit
order, for example: `Order SME001: from Kuala Lumpur 50000 to Kuching 93000, 2 kg,
30x20x10 cm, within 7 days, recipient Customer A; budget RM50`. Select
**Extract explicit order details**, review the editable draft and answer its
focused missing-field questions. The same editor accepts the operations sample
CSV upload, so incomplete rows can be corrected there. Select **Confirm corrected
draft and create job** only after validation. The deterministic parser recognizes
labeled facts; it does not claim general language understanding or fill missing
customer details. A user-stated budget is displayed for review, not automatically
used to invent a carrier quote. Collect complete EasyParcel and Lalamove quote
evidence next. A complete intake is ready for planning, not booking. Live carrier
rates, tracking and booking remain unavailable.

## Guided quote collection

After creating a complete delivery job, use **Collect real shipping quotations**
to download a minimal quote-request sheet without recipient names. It lists the
package facts needed for individual EasyParcel courier requests and possible
same-region Lalamove multi-stop request candidates. A candidate is never a
claim that a vehicle is available. Cross-sea groupings are not proposed as one
road route. Record an actual provider quote in the form, review missing fields,
correct the draft, and save it. Both providers remain `NOT_CONNECTED`; the form
stores user evidence as `USER_IMPORTED_UNVERIFIED`. Provider-specific CSV uploads
remain available. The progress table shows order-level courier coverage,
complete vehicle subsets and unresolved quote requests. A quote-backed plan must
be previewed and approved, then sent to a persistent delivery job for a second
approval. No booking, dispatch, payment or live tracking occurs.

## Simplified quote entry

Open **Collect real shipping quotations** and choose an existing delivery job.
For an EasyParcel parcel quote, choose one order; its pickup and destination
postcodes, weight and package dimensions appear automatically. Vehicle-only
fields stay hidden. For Lalamove, choose a possible same-region request group,
select the covered orders and edit the ordered stop table. The app builds the
stop JSON internally. A request candidate does not prove Lalamove serves the
route.

Enter the actual service, full MYR amount, charge treatment, transit estimate,
conditions, evidence reference and expiry using Malaysia-local date/time
controls. Order dimensions count as quoted eligibility only after you confirm
the provider accepted them. Capacity and route sequence also require provider
confirmation. Tax and surcharge treatment start as `UNKNOWN`. Select **Review
quote draft**; the checklist shows what is missing. Correct the form and review
again, then save the quote. Manual evidence remains `USER_IMPORTED_UNVERIFIED`.
CSV import, the existing solver, both demos and the separate job approval gate
remain available. No booking or live provider API call is made.
