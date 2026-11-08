"""Read-only provider rate checks. No booking or payment endpoints."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib import parse, request, error
import json
import os
import re

EASYPARCEL_RATE_URL = 'https://connect.easyparcel.my/?ac=EPRateCheckingBulk'

def _secret(name, secrets=None):
    if secrets is not None:
        return secrets.get(name)
    if os.environ.get(name):
        return os.environ[name]
    try:
        import streamlit as st
        return st.secrets.get(name)
    except (ImportError, FileNotFoundError, KeyError):
        return None

def _result(provider, status, reason, quotes=None):
    return {'provider':provider, 'status':status, 'reason':reason, 'quotes':quotes or []}

def _positive(value):
    try:
        number=Decimal(str(value))
        return number if number.is_finite() and number>0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None

def _post(url, fields, timeout):
    req=request.Request(url, parse.urlencode(fields).encode('utf-8'), method='POST')
    with request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


class CarrierAdapter(ABC):
    @abstractmethod
    def fetch_rates(self, shipment):
        """Return authenticated, timestamped rate quotations for one shipment."""


class EasyParcelAdapter(CarrierAdapter):
    def __init__(self, secrets=None, transport=None):
        self.secrets=secrets
        self.transport=transport or _post

    def connection_status(self):
        return 'CONNECTED' if _secret('EASYPARCEL_API_KEY', self.secrets) else 'NOT_CONNECTED'

    def fetch_rates(self, shipment):
        provider='EasyParcel Malaysia'
        key=_secret('EASYPARCEL_API_KEY', self.secrets)
        if not key:
            return _result(provider,'NOT_CONNECTED','Set EASYPARCEL_API_KEY to request authorised rates.')
        mapping={'pick_code':'origin_postcode','send_code':'destination_postcode',
                 'pick_state':'origin_state','send_state':'destination_state',
                 'weight':'weight_kg','length':'length_cm','width':'width_cm','height':'height_cm'}
        missing=[name for name in ('order_id',*mapping.values()) if not str(shipment.get(name) or '').strip()]
        if missing:
            return _result(provider,'ERROR','Missing provider request facts: '+', '.join(missing))
        if any(not re.fullmatch(r'\d{5}',str(shipment[name])) for name in ('origin_postcode','destination_postcode')):
            return _result(provider,'ERROR','Postcodes must contain five digits.')
        if any(_positive(shipment[name]) is None for name in ('weight_kg','length_cm','width_cm','height_cm')):
            return _result(provider,'ERROR','Weight and dimensions must be positive.')
        fields={'api':key,'bulk[0][pick_country]':'MY','bulk[0][send_country]':'MY'}
        fields.update({f'bulk[0][{name}]':str(shipment[source]) for name,source in mapping.items()})
        try:
            data=self.transport(EASYPARCEL_RATE_URL,fields,10)
        except error.HTTPError as exc:
            reason='Authentication failed.' if exc.code in (401,403) else 'Rate limit reached.' if exc.code==429 else 'Provider HTTP error.'
            return _result(provider,'ERROR',reason)
        except (TimeoutError,error.URLError,OSError):
            return _result(provider,'ERROR','Provider request timed out or network is unavailable.')
        except (ValueError,TypeError):
            return _result(provider,'ERROR','Unreadable provider response.')
        if not isinstance(data,dict) or str(data.get('api_status','')).lower() not in ('success','1'):
            return _result(provider,'ERROR','Provider rejected the rate check or returned an unexpected status.')
        rows=data.get('result')
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or str(rows[0].get('status','')).lower()!='success':
            return _result(provider,'ERROR','No successful rate result.')
        rates=rows[0].get('rates')
        if not isinstance(rates,list):
            return _result(provider,'ERROR','Unrecognized rate structure.')
        observed=[]
        for group in rates:
            if not isinstance(group,dict): continue
            for tier in ('member_rate','non_member_rate'):
                for item in group.get(tier,[]) if isinstance(group.get(tier),list) else []:
                    if not isinstance(item,dict) or (price:=_positive(item.get('price'))) is None: continue
                    observed.append({'source_class':'LIVE_AUTHENTICATED','provider':provider,
                        'order_id':str(shipment['order_id']),'courier':item.get('courier_name'),
                        'service':item.get('service_name'),'service_id':item.get('service_id'),
                        'rate_id':item.get('rate_id'),'account_tier':tier,'displayed_cost_myr':price,
                        'shipment_price_myr':_positive(item.get('shipment_price')),
                        'addon_price_myr':_positive(item.get('addon_price')),
                        'delivery_text':item.get('delivery'),'collected_at':datetime.now(timezone.utc).isoformat(),
                        'valid_until':None,'tax_status':'UNKNOWN','surcharge_status':'UNKNOWN',
                        'full_cost':False,'review_status':'INCOMPLETE',
                        'source_reference':'EasyParcel authenticated rate check; rate_id='+str(item.get('rate_id') or 'unknown')})
        return _result(provider,'CONNECTED','Authenticated rate check succeeded; payable total and validity require review.',observed)


class LalamoveAdapter(CarrierAdapter):
    def __init__(self, secrets=None):
        self.secrets=secrets

    def connection_status(self):
        return 'CONNECTED' if _secret('LALAMOVE_API_KEY',self.secrets) and _secret('LALAMOVE_API_SECRET',self.secrets) else 'NOT_CONNECTED'

    def fetch_rates(self, shipment):
        if self.connection_status()=='NOT_CONNECTED':
            return _result('Lalamove Malaysia','NOT_CONNECTED','Sandbox API key and secret are required.')
        stops=shipment.get('stops') or []
        if len(stops)<2 or any(not isinstance(stop,dict) or not stop.get('address') or not isinstance(stop.get('coordinates'),dict) or any(stop['coordinates'].get(k) is None for k in ('lat','lng')) for stop in stops):
            return _result('Lalamove Malaysia','ERROR','Exact pickup and ordered drop-off addresses and coordinates are required; postcodes alone are insufficient.')
        return _result('Lalamove Malaysia','ERROR','Service type, supported city, capacity and account access need provider confirmation before sandbox requests.')

class FocusedProviderAdapter(CarrierAdapter):
    """No live endpoint is assumed; integration requires provider documentation."""
    def __init__(self,provider):
        if provider not in ('EasyParcel Malaysia','Lalamove Malaysia','Pos Malaysia'):
            raise ValueError('Unsupported provider.')
        self.provider=provider
    def fetch_rates(self,shipment):
        return {'status':'NOT_CONNECTED','provider':self.provider,'quotes':[],
                'reason':'Authorized API credentials and verified provider request format are unavailable.'}
