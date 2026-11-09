"""Presentation-only patterns for the public fictional workspace."""
from html import escape

import streamlit as st


STYLE = """<style>
:root {color-scheme: light;}
.stApp {background: #f6f3ec; color: #182c35;}
.stApp h1, .stApp h2, .stApp h3 {color: #182c35; letter-spacing: -.025em; line-height: 1.2;}
.stApp h1 {font-weight: 750;}
.stApp [data-testid="stMainBlockContainer"] {padding-top: 3.3rem;}
.stApp p, .stApp li {line-height: 1.55;}
.stApp button:focus-visible {outline: 3px solid #a05b10; outline-offset: 3px;}
.kk-eyebrow {font-size: .82rem; font-weight: 700; color: #33766d; letter-spacing: .04em; margin: 0 0 .4rem;}
.kk-order {background: #fff; border: 1px solid #dfe5e1; border-radius: .65rem; padding: .9rem 1rem; margin: .28rem 0 .7rem; min-height: 6.9rem;}
.kk-order strong {font-size: 1.08rem; color: #182c35;}
.kk-order .meta {color: #4d5e61; margin-top: .3rem; font-size: .94rem;}
.kk-order .due {font-weight: 700; color: #245c55;}
.kk-route {background: #fff; border: 1px solid #dfe5e1; border-left: 4px solid #33766d; border-radius: .55rem; padding: 1rem 1.1rem; margin: .45rem 0 .85rem;}
.kk-route.featured {border-left-color: #b66b1b; background: #fffdf8;}
.kk-route .top {display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; flex-wrap: wrap;}
.kk-route strong {font-size: 1.06rem; color: #182c35;}
.kk-route .price {font-weight: 750; font-variant-numeric: tabular-nums; font-size: 1.15rem; white-space: nowrap; color: #182c35;}
.kk-route .detail {color: #4d5e61; margin-top: .32rem; line-height: 1.5;}
.kk-cost {background: #182c35; color: #fff; border-radius: .7rem; padding: 1.2rem 1.4rem; margin: .55rem 0 1rem;}
.kk-cost .label {color: #d8e5df; font-size: .9rem;}
.kk-cost .amount {font-size: clamp(1.8rem, 4vw, 2.4rem); font-weight: 750; line-height: 1.2; font-variant-numeric: tabular-nums; margin: .2rem 0;}
.kk-cost .compare {color: #f4e6cf; font-size: .94rem;}
.kk-decision {background: #fff; border: 1px solid #dfe5e1; border-radius: .65rem; padding: 1rem 1.25rem; margin: .6rem 0 1rem;}
.kk-decision .amount {font-size: 1.9rem; font-weight: 750; color: #182c35; font-variant-numeric: tabular-nums;}
.kk-decision .meta {color: #4d5e61; margin-top: .4rem;}
.kk-approved {background: #edf5f1; border: 1px solid #bad4c8; border-radius: .65rem; padding: 1rem 1.25rem; margin: .65rem 0 1rem;}
.kk-approved strong {color: #1b4f47; font-size: 1.06rem;}
.kk-approved .amount {color: #182c35; font-size: 1.75rem; font-weight: 750; font-variant-numeric: tabular-nums; margin-top: .4rem;}
.kk-approved .meta {color: #425b55; margin-top: .3rem;}
@media (max-width: 640px) {.kk-route .top {display: block;} .kk-route .price {display: block; margin-top: .3rem;} .kk-order {min-height: 0;} .kk-cost {padding: 1rem;}}
</style>"""


def order_card(row):
    city = escape(str(row['destination']))
    postcode = escape(str(row['destination_postcode']))
    oid = escape(str(row['order_id']))
    deadline = escape(str(row['deadline_days']))
    st.markdown(f'<div class="kk-order"><strong>{city} · {postcode}</strong>'
                f'<div class="meta">{oid} <span aria-hidden="true">·</span> '
                f'<span class="due">Due in {deadline} day(s)</span></div></div>', unsafe_allow_html=True)


def route_card(choice, orders, quote):
    by_id = {str(row['order_id']): row for row in orders.to_dict('records')}
    ids = tuple(choice['shipment_ids'])
    cities = list(dict.fromkeys(str(by_id[oid]['destination']) for oid in ids))
    van = choice['method'] == 'multi_stop_vehicle'
    title = 'Multi-stop van delivery' if van else 'Courier parcel'
    destination = ', '.join(cities)
    deadline = min(int(by_id[oid]['deadline_days']) for oid in ids)
    transit = quote['transit_days'] if quote else 'Unknown'
    css = 'kk-route featured' if van else 'kk-route'
    st.markdown(f'<div class="{css}"><div class="top"><strong>{escape(title)} · {escape(destination)}</strong>'
                f'<span class="price">RM {choice["total_myr"]:.2f}</span></div>'
                f'<div class="detail">{escape(", ".join(ids))} · {len(ids)} {"stops" if van else "parcel"}</div>'
                f'<div class="detail">Estimated delivery time after pickup: {escape(str(transit))} day(s). '
                f'Shortest order deadline: {deadline} day(s). Fictional estimate, not guaranteed.</div></div>',
                unsafe_allow_html=True)


def cost_panel(total, baseline, difference, coverage):
    comparison = (f'Separate courier delivery: RM {baseline:.2f} · Assumed difference: RM {difference:.2f}'
                  if baseline is not None and difference is not None else 'Separate courier comparison unavailable')
    st.markdown(f'<div class="kk-cost"><div class="label">Suggested delivery cost · fictional assumption</div>'
                f'<div class="amount">RM {total:.2f}</div>'
                f'<div class="compare">{escape(comparison)} · {coverage} deliveries covered</div></div>',
                unsafe_allow_html=True)


def decision_panel(total, count, groups, methods):
    st.markdown(f'<div class="kk-decision"><div class="kk-eyebrow">REVIEW BEFORE APPROVAL</div>'
                f'<div class="amount">RM {total:.2f}</div>'
                f'<div class="meta">{count} deliveries in {groups} groups · {escape(methods)} · fictional assumed cost</div></div>',
                unsafe_allow_html=True)


def approved_panel(total, count, groups):
    st.markdown(f'<div class="kk-approved"><strong>Approved for fictional preparation</strong>'
                f'<div class="amount">RM {total:.2f}</div>'
                f'<div class="meta">{count} deliveries · {groups} groups · No booking or dispatch</div></div>',
                unsafe_allow_html=True)
