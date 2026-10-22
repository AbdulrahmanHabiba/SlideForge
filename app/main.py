"""SlideForge HTTP API. All batch artifacts are streamed back in one response.
No databases, user accounts, server-side artifact retention, or advertisements.
"""
from __future__ import annotations
import asyncio
import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from .core import (MAX_JOBS, MAX_INPUT_BYTES, Source, ConversionError,
                   convert_source, get_source_from_url, safe_name)

logger = logging.getLogger('slideforge')
app = FastAPI(title='SlideForge', version='2.1.0', docs_url=None, redoc_url=None)
STATIC = Path(__file__).resolve().parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.get('/')
async def home():
    return FileResponse(STATIC / 'index.html', media_type='text/html')

@app.get('/api/health')
async def health():
    return {'status': 'ok', 'version': '2.1.0', 'source_mode': 'public-slides', 'max_links': MAX_JOBS, 'formats': ['pdf', 'pptx'], 'max_pages': 80}

async def prepare_file(f: UploadFile) -> tuple[str, Source]:
    filename = Path(f.filename or 'document').name
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.pdf', '.pptx', '.png', '.jpg', '.jpeg', '.webp'}:
        raise ConversionError('Unsupported upload. Use PDF, PPTX, JPG, PNG or WEBP.')
    raw = await f.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ConversionError('Upload is larger than 25 MB.')
    name = safe_name(Path(filename).stem)
    return name, Source(name, raw, suffix, 'upload')

@app.post('/api/convert')
@app.post('/api/download')
async def convert(
    urls: Annotated[str, Form()] = '[]',
    fmt: Annotated[str, Form()] = 'both',
    quality: Annotated[str, Form()] = 'hd',
    files: list[UploadFile] | None = File(default=None),
):
    if fmt not in ('pdf', 'pptx', 'both') or quality not in ('hd', 'sd'):
        raise HTTPException(422, 'Invalid format or quality.')
    try:
        links = json.loads(urls)
    except Exception:
        raise HTTPException(422, 'Links must be a JSON array.')
    if not isinstance(links, list) or any(not isinstance(s, str) for s in links):
        raise HTTPException(422, 'Links must be strings.')
    links = [x.strip() for x in links if x.strip()]
    if len(links) + len(files or []) == 0:
        raise HTTPException(422, 'Add at least one link or file.')
    if len(links) + len(files or []) > MAX_JOBS:
        raise HTTPException(422, f'You can process up to {MAX_JOBS} items per batch.')
    jobs: list[tuple[str, str, str | UploadFile]] = []
    for u in links:
        jobs.append(('link', u, u))
    for f in files or []:
        jobs.append(('upload', f.filename or 'file', f))

    pool = asyncio.Semaphore(3)
    async def one(kind: str, label: str, payload: str | UploadFile):
        async with pool:
            try:
                if kind == 'link':
                    name, source = await get_source_from_url(payload, quality)
                else:
                    name, source = await prepare_file(payload)
                # Pillow / PyMuPDF / LibreOffice are blocking, so offload CPU work.
                results = await asyncio.to_thread(convert_source, source, quality, fmt)
                return {'label': label, 'name': name, 'files': results, 'error': None,
                        'note': 'Created from public slide images; this is not the original uploaded PowerPoint.' if isinstance(source, list) else None}
            except ConversionError as exc:
                return {'label': label, 'name': safe_name(label), 'files': {}, 'error': str(exc)}
            except Exception:
                logger.exception('Unexpected conversion failure')
                return {'label': label, 'name': safe_name(label), 'files': {},
                        'error': 'Something went wrong while converting this item.'}

    result = await asyncio.gather(*(one(*job) for job in jobs))
    # ZIP_STORED supports efficient browser-side extraction without a JS dependency.
    buf = io.BytesIO()
    manifest: list[dict] = []
    filenames_used = set()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as zf:
        for index, item in enumerate(result, 1):
            entries = []
            for extension, data in item['files'].items():
                candidate = safe_name(item['name'])
                filename = f'{candidate}.{extension}'
                if filename.lower() in filenames_used:
                    filename = f'{candidate}-{index}.{extension}'
                filenames_used.add(filename.lower())
                zf.writestr(filename, data)
                entries.append({'name': filename, 'size': len(data), 'format': extension})
            manifest.append({'source': item['label'], 'title': item['name'], 'files': entries, 'error': item['error'], 'note': item.get('note')})
        zf.writestr('manifest.json', json.dumps({'items': manifest, 'quality': quality}, ensure_ascii=False))
    if not any(x['files'] for x in manifest):
        return Response(content=json.dumps({'detail': 'No files could be converted.', 'items': manifest}),
                        media_type='application/json', status_code=422)
    buf.seek(0)
    async def archive_chunks():
        while chunk := buf.read(64 * 1024):
            yield chunk
        buf.close()
    return StreamingResponse(archive_chunks(), media_type='application/zip', headers={
        'Content-Disposition': 'attachment; filename="slideforge-batch.zip"',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
    })
