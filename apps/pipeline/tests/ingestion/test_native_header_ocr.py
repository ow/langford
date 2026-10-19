"""Original scanned headers must recover dates without borrowing body dates."""
from pathlib import Path
import shutil
import sys

import pytest

from pipeline.ingestion.official_ballots import load_official_minutes


@pytest.mark.skipif(sys.platform != 'darwin' or not shutil.which('swiftc'), reason='Native Apple Vision requires macOS and Swift')
@pytest.mark.parametrize(('filename', 'catalog_date', 'expected'), [
    ('2019-04-01-original-first-page.pdf', '2019-04-01', '2019-04-01'),
    # Printed21st is legible, but actual Vision215/21s is not a valid ordinal.
    ('2016-11-21-original-first-page.pdf', '2016-11-21', None),
])
def test_original_header_local_vision_recovers_only_complete_unambiguous_dates(tmp_path, filename, catalog_date, expected):
    folder=tmp_path/'archive/meeting/Minutes'
    folder.mkdir(parents=True)
    fixture=Path(__file__).parents[1]/'fixtures/native-headers'/filename
    shutil.copyfile(fixture,folder/'Minutes.pdf')
    result=load_official_minutes(
        {'archive_path':'archive/meeting','meeting_date':catalog_date},
        root=tmp_path,people=[],cache_dir=tmp_path/'cache',
    )
    assert result['local_date']==expected
    if expected:
        proof=result['source_date_evidence']
        assert proof['method']=='macos_vision_original_pdf_header'
        assert proof['source_sha256']==result['source_sha256']
        assert proof['source_quote'].startswith('Monday, April 1, 2019')
        assert proof['weekday_verified'] is True
        assert proof['render_sha256'] and proof['engine']
