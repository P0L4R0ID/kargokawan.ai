# KargoKawan architecture and limits

The original `engine.py` contains a deterministic simulated Malaysian shipment
optimizer. It is unchanged. `agent.py` orchestrates read-only planning and
preview tools; it cannot book transportation. `quotes.py` validates a separate
31-field user-imported quotation path. `hybrid_quotes.py` classifies incomplete
research observations, while `focused_quotes.py` handles EasyParcel and Lalamove
manual quote evidence. Live adapters report `NOT_CONNECTED`.

`mixed_method.py` uses SciPy MILP to choose disjoint eligible quotations that
cover each order exactly once. It checks solver termination, numerical bounds,
integrality and shipment coverage. `READY` means the solver proved optimality;
`SOLVER LIMITED` means it returned a feasible plan without that proof. Values
and source references come only from supplied quotes; totals use Decimal.
At most 20 orders and 500 quotes are evaluated. Expired, incomplete, public
reference and synthetic quotes are excluded from real optimization. The demo
explicitly enables synthetic quotes in an isolated mode.

Every plan is a proposal. Approval recomputes eligibility and rejects changed
orders, quotes or provider availability. The demo disruption clears prior
approval. There are no booking, payment or carrier API calls. Manual labels
claiming live authentication do not by themselves prove provider identity.
Current live EasyParcel, Lalamove and Pos Malaysia integration is planned,
not implemented. Real carrier data and independently verified quotes remain
necessary before making a real savings claim.
