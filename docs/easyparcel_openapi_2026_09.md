# EasyParcel Open API 2026-09: read-only integration boundary

The contract used here is the user-supplied *EasyParcel API Reference.pdf*, version
2026-09 (OAuth pp. 28–31, standard quotations pp. 39–43, on-demand pp. 80–85).
The PDF is not committed to the repository. No live EasyParcel request was made
while developing this branch.

## Implemented

- `easyparcel_openapi.py` builds the documented JSON `shipment` array for one to
  five existing orders. Exact sender and receiver `MY-##` subdivision codes must
  be supplied by the operator; postcodes remain five-digit strings, including leading zeroes.
  Dimensions are sent only when present. No state or dimensions are inferred.
- Its transport-injected standard quotation client makes one bounded POST to
  `/open_api/2026-09/shipment/quotations`. It has no retry or shipment-writing
  method. HTTP errors, 429, malformed responses, missing MYR totals and
  individual shipment errors are handled separately.
- Observations retain service/courier IDs and names, total and EasyParcel-payable
  amounts, shipping/tax/feature/BYOC components, coupon discount, delivery text,
  collection time and provider request ID. A BYOC `seller_payable_amount` is **not**
  the full shipping cost. Unknown transit and expiry remain unknown.
- Private Pilot exposes an authenticated, owner-scoped request path and order
  selection. The server reloads selected orders from the private job; the browser
  cannot provide alternate order data. Observations are review-only and are not
  stored as planner-eligible quotes. Existing manual quotes and approvals are
  unchanged. Public fictional demos never call this path.
- Exact ordered on-demand coordinates can be validated, but on-demand HTTP calls
  are disabled. Postcodes are never converted to guessed coordinates.

## Deliberately disabled

The existing production `/oauth/easyparcel/start` and callback still return 403.
Their older isolated test flow stores tokens by browser session in SQLite and is
**not** suitable for the owner-scoped PostgreSQL pilot. The production quote
service is not registered, so the Private Pilot returns `NOT_CONNECTED` even
when a user clicks **Check EasyParcel rates**. No token, authorization code or
client secret is sent to Streamlit. There is no API credential or secret in this
branch. The legacy Individual API key adapter remains separate.

The PDF identifies `https://api.easyparcel.com/oauth/login` as the authorization
URL (p. 28), while its Postman setup says
`https://developer.easyparcel.com/oauth/login` (p. 32). The on-demand endpoint
description says `/ondemand/quotation` (p. 80), while the Python example says
`/ondemand/quotations` (p. 85). Neither discrepancy was resolved through an
authorized sandbox response. Production OAuth and on-demand calls must stay
disabled until they are verified; no path is chosen by guesswork.

The PDF says the account selected during OAuth determines Sandbox or Live.
The standard successful quotation response does not provide an attested account
environment, and the token example does not contain an account ID or environment.
Accordingly the UI reports `UNKNOWN`; an operator's chosen label must not be
presented as provider verification. A server-side owner-bound token store, exact
account verification, environment attestation and safe refresh flow are required
before enabling live requests. These must use persistent PostgreSQL and encrypted
tokens; Render's ephemeral filesystem and Streamlit session state are unsuitable.

## Safe next manual step

Obtain an authorized Sandbox account and ask EasyParcel to confirm the canonical
OAuth authorization host, on-demand path/multi-stop support, and a documented
read-only way to verify the authorized account ID and Sandbox/Live environment.
Then implement and test the owner-scoped PostgreSQL OAuth link and refresh flow
with mocks before making a single operator-triggered Sandbox quotation request.
Do not enable booking, submission, payment, cancellation or dispatch endpoints.
