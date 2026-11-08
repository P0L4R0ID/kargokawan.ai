"""Optional authenticated pilot section; public demos need no login."""
import json
import hashlib
import secrets
import time
import pandas as pd
import streamlit as st
from pilot_client import call_pilot


def _secrets():
    try:
        return st.secrets
    except (FileNotFoundError,KeyError):
        return {}


def render():
    st.header('Authenticated pilot operations')
    st.caption('Separate from fictional demos. EasyParcel Open API OAuth: NOT_CONNECTED. No booking or payment.')
    settings=_secrets()
    try:
        auth=settings.get('auth',{})
        allowed=settings.get('PILOT_OPERATOR_SUB')
    except (FileNotFoundError,KeyError):
        auth={};allowed=None
    if not allowed or not all(auth.get(k) for k in ('redirect_uri','cookie_secret','client_id','client_secret','server_metadata_url')) or auth.get('expose_tokens')!='id':
        st.info('Pilot login is not configured. An OIDC provider, ID-token exposure and exact operator subject are required.')
        return
    if not getattr(st.user,'is_logged_in',False):
        st.info('Sign in with the configured identity provider to request pilot access.')
        if st.button('Sign in for pilot'): st.login()
        return
    try:
        user_valid=st.user.get('sub')==allowed and int(st.user.get('exp') or 0)>int(time.time())
    except (TypeError,ValueError):
        user_valid=False
    if not user_valid:
        st.error('This signed-in identity is not the allowed pilot operator, or its session expired.')
        if st.button('Sign out of pilot'): st.logout()
        return
    try:
        id_token=st.user.tokens['id']
    except (KeyError,AttributeError,TypeError):
        st.error('The identity provider ID token is unavailable. Configure expose_tokens = "id".')
        return
    status=call_pilot(id_token,'GET','/pilot/status')
    if status['status']!='OK':
        st.warning('Pilot operations unavailable: '+status.get('reason','Backend identity or persistent storage is not ready.'))
        return
    st.success('Pilot operator verified by Render; persistent job storage is available.')
    if st.button('Sign out of pilot'): st.logout()
    from sample_intake import validate_complete
    uploaded=st.file_uploader('Upload pilot delivery orders CSV',type='csv',key='pilot_orders_upload')
    if uploaded is not None and st.button('Create private pilot job'):
        try:
            orders=validate_complete(uploaded.getvalue()).to_dict('records')
            upload_id='pilot_order_key_'+hashlib.sha256(uploaded.getvalue()).hexdigest()
            request_key=st.session_state.setdefault(upload_id,secrets.token_urlsafe(24))
            result=call_pilot(id_token,'POST','/pilot/jobs',{'orders':orders},request_key=request_key)
            if result['status']=='OK': st.success('Private pilot job created: '+result['data']['job_id'])
            else: st.error(result['reason'])
        except (ValueError,UnicodeError) as exc: st.error('Order CSV is incomplete or invalid: '+str(exc))
    listing=call_pilot(id_token,'GET','/pilot/jobs')
    if listing['status']!='OK':
        st.warning(listing.get('reason','Jobs unavailable.'));return
    ids=listing['data']['job_ids']
    if not ids:
        st.info('No private pilot jobs yet.');return
    job_id=st.selectbox('Your private pilot job',ids,key='pilot_job_select')
    job=call_pilot(id_token,'GET','/pilot/jobs/'+job_id)
    if job['status']!='OK': st.warning(job.get('reason','Job unavailable.'));return
    st.caption('Private pilot job · version '+str(job['data']['version']))
    edited=st.data_editor(pd.DataFrame(job['data']['orders']),key='pilot_order_editor_'+job_id,hide_index=True)
    if st.button('Save pilot order corrections'):
        from sample_intake import validate_complete
        try:
            frame=validate_complete(edited.to_csv(index=False))
            changed=call_pilot(id_token,'PUT','/pilot/jobs/'+job_id,{'orders':frame.to_dict('records')},version=job['data']['version'])
            if changed['status']=='OK': st.success('Private orders saved. Earlier quote drafts were cleared; reload to see current data.')
            else: st.error(changed['reason'])
        except ValueError as exc: st.error('Correct the order data first: '+str(exc))
    quote_upload=st.file_uploader('Upload one reviewed pilot quotation CSV',type='csv',key='pilot_quote_upload')
    st.caption('Only PUBLIC_REFERENCE and USER_IMPORTED_UNVERIFIED drafts are accepted. No quote is provider-authenticated or executable here.')
    if quote_upload is not None and st.button('Save private pilot quote draft'):
        from hybrid_quotes import parse_csv
        try:
            quotes=parse_csv(quote_upload.getvalue())
            if len(quotes)!=1: raise ValueError('Upload exactly one quotation row.')
            quote=json.loads(json.dumps(quotes[0],default=str))
            upload_id='pilot_quote_key_'+job_id+'_'+hashlib.sha256(quote_upload.getvalue()).hexdigest()
            request_key=st.session_state.setdefault(upload_id,secrets.token_urlsafe(24))
            result=call_pilot(id_token,'POST','/pilot/jobs/'+job_id+'/quotes',{'quote':quote},request_key=request_key)
            if result['status']=='OK': st.success('Private quote draft saved.')
            else: st.error(result['reason'])
        except (ValueError,UnicodeError) as exc: st.error('Quotation import rejected: '+str(exc))
    quote_ids=call_pilot(id_token,'GET','/pilot/jobs/'+job_id+'/quotes')
    if quote_ids['status']=='OK' and quote_ids['data']['quote_ids']:
        quote_id=st.selectbox('Your private quote draft',quote_ids['data']['quote_ids'],key='pilot_quote_select')
        quote=call_pilot(id_token,'GET','/pilot/jobs/'+job_id+'/quotes/'+quote_id)
        if quote['status']=='OK':
            st.json(quote['data']['quote'])
            with st.expander('Correct this private quote draft'):
                revised_text=st.text_area('Quotation JSON evidence',value=json.dumps(quote['data']['quote'],indent=2),key='pilot_quote_json_'+quote_id)
                if st.button('Save corrected private quote'):
                    try:
                        revised=json.loads(revised_text)
                        saved=call_pilot(id_token,'PUT','/pilot/jobs/'+job_id+'/quotes/'+quote_id,
                                         {'quote':revised},version=quote['data']['version'])
                        if saved['status']=='OK': st.success('Quote draft updated. Reload to review current evidence.')
                        else: st.error(saved['reason'])
                    except ValueError: st.error('Enter valid JSON quotation evidence.')
