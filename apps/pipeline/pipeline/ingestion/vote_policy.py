"""Automatically refresh a previously validated official voting convention.

Unchanged official link and document SHA256 extend applicability without human
review. Changed content/link or unavailable verification holds inference for
machine policy re-evaluation. This does not authorize a different municipality.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin,urlparse
from bs4 import BeautifulSoup
import requests


def _url_key(url):
    parsed=urlparse(url)
    return parsed.netloc.lower().removeprefix('www.'),parsed.path


def refresh_vote_policy(rule,cache_path,checked_date,session=None):
    cache_path=Path(cache_path)
    cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    http=session or requests.Session()
    try:
        index=http.get(rule['official_directory'],timeout=30)
        index.raise_for_status()
        soup=BeautifulSoup(index.text,'html.parser')
        links={urljoin(rule['official_directory'],a['href']) for a in soup.find_all('a',href=True) if 'council procedure' in a.get_text(' ',strip=True).casefold()}
        if {_url_key(url) for url in links}!={_url_key(rule['bylaw_url'])}:
            return {**rule,'policy_status':'changed_official_link_requires_machine_re_evaluation','observed_links':sorted(links)}
        headers={}
        if cache.get('bylaw_sha256')==rule['bylaw_sha256'] and cache.get('etag'):headers['If-None-Match']=cache['etag']
        document=http.get(rule['bylaw_url'],headers=headers,timeout=30)
        if document.status_code==304:
            digest=cache.get('bylaw_sha256')
        else:
            document.raise_for_status();digest=hashlib.sha256(document.content).hexdigest()
        if digest!=rule['bylaw_sha256']:
            return {**rule,'policy_status':'changed_document_requires_machine_re_evaluation','observed_sha256':digest}
        refreshed={**rule,'policy_status':'verified_unchanged','validated_as_of':checked_date,'enabled_through':checked_date}
        cache_path.parent.mkdir(parents=True,exist_ok=True)
        cache_path.write_text(json.dumps({'bylaw_url':rule['bylaw_url'],'bylaw_sha256':digest,'etag':document.headers.get('ETag') or cache.get('etag'),'checked_as_of':checked_date},indent=2))
        return refreshed
    except (requests.RequestException,OSError,ValueError) as error:
        return {**rule,'policy_status':'verification_unavailable_hold_inference','verification_error':type(error).__name__}
