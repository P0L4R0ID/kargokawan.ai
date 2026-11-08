# Guided quotation collection demo (about 2 minutes)

1. In **Tell KargoKawan what you need delivered**, enter explicit order lines or import `data/samples/malaysia_sme_5_orders.csv` through **Import delivery operations CSV**. Correct any missing fields and confirm the draft as a delivery job. Show the job ID and checklist.
2. Scroll to **Collect real shipping quotations**. Download the minimal quote-request CSV: it contains order IDs, postcodes, dimensions, weights and deadlines, with no recipient names. Show the possible same-region multi-stop request candidates. They are requests for evidence, not claimed Lalamove service availability.
3. Enter a manually obtained EasyParcel courier or Lalamove multi-stop quote. Leave tax treatment or expiry blank to show `INCOMPLETE` or `NEEDS_REVIEW`; correct the form and review again. No price is invented. Alternatively upload the existing provider-specific CSV.
4. Show the progress table: eligible courier quote IDs by order, complete vehicle subsets, missing quote requests and plan readiness. Only complete, compatible quotations can feed the mixed-method planner.
5. Preview and approve a complete quote-backed plan. Send it to the delivery job and show that the job still needs separate approval. The manifest is a proposal; booking and tracking require external confirmation evidence.

No live provider API is connected. Manual quotes remain `USER_IMPORTED_UNVERIFIED`, and synthetic demo prices remain separate.
