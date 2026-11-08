# Fictional Malaysian SME delivery orders

Both files contain **synthetic test data only**. The recipient names are placeholders. No order has been booked, dispatched or delivered. Postcodes are five-character sample inputs; confirm real customer postcodes independently.

- `malaysia_sme_5_orders.csv`: five complete fictional orders from Kuala Lumpur to Kuala Lumpur, George Town, Johor Bahru, Kota Kinabalu and Kuching.
- `malaysia_sme_incomplete_orders.csv`: the same orders with three deliberately blank fields to demonstrate the intake checklist.

| Column | Meaning |
| --- | --- |
| `order_id` | Your unique shipment identifier. |
| `origin` | Pickup city supported by the simulated planner. |
| `destination` | Delivery city supported by the simulated planner. |
| `weight_kg` | Positive package weight in kilograms. |
| `length_cm`, `width_cm`, `height_cm` | Positive package dimensions in centimetres. |
| `deadline_days` | Whole number of days allowed for delivery. |
| `recipient` | Recipient label for the operations manifest. Replace the synthetic name with your own authorized order information. |
| `origin_postcode`, `destination_postcode` | Exact five-digit Malaysian postcodes, stored as text so leading zeros survive. Never derive these from city names. |

To try the full intake workflow, start Streamlit, scroll to **What do you need delivered?**, and use **Import delivery operations CSV**. Select either file. The complete file can create a job; the incomplete file shows action items for missing recipient and postcodes. Review the editable table, then select **Create delivery job**. A job is a local task record, not a carrier booking.

The sidebar **Import shipment CSV** also accepts the complete file because its first eight columns match the established simulated-planner schema. That upload intentionally keeps only those eight columns; use the operations uploader to preserve recipient and postcode fields. The simulated planner uses fictional rates and requires **Plan shipments**. A real quote-backed plan additionally requires complete eligible courier/vehicle quotations and explicit approval.

Before planning, supply all required operational fields per order: ID, recipient, both postcodes, positive weight and dimensions, and a positive whole-number deadline. Use supported city names in the simulated dashboard. Replace sample details with your own shipment information only when authorized to handle it. The app has no live booking or payment connection.

For collecting real quote evidence, see `data/focused/templates/easyparcel_malaysia.csv` and `data/focused/templates/lalamove_malaysia.csv`. They are empty templates, not carrier prices. Enter only actual provider evidence and review provenance, charges, expiry and route stops before approval.
