"""Refresh street-only City GIS data; retain independently reviewed aliases.

Run with Python 3 from any directory. No address ranges or geometry are requested.
The City service also contains neighbouring municipalities: the locality filter
and response-level locality check are mandatory. This script never adds aliases.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

LAYER = 'https://arcex.langford.ca/server/rest/services/Engineering_Infrastructure/Dark_Parcels_Base/MapServer/3'
ABBREVIATIONS = {'Avenue': 'Ave', 'Boulevard': 'Blvd', 'Close': 'Cl', 'Court': 'Crt',
    'Crescent': 'Cres', 'Drive': 'Dr', 'Gardens': 'Gdns', 'Green': 'Grn', 'Heights': 'Hts',
    'Highway': 'Hwy', 'Lane': 'Ln', 'Parkway': 'Pkwy', 'Place': 'Pl', 'Plateau': 'Plat',
    'Road': 'Rd', 'Terrace': 'Terr'}


def refresh() -> None:
    target = Path(__file__).with_name('langford-streets.json')
    previous = json.loads(target.read_text())
    with urlopen(LAYER + '?f=json', timeout=60) as response:
        metadata = json.load(response)
    if 'error' in metadata or 'Query' not in metadata.get('capabilities', '').split(','):
        raise ValueError('Official layer is not queryable')
    params = {'where': "Community='Langford'", 'outFields': 'Full_Name,Str_Name,Str_Desg,Community,Status',
        'returnDistinctValues': 'true', 'returnGeometry': 'false', 'f': 'json'}
    url = LAYER + '/query?' + urlencode(params)
    with urlopen(url, timeout=60) as response:
        raw = response.read()
    data = json.loads(raw)
    features = data.get('features', [])
    if 'error' in data or not features or data.get('exceededTransferLimit'):
        raise ValueError('Missing, invalid, or truncated official response')
    if len(features) >= metadata['maxRecordCount']:
        raise ValueError('Response reaches transfer ceiling; pagination review required')
    names = set()
    for feature in features:
        row = feature['attributes']
        if row['Community'] != 'Langford' or row['Status'] != 'A':
            raise ValueError('Unexpected locality/status; preserve previous asset for review')
        # Full_Name preserves official mixed case; Str_Name has a known spelling
        # disagreement, so it must never replace the actual published Full_Name.
        name = row['Full_Name'].removesuffix(' (Private)').strip()
        designation = row['Str_Desg'].title()
        short = ABBREVIATIONS.get(designation, designation)
        if not name.endswith(' ' + short):
            raise ValueError(f'Unrecognised official suffix: {name!r}')
        names.add(name[:-len(short)] + designation)
    if not set(previous.get('street_aliases', {}).values()).issubset(names):
        raise ValueError('A reviewed alias target disappeared; independent source review required')
    previous.update(source_url=url, retrieved_at=datetime.now(timezone.utc).isoformat(),
        source_sha256=hashlib.sha256(raw).hexdigest(), source_record_count=len(features),
        canonical_street_count=len(names), streets=sorted(names, key=str.casefold))
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(previous, indent=2) + '\n')
    temporary.replace(target)
    print(f'Refreshed {len(names)} canonical Langford street names; reviewed aliases retained.')


if __name__ == '__main__':
    refresh()
