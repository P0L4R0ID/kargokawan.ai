# Codex cloud environment

Select **this GitHub repository** as the Codex environment source.

Recommended environment setup command:

```bash
bash scripts/setup.sh
```

No secrets are required for the deterministic MVP. For tasks adding an LLM, configure the API key as a Codex environment secret, never commit `.env` or tokens.

To preview the app in a cloud terminal:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Expose or forward port 8501 using the Codex environment's port preview controls, if available.

Run `python -m pytest -q` after changes. All shipping prices/providers are demo assumptions.
