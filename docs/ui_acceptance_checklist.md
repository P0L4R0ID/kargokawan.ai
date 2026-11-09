# UI acceptance checklist

- [ ] Opening the app shows **Five-order walkthrough** first, with one clear scenario-loading action and a fictional-data disclosure.
- [ ] **Delivery orders** lists all five destinations and postcodes without a wide raw table; detailed CSV-like data is expandable.
- [ ] **Plan & compare** explains chosen groups, eligible baseline, assumption evidence, excluded options and truthful solver status.
- [ ] **Review & approve** has no manifest before human approval. Preview and approval remain distinct actions; discard leaves orders unchanged.
- [ ] **Activity** records only actions actually taken. Van disruption clears prior approval and calls for a new decision.
- [ ] An impossible deadline shows an uncovered order and blocks approval and manifest export.
- [ ] **Private Pilot** retains OIDC checks and owner-scoped backend calls. Anonymous visitors see login/setup guidance, not real jobs.
- [ ] **Advanced & other demos** retains the previous dashboard and four-order workflow.
- [ ] Keyboard focus is visible on buttons. Read text and status at laptop and phone widths; ensure no main recommendation requires horizontal scrolling.
- [ ] Exported fictional manifest says **NOT A BOOKING**. No UI claims booking, payment, dispatch or guaranteed delivery.

Automated Streamlit AppTest checks widgets, reruns and state transitions, but it cannot establish keyboard focus order, screen-reader quality or pixel-level mobile layout. The native Streamlit tab component and responsive columns reduce layout risk; manual browser inspection at narrow widths and assistive-technology review remain necessary before public release. The advanced toolset still has dense legacy forms, and the private pilot retains its existing technical quote-evidence editing interface.
