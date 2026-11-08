# Delivery operations demo (2–3 minutes)

1. Start Streamlit and show **What do you need delivered?**. Enter a plain-language
   goal in the text area. The assistant above can interpret logistics requests,
   while actual orders always come from explicit input. Select **Load synthetic
   nationwide intake sample** to see 15 fictional orders and a checklist for
   missing exact postcodes. City names never invent delivery postcodes.
2. Show **Create delivery job**. The job receives a persistent `KK-` ID, a
   lifecycle state and timestamped event history. The intake checklist marks
   user tasks; the agent identifies quote and planning tasks.
3. In the imported quotation sections, upload complete user-obtained courier
   and vehicle quotes. The mixed-method solver can propose a complete plan for
   postcode-aware orders; public starting prices cannot. Preview and explicitly
   approve. Export the manifest to show each order's chosen provider, quote
   reference, method and deadline. The manifest says **NOT A BOOKING**.
4. Mark preparation complete and hand off for manual provider booking. The
   user records a real provider confirmation reference, tracking ID and evidence.
   Only then can the job be marked booked. Transit and delivery need additional
   evidence. Show the status counters and audit events.
5. Explain the limit: no provider booking/tracking APIs are connected. The
   existing simulated shipping demo and optional LLM assistant remain separate.
