# Restricted pilot identity and job API

The public fictional demo remains at `https://kargokawan.streamlit.app`. Its demo jobs use disposable session-scoped SQLite and are **not** a real customer workspace. The separate Render backend is reported at `https://kargokawan-oauth.onrender.com`; EasyParcel's registered callback remains `https://kargokawan-oauth.onrender.com/oauth/easyparcel/callback`. This branch was not deployed by Codex. No live EasyParcel login, quotation or booking was performed.

## What is implemented

Streamlit has a separate **Authenticated pilot operations** section. When a trusted OIDC provider is configured, `st.login()` signs in the operator. The UI checks an exact allowlisted `sub` and session expiry for its display gate. It takes only the OIDC **ID token** from `st.user.tokens["id"]` in server-side Python and sends it over HTTPS in an Authorization header to Render; it never puts that token in a widget, URL, or browser JavaScript. Render independently checks the token's RS256 signature using the configured HTTPS JWKS, issuer, audience, issue/expiry times and exact allowlisted subject **on every request**. A name, email, Streamlit session ID, browser cookie or job ID alone is never accepted as operator identity. Streamlit's [OIDC and token exposure documentation](https://docs.streamlit.io/develop/concepts/connections/authentication) describes `st.login`, `st.user` and `expose_tokens = "id"`. The ID token audience on Render must match the Streamlit OIDC client ID.

The backend exposes only authenticated `/pilot/status`, draft jobs and manual/public-reference quote drafts. Job and quote SQL queries check the verified owner. Order POST/PUT validates the established 11 intake fields, five-digit string postcodes, positive weight/dimensions, unique IDs and deadlines. Quote POST/PUT accepts only the existing reviewed import fields and `PUBLIC_REFERENCE` or `USER_IMPORTED_UNVERIFIED`; it cannot accept a user-claimed authenticated or synthetic quote. There is **no** booking, payment, shipment creation, provider token or quotation retrieval route. POST requests require an idempotency key; PUT requests require the current numeric version to reject stale writes. Correcting orders clears old quote drafts. No cookie-based cross-origin API authentication or CORS access is provided: the Streamlit server makes the HTTPS calls itself.

The production EasyParcel OAuth start and callback **still return 403**. The current EasyParcel Open API [account-information example](https://github.com/easyparcel/OpenAPI/blob/main/source/includes/2026-09/_get_account_info.md) shows account name/type and addresses, but no documented immutable account ID in that response. A name is not enough to prove the expected provider account. The existing mock-only callback exercises state, CSRF, cookie binding, exact redirect, encrypted token storage and code exchange, but it is not a live account link. Do not show EasyParcel CONNECTED until an authorised handshake and reliable provider-account check succeed.

## Exact configuration required, not yet supplied

**Streamlit Community Cloud secrets** (enter in its Secrets settings, never commit a secrets file):

```toml
PILOT_OPERATOR_SUB = "<exact operator OIDC subject>"

[auth]
redirect_uri = "https://kargokawan.streamlit.app/oauth2callback"
cookie_secret = "<strong random secret>"
client_id = "<OIDC provider client ID>"
client_secret = "<OIDC provider client secret>"
server_metadata_url = "<provider HTTPS OIDC discovery URL>"
expose_tokens = "id"
```

Register `https://kargokawan.streamlit.app/oauth2callback` with the **operator identity provider**. That is different from the EasyParcel callback on Render. Choose and configure a real trusted OIDC provider; no provider or operator subject was invented in this branch. Streamlit's `st.user` expiration is checked in the UI, and Render verifies the signed token again on each request.

**Render secret environment variables** for the pilot job API:

```text
PILOT_ENABLED=1
PILOT_OIDC_ISSUER=<exact HTTPS OIDC issuer>
PILOT_OIDC_AUDIENCE=<same OIDC client ID used by Streamlit>
PILOT_OIDC_SUBJECT=<exact allowlisted operator subject>
PILOT_OIDC_JWKS_URL=<trusted HTTPS JWKS URL from provider discovery>
PILOT_DB_BACKEND=postgres
PILOT_DATABASE_URL=<Render-only session-pooler connection string>
PILOT_DATABASE_CA_FILE=<Render secret-file path for Supabase CA>
```

The optional PostgreSQL backend can run on Render Free with a separately configured Supabase Free database; see [supabase_pilot_setup.md](supabase_pilot_setup.md) for private-schema provisioning, TLS verification, connection pooling, backup and pause caveats. Missing PostgreSQL settings or connectivity return 503; no SQLite fallback occurs. The former `PILOT_DB_BACKEND=sqlite` path still requires an actual mounted persistent disk under `/var/data` and is unsuitable for Render Free. Neither option persists EasyParcel OAuth tokens on Render Free.

`Dockerfile.oauth` already copies the pilot API and store. Deploy this reviewed branch to the existing Render Docker web service only after confirming the disk and secrets. Keep the EasyParcel OAuth credentials and callback settings separate; this branch does not require them for `/pilot/status` or draft jobs. The existing health endpoint should return 200; without a valid operator token `/pilot/status` returns 401, and with missing storage it returns 503. After sign-in and database verification, `/pilot/status` returns `READY` and `easyparcel_oauth: NOT_CONNECTED`.

## Remaining release blockers

1. Select a real OIDC provider, configure its Streamlit and Render settings, and establish the exact operator subject. Test the signed ID-token bridge with that provider. Mocked tests do not prove the IdP configuration works.
2. For draft jobs, provision and independently verify the restricted Supabase PostgreSQL backend or a paid Render persistent disk. The free Render filesystem cannot persist OAuth tokens safely; EasyParcel linking stays disabled.
3. Review actual public deployment and job migration. The existing demo operations still live on disposable local disk and are not migrated into the owner-scoped pilot API. The pilot UI creates and edits private job drafts and quote drafts, but does not yet hand them to the optimiser or approval/booking workflow.
4. Confirm a provider-documented stable EasyParcel account identifier and a safe account verification call before binding any OAuth token to this operator. Keep OAuth start/callback disabled until then, with explicit consent and revocation behaviour tested.
5. Complete a security review of OIDC metadata/JWKS configuration, token lifetime, request limits, audit logging without PII, database backups and incident procedures before admitting real customer orders.

To disable pilot access immediately, remove `PILOT_ENABLED` on Render and rotate/revoke the operator IdP session as needed. To disable EasyParcel, its OAuth routes already return 403; revoke credentials in Developer Hub if any are later issued. No production OAuth activation is part of this branch.
