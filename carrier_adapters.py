"""Carrier API boundaries. No booking or rate call is made until an adapter is configured and invoked."""
from abc import ABC, abstractmethod


class CarrierAdapter(ABC):
    @abstractmethod
    def fetch_rates(self, shipment):
        """Return authenticated, timestamped rate quotations for one shipment."""


class EasyParcelAdapter(CarrierAdapter):
    def fetch_rates(self, shipment):
        raise RuntimeError('EasyParcel live quotes disabled: official API endpoint, authentication and account environment need verification. Upload an actual carrier quote CSV instead.')


class LalamoveAdapter(CarrierAdapter):
    def fetch_rates(self, shipment):
        raise RuntimeError('Lalamove live quotes are not configured.')

class FocusedProviderAdapter(CarrierAdapter):
    """No live endpoint is assumed; integration requires provider documentation."""
    def __init__(self,provider):
        if provider not in ('EasyParcel Malaysia','Lalamove Malaysia','Pos Malaysia'):
            raise ValueError('Unsupported provider.')
        self.provider=provider
    def fetch_rates(self,shipment):
        return {'status':'NOT_CONNECTED','provider':self.provider,'quotes':[],
                'reason':'Authorized API credentials and verified provider request format are unavailable.'}
