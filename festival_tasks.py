"""Session-only preparation prompts derived from an approved fictional plan."""


def readiness(orders, plan=None, *, previewed=False, approved=False, prepared=False):
    if plan is None:
        return 'Orders checked · planning has not been requested. External bookings not performed.'
    if plan['status'] == 'NOT READY':
        return 'Planning blocked · no complete option. External bookings not performed.'
    if prepared:
        return 'Plan approved · operator marked packages prepared. External bookings not performed.'
    if approved:
        return 'Plan approved · preparations pending. External bookings not performed.'
    if previewed:
        return 'Plan proposed · human approval pending. External bookings not performed.'
    return 'Orders checked · plan ready for review. External bookings not performed.'


def preparation_tasks(orders, approved):
    """Return prompts, never assertions of carrier verification or booking."""
    if approved is None or approved.get('status') not in ('READY', 'SOLVER LIMITED'):
        return []
    by_id = {str(row['order_id']): row for row in orders.to_dict('records')}
    tasks = []
    for choice in approved['decisions']:
        ids = tuple(choice['shipment_ids'])
        days = min(int(by_id[oid]['deadline_days']) for oid in ids)
        scope = ', '.join(ids)
        source = choice['quote_id']
        priority = (0, days)
        tasks.extend([
            {'id': source + ':carrier', 'title': f'Confirm real service availability and payable cost for {scope}',
             'why': 'The selected rate is fictional; the provider has not confirmed it.',
             'priority': 'External check', 'sort': priority, 'acknowledge': False, 'orders': ids},
            {'id': source + ':deadline', 'title': f'Check delivery deadlines for {scope}',
             'why': f'Shortest stated deadline in this group: {days} day(s). Confirm the real service can meet it.',
             'priority': 'Deadline check', 'sort': (1, days), 'acknowledge': True, 'orders': ids},
            {'id': source + ':details', 'title': f'Review recipient addresses and parcel details for {scope}',
             'why': 'Example records are fictional; real address and parcel checks remain with the operator.',
             'priority': 'Preparation', 'sort': (2, days), 'acknowledge': True, 'orders': ids},
            {'id': source + ':packing', 'title': f'Pack and label parcels for {scope}',
             'why': 'Operator preparation task; marking it done is not dispatch.',
             'priority': 'Preparation', 'sort': (3, days), 'acknowledge': True, 'orders': ids},
        ])
    tasks.extend([
        {'id': 'manifest', 'title': 'Download the approved preparation manifest',
         'why': 'The app cannot verify that a file was downloaded.', 'priority': 'Preparation',
         'sort': (4, 0), 'acknowledge': False, 'orders': tuple(by_id)},
        {'id': 'bookings', 'title': 'Arrange actual carrier bookings outside this demo',
         'why': 'No carrier connection, booking or payment is made here.', 'priority': 'External action',
         'sort': (5, 0), 'acknowledge': False, 'orders': tuple(by_id)},
    ])
    return sorted(tasks, key=lambda task: (task['sort'], task['id']))


def changed_orders(previous, current):
    """Compare selected methods only when both plans cover orders."""
    if not previous or previous.get('total_myr') is None or current.get('total_myr') is None:
        return []
    def methods(plan):
        return {oid: item['method'] for item in plan['decisions'] for oid in item['shipment_ids']}
    before, after = methods(previous), methods(current)
    return [(oid, before[oid], after[oid]) for oid in sorted(before.keys() & after.keys())
            if before[oid] != after[oid]]
