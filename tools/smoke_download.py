"""Exercise a real public link through the download API and inspect both files."""
import io
import asyncio
import json
import sys
import zipfile
from pathlib import Path

import fitz
from fastapi.testclient import TestClient
from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
from app.core import fetch_public
from bs4 import BeautifulSoup

url = sys.argv[1]
expected = int(sys.argv[2])
if len(sys.argv) > 3:
    # Diagnostic only: use previously captured public viewer metadata while
    # downloading every real image from its declared public CDN URL.
    from app import core
    fixture = Path(sys.argv[3]).read_bytes()
    original_fetch = core.fetch_public
    async def with_captured_viewer(requested, max_bytes=core.MAX_INPUT_BYTES):
        if requested == url:
            return fixture, 'text/html', url
        return await original_fetch(requested, max_bytes=max_bytes)
    core.fetch_public = with_captured_viewer
    print('Diagnostic: viewer metadata is a captured fixture; image downloads are live.')
with TestClient(app) as client:
    response = client.post('/api/download', data={'urls': json.dumps([url]), 'fmt': 'both', 'quality': 'sd'})
if response.status_code != 200 and len(sys.argv) == 3:
    raw, content_type, final_url = asyncio.run(fetch_public(url, max_bytes=3 * 1024 * 1024))
    soup = BeautifulSoup(raw, 'html.parser')
    print('Source diagnostics:', {'bytes': len(raw), 'content_type': content_type,
          'title': soup.title.get_text() if soup.title else None,
          'script_ids': [tag.get('id') for tag in soup.find_all('script') if tag.get('id')],
          'has_viewer_metadata': b'__NEXT_DATA__' in raw,
          'public_image_count': len(soup.select('img[src*="image.slidesharecdn.com"]')),
          'text_start': soup.get_text(' ', strip=True)[:600]})
assert response.status_code == 200, response.text[:2000]
assert response.headers['content-type'].startswith('application/zip')
with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
    item = json.loads(archive.read('manifest.json'))['items'][0]
    assert not item['error'], item
    assert item['note'], item
    for info in item['files']:
        raw = archive.read(info['name'])
        if info['format'] == 'pdf':
            with fitz.open(stream=raw, filetype='pdf') as pdf:
                assert len(pdf) == expected, len(pdf)
        else:
            assert len(Presentation(io.BytesIO(raw)).slides) == expected
        print(f"Verified {info['format']}: {expected} slides, {len(raw)} bytes")
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/slideforge-live-download.zip').write_bytes(response.content)
print(f'API returned a valid ZIP: {len(response.content)} bytes')
