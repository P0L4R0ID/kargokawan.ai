# Orders-first browser acceptance checklist

At **1366px and 1440px laptop**, **768px tablet** and **375px phone** widths, check:

- [ ] Landing screen shows KargoKawan, five fictional order cards and compact demo disclosure. No recommendation, cost, saving or van assignment appears before planning.
- [ ] Pickup and destination counts match the validated order records. The complete evidence and deadline controls are expandable and keyboard reachable.
- [ ] **Find the best delivery plan** is the one dominant action. It advances to Plan and triggers the optimiser; plain reruns on Orders do not.
- [ ] Plan leads with cost, then shows any selected van before courier cards, with method, covered orders and deadline context without horizontal scrolling or repeated city names. Technical quote IDs, exclusions, provenance and solver status remain under **How was this calculated?**.
- [ ] **Why KargoKawan recommends this plan** gives concise reasons from current solver outputs: cost objective, valid parcel comparison, selected grouping, deadline compatibility and zero-buffer warning. It does not claim the fastest service or guaranteed arrival. No comparison appears without a valid baseline.
- [ ] **Review this delivery plan** opens a distinct approval step. No manifest exists until **Approve this plan** succeeds. **Change plan** discards without approval.
- [ ] Prepare leads with **Your plan is approved** and the five-row NOT A BOOKING manifest. **Preparation details** holds the full derived task list; the main screen gives one next-action explanation. Package preparation is not described as dispatch.
- [ ] Internal review and packing acknowledgements survive reruns and appear once in fictional session history. Carrier confirmation, manifest download and real booking are never represented as verified by a checkbox.
- [ ] **Simulate van unavailable** clears approval, preparation and old task marks, shows a short van-unavailable notice, impacted orders and valid old/new assumed totals, then requires fresh review. New tasks match replacement groups. **Activity history** remains optional. **Restore van** works too.
- [ ] An impossible FEST004 deadline identifies the uncovered order and offers **Review deliveries** without inventing a saving.
- [ ] **Reset demo to orders** clears the plan, approval and disruption state, but leaves five validated orders visible.
- [ ] Private Pilot and Advanced tools are secondary and remain functional; fictional data never appears in private pilot jobs.
- [ ] Keyboard focus, contrast, text wrapping, card spacing and touch targets are usable at both widths.

Streamlit AppTest validates state and actions, but not screen-reader output, actual keyboard focus order, touch targets or pixel-level phone layout. Those checks remain manual before deploying this branch.

Local Chromium review covered Orders, Plan, Approval and Prepare at approximately 1212px window width. Managed Chrome blocked device emulation; exact breakpoint, Approval, Prepare, disruption, keyboard and screen-reader visual checks remain pending. See [product design](product_design.md).
