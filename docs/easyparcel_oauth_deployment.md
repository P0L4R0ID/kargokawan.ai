# EasyParcel Open API OAuth deployment readiness

## Verified provider contract

The [EasyParcel Open API authentication reference](https://easyparcel.github.io/OpenAPI/?php#oauth-authentications) (current 2026-09 source) documents an **Authorization Code** flow: send `client_id`, `redirect_uri` and `state` to `https://api.easyparcel.com/oauth/login`; receive `code` and `state` at the registered redirect URI; POST `grant_type=authorization_code`, the same `redirect_uri` and `code` to `https://api.easyparcel.com/oauth/token` with HTTP Basic `client_id:client_secret`. The same token endpoint accepts `grant_type=refresh_token` with a refresh token. The response may contain access/refresh tokens and expiry values. The [Developer Hub guide](https://easyparcel.github.io/OpenAPI/?php#get-app-client-credentials) says to register an application with a redirect URI and obtain its client ID and secret. Its Postman collection leaves scope blank; this implementation requests no optional scopes. Provider approval and actual granted permissions remain unverified. No provider handshake has been performed.

The provider source also uses a different login host in one Postman walkthrough. This backend follows the explicit OAuth authentication reference (`api.easyparcel.com/oauth/login`). Confirm the host against your Developer Hub app before going live. Do not replace it based on a guessed endpoint.

## Architecture decision

Use a **separate HTTPS WSGI callback service**, not a Streamlit Community Cloud query-parameter callback. Streamlit can read query parameters, but `st.session_state` is tied to its WebSocket session; a provider browser redirect cannot be relied on to resume the same session for CSRF validation or secure token exchange. Community Cloud also does not expose a custom `/oauth/easyparcel/callback` server route in this project. The callback service validates a random state against a short-lived server-side record bound to a Secure, HttpOnly, SameSite=Lax browser cookie. It consumes the state once, exchanges the code on the server, and encrypts the token response before storing it in SQLite. It never sends tokens to the browser. Token refresh is implemented as a server-only function and is not yet scheduled or wired into quotations.

This is **callback readiness, not an integrated Open API connection**. The Streamlit quotation UI still uses the separate legacy Individual API key adapter and manual evidence entry. The callback service has no user-account bridge into Streamlit, so an OAuth token cannot yet be used for quote retrieval. Do not point real users to the OAuth start route until an authenticated account-linking design and access controls are added.

## Hosting and values

Deploy the Streamlit app to a stable HTTPS hostname. After deployment, open its actual browser URL. That complete origin is the **Platform URL** to register in Developer Hub; the GitHub repository URL and local `localhost:8501` are not substitutes. Deploy `Dockerfile.oauth` as a separate private-backed HTTPS web service, with a persistent volume mounted for its SQLite file. The **Allowed Redirect URI** is the backend's exact public HTTPS URL plus `/oauth/easyparcel/callback`, for example `https://YOUR-BACKEND-HOST/oauth/easyparcel/callback`. The hostname here is a placeholder, not a claimed deployment. Register that exact string in Developer Hub and set it as `EASYPARCEL_OAUTH_REDIRECT_URI`.

Set these **server-side only** on the callback host:

- `EASYPARCEL_OAUTH_CLIENT_ID` and `EASYPARCEL_OAUTH_CLIENT_SECRET`: from your authorised Developer Hub app.
- `EASYPARCEL_OAUTH_REDIRECT_URI`: exact registered HTTPS callback URL.
- `EASYPARCEL_OAUTH_DB`: absolute path on a persistent, access-controlled volume. Run one worker/replica for this SQLite setup.
- `EASYPARCEL_OAUTH_FERNET_KEY`: a stable Fernet encryption key generated once with `Fernet.generate_key()` and held in the host's secret manager. Losing or rotating it without migration makes stored tokens unreadable.

`Dockerfile.oauth` runs the WSGI callback on port 8080 by default; the host must terminate HTTPS and forward requests without changing the callback path. The health route is `/health`. Restrict access to the start route until the account-linking design is complete. Do not put credentials in Streamlit widgets, `.env` committed to Git, screenshots, or logs. Protect the persistent volume and backups. Access logs must not record callback query strings containing authorization codes.

## Manual deployment sequence

1. Deploy Streamlit and copy its actual HTTPS origin for **Platform URL**.
2. Deploy the callback container on a separate HTTPS hostname with a persistent volume and the five secrets above, using a provisional exact redirect URI based on that hostname.
3. Register the app in EasyParcel Developer Hub with the Streamlit Platform URL and exact callback Allowed Redirect URI; copy the issued client credentials into the backend secret manager.
4. Verify `/health` and exact HTTPS callback routing, then conduct a controlled sandbox OAuth handshake with an authorised EasyParcel account. Inspect server-side status only; never copy tokens into the UI.
5. Build and review a secure Streamlit-to-backend account-linking and Open API quote adapter before enabling OAuth-based quotation retrieval.

Automated tests use mocked token responses and do not prove EasyParcel authentication, refresh behaviour against the provider, or deployment compatibility. The existing Individual API key and manual quotation flows remain the usable paths.
