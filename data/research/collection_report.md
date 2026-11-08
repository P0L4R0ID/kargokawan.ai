# Malaysian logistics price collection — 8 November 2026

This dataset contains **four official public reference price components**, **zero personalized quotations**, and **four scenario quote gaps**. None of the observed amounts is a complete, eligible price for the target shipments. No real-price cross-method savings comparison is defensible yet. Direct fetches to all seven carrier domains returned proxy HTTP 403; indexed official pages were used only for the reference entries linked below. No API, booking, payment or authenticated quote tool was used.

## Source evidence

- [EasyParcel Malaysia public shipping rates](https://easyparcel.com/my/shipping-rates/) lists pay-per-use reference rates including Pos Malaysia MelPlus RM5.30, J&T Express RM5.93 and DHL eCommerce RM6.04, each labelled up to 3 kg. The page does not establish a final price for a specified postcode pair, parcel or date. These are aggregator display rates, not individual carrier quotations.
- [Lalamove Malaysia vehicle pricing](https://www.lalamove.com/en-my/all-vehicle-pricing-detail) lists a RM7 additional-stop fee for a 7-ft van in one displayed schedule. The page also displays another schedule, and a full trip requires a route-specific quote. The RM7 fee must never be treated as the total five-stop price.
- [J&T Express Malaysia shipping rates](https://www.jtexpress.my/index.php/shipping-rates), [Ninja Van price estimate guidance](https://www.ninjavan.co/en-my/support/shipper-support/pricing-and-coverage/how-to-calculate-and-check-shipping-rates), [Pos Malaysia](https://www.pos.com.my/), and [DHL Malaysia quote tool](https://www.dhl.com/my-en/home/get-a-quote.html) identify quotation paths; no exact rate was obtained.
- [TheLorry Malaysia business FAQ](https://thelorry.com/my/business/faq2/) describes distance, vehicle and extra-stop dependent pricing. It gives no matching five-stop total.

The collection date is 2026-11-08 UTC for every entry. Source pages were found through an indexed search of official domains because direct carrier-site access from this environment was denied. Treat the listed prices as published references that require re-verification before use in a decision.

## Competitor and comparison finding

EasyParcel publicly compares courier services and publishes indicative parcel starting rates. Lalamove describes multi-stop delivery and separately publishes stop charges, while the full vehicle quote depends on the route. TheLorry describes vehicle and distance based pricing with optional multiple drop-offs. These official descriptions support the **possibility** of comparing parcel-by-parcel delivery against a dedicated multi-stop vehicle. They do not prove a saving. A comparison needs five individual quotes and one full vehicle quote for the same pickup, five stops, sizes, dates, delivery requirements, tax and surcharge treatment.

For KL–Penang, KL–Johor, intra-Sabah and Peninsular–East Malaysia, collect exact postcode pairs, dimensions, weight, service, transit and full MYR totals from official tools or documented authorized APIs. Preserve source reference, retrieval time, expiry, conditions and fee breakdown. No exact postcode has been invented from a city. These gaps are listed in `quote_collection_gaps.csv`.

## Import readiness

`kargokawan_import_ready.csv` is header-only: no obtained record contains the required postcode-specific eligibility, total price, source reference and validity fields. The existing importer also limits grouping to shipments with identical origin and destination postcodes; it cannot represent five distinct delivery stops as one group quote. This research did not alter the importer or optimizer. A genuine multi-stop comparison would need a separately reviewed data model and engine change after obtaining evidence.

No live API credentials were created or used. No source here is represented as a personalized quote or official API response.
