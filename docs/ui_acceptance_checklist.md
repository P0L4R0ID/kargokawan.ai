# Orders-first browser acceptance checklist

At **1366px laptop width** and **375px phone width**, check:

- [ ] Landing screen shows KargoKawan, five fictional order cards and compact demo disclosure. No recommendation, cost, saving or van assignment appears before planning.
- [ ] Pickup and destination counts match the validated order records. The complete evidence and deadline controls are expandable and keyboard reachable.
- [ ] **Find the best delivery plan** is the one dominant action. It advances to Plan and triggers the optimiser; plain reruns on Orders do not.
- [ ] Plan leads with cost, then shows any selected van before courier cards, with method, covered orders and deadline context without horizontal scrolling or repeated city names. Technical quote IDs, exclusions, provenance and solver status remain under **How this was calculated**.
- [ ] **Review this delivery plan** opens a distinct approval step. No manifest exists until **Approve this plan** succeeds. **Change plan** discards without approval.
- [ ] Prepare shows the five-row NOT A BOOKING manifest and a compact **What needs doing** section derived from approved groups, without repeating plan cards. Package preparation is not described as dispatch.
- [ ] Internal review and packing acknowledgements survive reruns and appear once in fictional session history. Carrier confirmation, manifest download and real booking are never represented as verified by a checkbox.
- [ ] **Simulate van unavailable** clears approval, preparation and old task marks, explains impacted orders and valid old/new assumed totals, then requires fresh review. New tasks match replacement groups. **Restore van** works too.
- [ ] An impossible FEST004 deadline identifies the uncovered order and offers **Review deliveries** without inventing a saving.
- [ ] **Reset demo to orders** clears the plan, approval and disruption state, but leaves five validated orders visible.
- [ ] Private Pilot and Advanced tools are secondary and remain functional; fictional data never appears in private pilot jobs.
- [ ] Keyboard focus, contrast, text wrapping, card spacing and touch targets are usable at both widths.

Streamlit AppTest validates state and actions, but not screen-reader output, actual keyboard focus order, touch targets or pixel-level phone layout. Those checks remain manual before deploying this branch.
