# Orders-first browser acceptance checklist

At **1366px laptop width** and **375px phone width**, check:

- [ ] Landing screen shows KargoKawan, five fictional order cards and compact demo disclosure. No recommendation, cost, saving or van assignment appears before planning.
- [ ] Pickup and destination counts match the validated order records. The complete evidence and deadline controls are expandable and keyboard reachable.
- [ ] **Find the best delivery plan** is the one dominant action. It advances to Plan and triggers the optimiser; plain reruns on Orders do not.
- [ ] Plan cards show method, covered orders, cost and deadline context without horizontal scrolling or repeated city names. Technical quote IDs, exclusions, provenance and solver status remain under **How this was calculated**.
- [ ] **Review this delivery plan** opens a distinct approval step. No manifest exists until **Approve this plan** succeeds. **Change plan** discards without approval.
- [ ] Prepare shows the five-row NOT A BOOKING manifest and fictional preparation marker. No booking, payment, dispatch or tracking claim appears.
- [ ] **Simulate van unavailable** clears approval and preparation, explains old/new valid assumed totals and requires a fresh review. **Restore van** works too.
- [ ] An impossible FEST004 deadline identifies the uncovered order and offers **Review deliveries** without inventing a saving.
- [ ] **Reset demo to orders** clears the plan, approval and disruption state, but leaves five validated orders visible.
- [ ] Private Pilot and Advanced tools are secondary and remain functional; fictional data never appears in private pilot jobs.
- [ ] Keyboard focus, contrast, text wrapping, card spacing and touch targets are usable at both widths.

Streamlit AppTest validates state and actions, but not screen-reader output, actual keyboard focus order, touch targets or pixel-level phone layout. Those checks remain manual before deploying this branch.
