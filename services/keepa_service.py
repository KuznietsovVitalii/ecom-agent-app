import streamlit as st
import pandas as pd
import keepa
import requests
import numpy as np
from datetime import datetime

KEEPA_BASE_URL = "https://api.keepa.com"

class KeepaService:
    def __init__(self, api_key):
        self.api_key = api_key
        self.api = keepa.Keepa(api_key, timeout=60) if api_key else None

    @st.cache_data(ttl=3600)
    def get_product_info(_self, asins, domain_id=1, **kwargs):
        """Fetches product info using direct HTTP request. Cached for 1 hour."""
        if not _self.api_key: 
            return {"error": "Keepa API Key not provided."}
        
        if isinstance(asins, str):
            asins = [s.strip() for s in asins.split(',') if s.strip()]
        if not asins:
            return {"error": "ASIN parameter is empty."}

        params = {'key': _self.api_key, 'domain': domain_id, 'asin': ','.join(asins)}
        if kwargs.get('stats_days'): params['stats'] = kwargs.get('stats_days')
        if kwargs.get('include_rating'): params['rating'] = 1
        if kwargs.get('include_history'): params['history'] = 1
        if kwargs.get('limit_days'): params['days'] = kwargs.get('limit_days')
        if kwargs.get('include_offers'): params['offers'] = 100
        if kwargs.get('include_buybox'): params['buybox'] = 1
        if kwargs.get('force_update_hours') is not None: params['update'] = kwargs.get('force_update_hours')
        
        try:
            response = requests.get(f"{KEEPA_BASE_URL}/product", params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": f"API request failed: {e}"}
