"""Plain-language reasons derived only from a checked fictional plan."""

from decimal import Decimal


def plan_reasons(orders, quotes, result):
    """Return four concise reasons, or none when there is no complete plan."""
    if result['status'] not in ('READY', 'SOLVER LIMITED'):
        return []
    by_id = {str(row['order_id']): row for row in orders.to_dict('records')}
    by_quote = {quote['quote_id']: quote for quote in quotes}
    eligible = {item['quote_id'] for item in result['reviewed'] if item['status'] == 'ELIGIBLE'}
    if result['status'] == 'READY':
        objective = ('KargoKawan minimised total eligible assumed cost, not delivery speed. '
                     'Every order had to be covered within its deadline using an available option.')
    else:
        objective = ('KargoKawan sought the lowest eligible assumed cost, not delivery speed. '
                     'This complete plan is feasible, but the solver did not prove it is the cheapest.')
    reasons = [objective]
    if result['baseline_myr'] is not None and result['difference_myr'] is not None:
        reasons.append(f"The selected plan totals RM {result['total_myr']:.2f}, versus RM "
                       f"{result['baseline_myr']:.2f} for separate eligible parcels "
                       f"(RM {result['difference_myr']:.2f} assumed difference).")
    else:
        reasons.append('No valid all-parcel comparison is available for these orders and constraints.')
    vehicles = [item for item in result['decisions'] if item['method'] == 'multi_stop_vehicle']
    if vehicles:
        covered = sum(len(item['shipment_ids']) for item in vehicles)
        separate = []
        for item in vehicles:
            costs = []
            for oid in item['shipment_ids']:
                options = [quote['displayed_cost_myr'] for quote in quotes
                           if quote['quote_id'] in eligible and quote['transport_method'] == 'parcel_courier'
                           and quote['shipment_ids'] == (oid,)]
                if not options:
                    costs = []
                    break
                costs.append(min(options))
            if costs:
                separate.append((sum(costs, Decimal(0)), item['total_myr']))
        if len(separate) == len(vehicles):
            parcel_total = sum((value[0] for value in separate), Decimal(0))
            vehicle_total = sum((value[1] for value in separate), Decimal(0))
            reasons.append(f"The selected multi-stop vehicle groups {covered} orders for RM {vehicle_total:.2f}; "
                           f"separate eligible parcels for those orders total RM {parcel_total:.2f}.")
        else:
            reasons.append(f'The selected multi-stop vehicle combines {covered} orders on one quoted route; '
                           'no complete parcel-only price exists for that group.')
    else:
        reasons.append('No multi-stop vehicle is selected; the complete plan uses individual courier parcels.')
    transits = []
    tight = []
    for choice in result['decisions']:
        transit = int(by_quote[choice['quote_id']]['transit_days'])
        transits.append(transit)
        for oid in choice['shipment_ids']:
            if transit == int(by_id[oid]['deadline_days']):
                tight.append(oid)
    eta = (f"Selected transit assumptions are {min(transits)}–{max(transits)} day(s) after pickup "
           if min(transits) != max(transits) else
           f"Selected transit assumptions are {transits[0]} day(s) after pickup ")
    eta += 'and meet the stated deadlines; arrival is not guaranteed.'
    if tight:
        eta += f" {', '.join(sorted(tight))} has zero day of buffer."
    reasons.append(eta)
    return reasons
