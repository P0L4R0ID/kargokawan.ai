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
    st.caption('Separate from fictional demos. EasyParcel OAuth and rate checks require explicit operator action. No booking or payment.')
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
    st.subheader('EasyParcel connection')
    connection=call_pilot(id_token,'GET','/pilot/easyparcel/connection')
    if connection['status']=='OK':
        details=connection['data']
        st.info('Connection: '+details['status']+' · Account environment: '+details['environment'])
        if details['environment']=='UNKNOWN' and details['status']=='CONNECTED':
            st.warning('EasyParcel did not attest Sandbox or Live during OAuth. Do not claim Sandbox verification.')
        host_choice=st.radio('Authorization host',
            ['api.easyparcel.com (documented authorization endpoint)',
             'developer.easyparcel.com (separate fallback attempt)'],
            key='pilot_easyparcel_auth_host')
        if st.button('Prepare EasyParcel Connect'):
            st.session_state.pop('pilot_easyparcel_connect_url',None)
            st.session_state.pop('pilot_easyparcel_sample_result',None)
            host='api' if host_choice.startswith('api.') else 'developer'
            prepared=call_pilot(id_token,'POST','/pilot/easyparcel/link-intent',
                                {'authorization_host':host},request_key=secrets.token_urlsafe(24))
            if prepared['status']=='OK':
                st.session_state['pilot_easyparcel_connect_url']=prepared['data']['start_url']
                st.session_state['pilot_easyparcel_connect_until']=int(time.time())+300
            else: st.warning(prepared.get('reason','Connection setup is unavailable.'))
        url=st.session_state.get('pilot_easyparcel_connect_url','')
        if (int(time.time()) < st.session_state.get('pilot_easyparcel_connect_until',0)
                and url.startswith('https://kargokawan-oauth.onrender.com/oauth/easyparcel/start?ticket=')):
            st.link_button('Continue to EasyParcel account authorization',url)
            st.caption('This one-time link expires after five minutes. Select your Sandbox account at EasyParcel. A fallback host requires a fresh Connect attempt.')
        if details['status']=='CONNECTED':
            st.caption('First test uses only the fictional 10150 → 11950, 1.5 kg sample from the API reference. No private job or customer details are sent.')
            if st.button('Check one fictional EasyParcel sample rate'):
                checked=call_pilot(id_token,'POST','/pilot/easyparcel/sandbox-quotation',{},
                                   request_key=secrets.token_urlsafe(24))
                if checked['status']=='OK': st.session_state['pilot_easyparcel_sample_result']=checked['data']
                else: st.warning(checked.get('reason','Provider quotation unavailable.'))
            sample=st.session_state.get('pilot_easyparcel_sample_result')
            if sample:
                st.caption('Provider environment evidence: '+sample.get('environment','UNKNOWN')+
                           ' · '+sample.get('sample_input','FICTIONAL INPUT')+
                           ' · Review only, never a booking or planner quote')
                if sample.get('observations'): st.dataframe(sample['observations'],hide_index=True)
                if sample.get('errors'): st.dataframe(sample['errors'],hide_index=True)
    else:
        st.info('EasyParcel Connect is unavailable: '+connection.get('reason','Backend configuration is incomplete.'))
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

    st.subheader('EasyParcel quotation readiness')
    readiness=call_pilot(id_token,'GET','/pilot/jobs/'+job_id+'/easyparcel/readiness')
    if readiness['status']=='OK':
        evidence=readiness['data']
        connector=evidence['connector']
        st.info('EasyParcel Open API: '+connector['status']+' · '+connector['reason'])
        st.caption('Credentials are not used here. Saved manual quotes remain USER_IMPORTED_UNVERIFIED; no carrier request occurred.')
        with st.expander('Check EasyParcel rates (private, read-only)'):
            st.caption('Private-job rate requests remain disabled for the first Sandbox test. The Connect section above uses only fictional PDF sample data.')
            chosen_orders=st.multiselect('Orders to quote (up to five)',
                [str(item['order_id']) for item in job['data']['orders']],
                max_selections=5,key='pilot_easyparcel_orders_'+job_id)
            subdivisions={}
            for order_id in chosen_orders:
                sender=st.text_input('Origin subdivision code for '+order_id+' (e.g. MY-14)',
                    key='pilot_easyparcel_sender_'+job_id+'_'+order_id)
                receiver=st.text_input('Destination subdivision code for '+order_id+' (e.g. MY-07)',
                    key='pilot_easyparcel_receiver_'+job_id+'_'+order_id)
                subdivisions[order_id]={'sender':sender,'receiver':receiver}
            if st.button('Check EasyParcel rates',disabled=True,
                         key='pilot_easyparcel_check_'+job_id):
                result=call_pilot(id_token,'POST','/pilot/jobs/'+job_id+'/easyparcel/quotations',
                    {'order_ids':chosen_orders,'subdivisions':subdivisions},
                    request_key=secrets.token_urlsafe(24))
                if result['status']=='OK':
                    st.session_state['pilot_easyparcel_result_'+job_id+'_'+str(job['data']['version'])]=result['data']
                else: st.warning(result.get('reason','EasyParcel is not connected.'))
            observed=st.session_state.get('pilot_easyparcel_result_'+job_id+'_'+str(job['data']['version']))
            if observed:
                st.caption('Account environment: '+observed.get('environment','UNKNOWN')+
                           ' · REVIEW ONLY · No booking · No planner promotion')
                if observed.get('observations'): st.dataframe(observed['observations'],hide_index=True)
                if observed.get('errors'): st.dataframe(observed['errors'],hide_index=True)
        if evidence['missing_quote_tasks']:
            st.write('Missing complete courier quotations')
            st.dataframe(evidence['missing_quote_tasks'],hide_index=True)
        if evidence['manual_quote_previews']:
            st.write('Saved EasyParcel evidence and review reasons')
            st.dataframe(evidence['manual_quote_previews'],hide_index=True)
        with st.expander('Preview a TEST_ONLY synthetic rate response'):
            st.warning('TEST_ONLY / SYNTHETIC — not an EasyParcel price, not saved, and never eligible for real planning.')
            chosen=st.selectbox('Fictional order for the test fixture',
                                [str(item['order_id']) for item in job['data']['orders']],
                                key='pilot_fixture_order_'+job_id)
            if st.button('Preview synthetic EasyParcel fixture',key='pilot_fixture_button_'+job_id):
                from easyparcel_quote_connector import FixtureEasyParcelQuoteAdapter, synthetic_demo_transport
                order=next(item for item in job['data']['orders'] if str(item['order_id'])==chosen)
                fixture=FixtureEasyParcelQuoteAdapter(synthetic_demo_transport).request_rates([order])
                if fixture['observations']: st.dataframe(fixture['observations'],hide_index=True)
                if fixture['rejections']: st.dataframe(fixture['rejections'],hide_index=True)
    else:
        st.warning('EasyParcel readiness unavailable: '+readiness.get('reason','Private backend is unavailable.'))

    st.subheader('Private quote-backed planning')
    st.caption('Manual evidence remains USER_IMPORTED_UNVERIFIED. A proposal is not a booking or payment.')
    availability=call_pilot(id_token,'GET','/pilot/jobs/'+job_id+'/availability')
    if availability['status']!='OK':
        st.warning(availability.get('reason','Provider availability is unavailable.'))
        return
    providers=[]
    if quote_ids['status']=='OK':
        for candidate in quote_ids['data']['quote_ids']:
            record=call_pilot(id_token,'GET','/pilot/jobs/'+job_id+'/quotes/'+candidate)
            if record['status']=='OK' and record['data']['quote'].get('provider'):
                providers.append(record['data']['quote']['provider'])
    known=sorted(set(providers)|set(availability['data']['unavailable']))
    unavailable=st.multiselect('Unavailable quoted providers',known,
                               default=availability['data']['unavailable'],key='pilot_unavailable_'+job_id)
    if st.button('Save provider availability',key='pilot_availability_save_'+job_id):
        saved=call_pilot(id_token,'PUT','/pilot/jobs/'+job_id+'/availability',
                         {'unavailable':unavailable},version=job['data']['version'])
        if saved['status']=='OK': st.success('Availability saved. Reload before requesting a plan.')
        else: st.error(saved['reason'])
    if st.button('Request private plan',key='pilot_plan_request_'+job_id):
        requested=call_pilot(id_token,'POST','/pilot/jobs/'+job_id+'/proposals',{},
                             request_key=secrets.token_urlsafe(24))
        if requested['status']=='OK':
            result=requested['data']
            if result['status']=='NOT READY':
                st.warning('NOT READY — '+result['reason'])
                for task in result['missing_tasks']: st.write('• '+task)
                if result.get('reviewed'): st.dataframe(result['reviewed'],hide_index=True)
            else:
                st.success('Reviewable private proposal created. Select it below before approval.')
        else: st.error(requested['reason'])
    listing=call_pilot(id_token,'GET','/pilot/jobs/'+job_id+'/proposals')
    if listing['status']!='OK':
        st.warning(listing.get('reason','Proposals unavailable.'))
        return
    if listing['data']['proposals']:
        proposal_id=st.selectbox('Review private plan proposal',
                                 [item['proposal_id'] for item in listing['data']['proposals']],
                                 key='pilot_proposal_'+job_id)
        detail=call_pilot(id_token,'GET','/pilot/jobs/'+job_id+'/proposals/'+proposal_id)
        if detail['status']=='OK':
            plan=detail['data']
            st.write('Proposal status: '+plan['approval_status']+' · Solver: '+plan['status'])
            st.write('Total MYR: '+plan['total_myr']+' · All-courier baseline: '+str(plan['baseline_myr'] or 'NOT AVAILABLE'))
            st.caption(plan['provenance']+' · NOT A BOOKING')
            st.dataframe(plan['decisions'],hide_index=True)
            with st.expander('Quote review and exclusions'):
                st.dataframe(plan['reviewed'],hide_index=True)
            if plan['approval_status']=='PROPOSED' and st.button('Approve this private plan',key='pilot_approve_'+proposal_id):
                approved=call_pilot(id_token,'PUT','/pilot/jobs/'+job_id+'/proposals/'+proposal_id+'/approval',
                                    {},version=plan['version'])
                if approved['status']=='OK': st.success('Plan approved. Reload to download its NOT A BOOKING manifest.')
                else: st.error(approved['reason'])
            if plan['approval_status']=='APPROVED':
                manifest=call_pilot(id_token,'GET','/pilot/jobs/'+job_id+'/proposals/'+proposal_id+'/manifest')
                if manifest['status']=='OK':
                    st.download_button('Download approved manifest — NOT A BOOKING',
                                       manifest['data']['csv'],file_name=manifest['data']['filename'],
                                       mime='text/csv',key='pilot_manifest_'+proposal_id)
                else: st.warning('Manifest unavailable: '+manifest['reason'])
    with st.expander('Private planning audit history'):
        audit=call_pilot(id_token,'GET','/pilot/jobs/'+job_id+'/audit')
        if audit['status']=='OK': st.dataframe(audit['data']['events'],hide_index=True)
        else: st.warning(audit['reason'])
