# EasyParcel Open API 2026-09: restricted OAuth test

Contract: the user-supplied *EasyParcel API Reference.pdf*, version 2026-09.
OAuth is on pp. 28–32, standard quotations on pp. 39–43, and on-demand
quotations on pp. 80–85. The PDF itself is not committed. No real provider call
was made during development.

The existing Google OIDC pilot identity is independently verified on Render.
Only the allowlisted operator can create a five-minute, one-time connection
ticket. The browser then visits the backend, which sets a Secure, HttpOnly,
SameSite=Lax cookie and a ten-minute, one-time OAuth state. The backend rejects
wrong cookies, expired/replayed tickets or state, and wrong operators.

The default authorization host is `https://api.easyparcel.com/oauth/login`.
The PDF's Postman variant, `https://developer.easyparcel.com/oauth/login`, is
available only through a **separate fresh attempt**. Both are fixed allowlisted
hosts and use the exact registered callback:
`https://kargokawan-oauth.onrender.com/oauth/easyparcel/callback`.
The server exchanges codes with HTTP Basic at
`https://api.easyparcel.com/oauth/token`, validates token lifetimes, and stores
encrypted access/refresh tokens under the verified operator subject in private
PostgreSQL. Refresh is server-side. Tokens and codes never return to Streamlit.

The first **Check one fictional EasyParcel sample rate** action posts only the
PDF's fictional Penang sample: `10150` to `11950`, `MY-07` to `MY-07`, 1.5 kg,
5×5×5 cm. No private job or customer data is sent. The server permits at most
one check per operator per 30 seconds, uses a 12-second timeout, and makes no
automatic retries. The parser preserves courier/service names and IDs, MYR
total, EasyParcel seller-payable amount, cost breakdown, coupon details,
optional duration, request ID and collection time. Missing fields stay unknown.
Results remain review-only and cannot enter the optimiser or approval workflow.

The PDF says the selected account determines Sandbox or Live, but its token
example and successful standard quotation example do not attest account ID or
environment. The UI therefore reports `UNKNOWN` after OAuth. If a provider
response includes the documented `rate_limit.limit_set` value `sandbox` or
`live`, that is recorded as provider evidence; otherwise it remains `UNKNOWN`.
An OAuth success or operator-selected host is never proof of Sandbox. A
connection identified as Live is blocked from further sample checks. The
first check is fictional and read-only even while environment is unknown.
Exact account ID verification remains a limitation.

The PDF's on-demand section says `/ondemand/quotation`, while its Python
example says `/ondemand/quotations`. On-demand HTTP calls stay disabled; the
code can validate exact coordinates without guessing from postcodes. Booking,
submission, payment, cancellation and dispatch are absent.

## Deployment configuration

Deploy this branch to the existing Render OAuth backend with `Dockerfile.oauth`
and persistent private Supabase PostgreSQL. Set these **Render-only** variables:

| Name | Required value |
| --- | --- |
| `PILOT_ENABLED` | `1` |
| `PILOT_DB_BACKEND` | `postgres` |
| `PILOT_DATABASE_URL`, `PILOT_DATABASE_CA_FILE` | Existing persistent Supabase connection and mounted trusted CA path |
| `PILOT_OIDC_ISSUER`, `PILOT_OIDC_AUDIENCE`, `PILOT_OIDC_SUBJECT`, `PILOT_OIDC_JWKS_URL` | Existing verified Google pilot identity configuration |
| `EASYPARCEL_OAUTH_ENABLED` | `1` only for this restricted test |
| `EASYPARCEL_OAUTH_CLIENT_ID` | Developer Hub client ID |
| `EASYPARCEL_OAUTH_CLIENT_SECRET` | Rotated private Developer Hub secret |
| `EASYPARCEL_OAUTH_REDIRECT_URI` | `https://kargokawan-oauth.onrender.com/oauth/easyparcel/callback` exactly |
| `EASYPARCEL_OAUTH_FERNET_KEY` | Stable private Fernet key, generated outside Git |

Generate the Fernet key privately with
`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
Keep it stable across restarts. The old `EASYPARCEL_OAUTH_DB` SQLite setting
belongs only to the legacy isolated test flow and is not used in production.
Without persistent PostgreSQL or complete configuration, OAuth remains
unavailable. Do not place provider secrets in Streamlit Secrets.

Set the private Streamlit pilot to this same branch while preserving its
existing Google OIDC Secrets and `PILOT_OPERATOR_SUB`. Its backend URL is fixed
to `https://kargokawan-oauth.onrender.com` in `pilot_client.py`.

## First manual browser test

1. After choosing to deploy, check backend `/health` is 200 and anonymous
   `/pilot/status` is 401. Sign into the private Streamlit pilot as the
   allowlisted Google operator.
2. In **EasyParcel connection**, choose the default `api.easyparcel.com` host.
   Click **Prepare EasyParcel Connect**, then the generated one-time link.
3. Select the EasyParcel **Sandbox/Demo account** and authorize. If that host
   fails, return to the pilot, select the developer-host variant and prepare
   a **new** link. Never reuse the old ticket.
4. Return to the pilot and inspect connection and environment. If environment
   says `UNKNOWN`, do not claim Sandbox verification.
5. Click **Check one fictional EasyParcel sample rate** once. Review total MYR,
   seller payable, optional transit text and source. It is neither a booking
   nor a planner-eligible quote.

No live OAuth handshake, Sandbox account identity or real quotation has been
verified by mocked development tests. Those require the operator's explicit
browser action after deployment.
