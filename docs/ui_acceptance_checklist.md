# Guided workspace browser acceptance

At **1366px laptop width** and **375px phone width**, check:

- [ ] Landing screen shows KargoKawan, a plain subtitle, fictional disclosure and one **Try with 5 example deliveries** action without requiring Google sign-in.
- [ ] The Orders step shows five readable destination cards without horizontal scrolling. The detailed evidence expander and deadline controls work with keyboard and touch.
- [ ] **Review delivery plan** advances to Plan; group cards distinguish van and courier, show coverage, assumed MYR and deadline context. No repeated city names in disruption copy.
- [ ] **How this was calculated** contains quote IDs, source limitations, exclusions and solver status; the primary recommendation stays short.
- [ ] **Review this plan** advances to Approve. The manifest is unavailable until **Approve this plan** succeeds. **Change plan** discards the proposal.
- [ ] Approval advances to Prepare. The five-row CSV says NOT A BOOKING. Package preparation is not described as dispatch.
- [ ] Backward navigation preserves session state without granting approval. The progress indicator matches the visible guarded step.
- [ ] Van disruption clears approval and preparation, explains old and new valid assumed totals, and requires a new decision. Restore works too.
- [ ] An impossible FEST004 deadline names that order as uncovered and offers a clear recovery action without a fictitious saving.
- [ ] Private Pilot remains separate and owner-scoped; Advanced tools remain accessible.
- [ ] Keyboard focus, screen-reader announcements, contrast, card height and button targets are usable at both widths.

Streamlit AppTest validates widgets, transitions and state, but not pixel layout, actual tab focus order, screen-reader output or touch targets. Those browser checks remain manual before deployment.
