"""Safe, bounded document ingestion and visual conversions for SlideForge.

We fetch open files and images exposed by public SlideShare viewers.
No authentication, cookies, protected content, or anti-bot circumvention.
"""
from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import re
import shutil
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import urlparse, urljoin, unquote

import fitz
import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, UnidentifiedImageError
from pptx import Presentation
from pptx.util import Inches
from .slideshare import public_slide_urls, ViewerError, BrowserRequired

MAX_INPUT_BYTES = 25 * 1024 * 1024
MAX_SLIDES = 80
MAX_JOBS = 100
USER_AGENT = 'SlideForge/1.0 (+document conversion; contact site owner)'
ALLOWED_SUFFIXES = {'.pdf', '.pptx', '.jpg', '.jpeg', '.png', '.webp'}
REMOTE_IMAGE_HOST = re.compile(r'(?:^|\.)(?:slidesharecdn\.com|slideshare\.net)$', re.I)

class ConversionError(ValueError):
    pass

@dataclass
class Source:
    name: str
    data: bytes
    kind: str
    origin: str

def safe_name(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '-', unescape(value))
    value = re.sub(r'\s+', ' ', value).strip(' .-')
    return value[:76] or 'document'

def _ip_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return addr.is_global

def validate_url(url: str) -> str:
    """Restrict remote URLs and reject obvious SSRF targets."""
    if not isinstance(url, str) or len(url) > 2048:
        raise ConversionError('Provide a valid HTTPS URL (maximum 2,048 characters).')
    parsed = urlparse(url.strip())
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ConversionError('Only public HTTPS links without credentials or custom ports are accepted.')
    host = parsed.hostname.lower().rstrip('.')
    if host in {'localhost', 'localhost.localdomain'} or host.endswith(('.local', '.internal', '.localhost')):
        raise ConversionError('Local network addresses are not supported.')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if '.' not in host or not re.fullmatch(r'[a-z0-9.-]+', host):
            raise ConversionError('Invalid hostname.')
    else:
        if not _ip_public(host):
            raise ConversionError('Private network addresses are not permitted.')
    return url.strip()

async def _resolve_public(host: str) -> None:
    try:
        records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ConversionError('Could not resolve this domain.') from exc
    if not records or any(not _ip_public(rec[4][0]) for rec in records):
        raise ConversionError('The link resolves to a restricted network address.')

async def fetch_public(url: str, max_bytes: int = MAX_INPUT_BYTES) -> tuple[bytes, str, str]:
    """Block redirects to private targets, limit size, limit time.

    NOTE: For high-trust hostile multi-tenant production, pin DNS to connected public
    addresses through a dedicated egress proxy. DNS preflight alone is not complete
    protection against DNS rebinding.
    """
    url = validate_url(url)
    async with httpx.AsyncClient(timeout=httpx.Timeout(18.0, connect=6.0), follow_redirects=False,
                                 headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/pdf,application/octet-stream,image/*'}) as client:
        for _ in range(4):
            parsed = urlparse(url)
            await _resolve_public(parsed.hostname)
            async with client.stream('GET', url) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    destination = r.headers.get('location')
                    if not destination:
                        raise ConversionError('Source returned a redirect without a destination.')
                    url = validate_url(urljoin(url, destination))
                    continue
                if r.status_code in (401, 403, 402):
                    raise ConversionError('The source requires permission, authentication, or payment. Use its official download option.')
                if r.status_code >= 400:
                    raise ConversionError(f'Source returned HTTP {r.status_code}.')
                declared = r.headers.get('content-length')
                if declared and declared.isdecimal() and int(declared) > max_bytes:
                    raise ConversionError('The source exceeds the 25 MB size limit.')
                chunks, total = [], 0
                async for piece in r.aiter_bytes(131072):
                    total += len(piece)
                    if total > max_bytes:
                        raise ConversionError('The source exceeds the size limit.')
                    chunks.append(piece)
                return b''.join(chunks), r.headers.get('content-type', ''), url
    raise ConversionError('Too many redirects from this source.')

# Matches full-size SlideShare slide images in the HTML, not preview thumbnails.
IMAGE_RE = re.compile(r'https?:(?:\\?/\\?/|//)[^\s"\'<>]+?\.(?:jpe?g|png|webp)(?:\?[^\s"\'<>]*)?', re.I)
SLIDE_NUMBER_RE = re.compile(r'(?:[-_/]slide[-_/]?|[-_/])([0-9]{1,3})(?=-\d{3,4}\.(?:jpe?g|png|webp)|[._-])', re.I)


def slide_image_urls(html: str) -> list[str]:
    decoded = unescape(html.replace('\\u002F', '/').replace('\\/', '/').replace('\\u0026', '&'))
    candidates = []
    for match in IMAGE_RE.finditer(decoded):
        url = match.group(0).rstrip('\\,]})')
        parsed = urlparse(url)
        if not parsed.hostname or not REMOTE_IMAGE_HOST.search(parsed.hostname):
            continue
        if 'ss_thumbnails' in url.lower() or '/75/' not in parsed.path and not re.search(r'(?:slide[-_])\d+', parsed.path, re.I):
            continue
        num = SLIDE_NUMBER_RE.search(parsed.path)
        if num is None:
            continue
        number = int(num.group(1))
        if not 1 <= number <= MAX_SLIDES:
            continue
        resolution = re.search(r'-(\d{3,4})(?:\.|-)', parsed.path)
        rank = int(resolution.group(1)) if resolution else 0
        candidates.append((number, rank, url))
    best: dict[int, tuple[int, str]] = {}
    for n, rank, url in candidates:
        if n not in best or rank > best[n][0]:
            best[n] = (rank, url)
    # Do not silently produce truncated presentations.
    numbers = sorted(best)
    if not numbers or numbers != list(range(1, max(numbers) + 1)):
        return []
    return [best[n][1] for n in numbers]


def explicitly_downloadable(html: str) -> bool:
    """Require affirmative metadata; fail closed when permissions cannot be verified."""
    deny = r'["\'](?:allow_download|allowDownload|is_downloadable|downloadable|downloadEnabled)["\']\s*:\s*false'
    allow = r'["\'](?:allow_download|allowDownload|is_downloadable|downloadable|downloadEnabled)["\']\s*:\s*true'
    return bool(re.search(allow, html, re.I)) and not bool(re.search(deny, html, re.I))

async def get_source_from_url(url: str, quality: str) -> tuple[str, list[bytes] | Source]:
    url = validate_url(url)
    host = urlparse(url).hostname.lower()
    if host == 'academia.edu' or host.endswith('.academia.edu'):
        raise ConversionError('Academia.edu normally requires a free account for official PDF downloads. Select PDF only → Download PDF on Academia, then upload the authorized file here.')
    if host == 'scribd.com' or host.endswith('.scribd.com'):
        raise ConversionError('Scribd pages do not offer a supported public file API. Use Scribd’s official download option for an authorized copy, then upload it here.')
    if host in {'slideshare.net', 'www.slideshare.net'} or host.endswith('.slideshare.net'):
        html_bytes, ctype, _ = await fetch_public(url, max_bytes=3 * 1024 * 1024)
        if 'html' not in ctype.lower() and not html_bytes.lstrip().startswith(b'<!'):
            raise ConversionError('SlideShare did not return a presentation page.')
        html = html_bytes.decode('utf-8', 'replace')
        try:
            deck_title, urls = public_slide_urls(html, url, quality, MAX_SLIDES)
        except BrowserRequired:
            from .browser import render_public_slideshare
            html = await render_public_slideshare(url)
            try:
                deck_title, urls = public_slide_urls(html, url, quality, MAX_SLIDES)
            except ViewerError as exc:
                raise ConversionError(str(exc)) from exc
        except ViewerError as exc:
            raise ConversionError(str(exc)) from exc
        semaphore = asyncio.Semaphore(5)
        async def load(image_url: str) -> bytes:
            async with semaphore:
                data, typ, _ = await fetch_public(image_url, max_bytes=8 * 1024 * 1024)
                if not data.startswith((b'\xff\xd8', b'\x89PNG', b'RIFF')):
                    raise ConversionError('One of the slides did not return a supported image.')
                return data
        images = await asyncio.gather(*(load(x) for x in urls))
        name = safe_name(deck_title)
        return name, images
    data, content_type, final_url = await fetch_public(url)
    if 'text/html' in content_type.lower() or data.lstrip()[:50].startswith((b'<!DOCTYPE html', b'<html')):
        raise ConversionError('That link points to a webpage, not a downloadable file. Use a direct PDF, PPTX, or image URL.')
    suffix = Path(unquote(urlparse(final_url).path)).suffix.lower()
    name = safe_name(Path(unquote(urlparse(final_url).path)).stem)
    return name, Source(name, data, suffix, final_url)


def as_rgb_jpeg(raw: bytes, quality: str) -> tuple[bytes, tuple[int, int]]:
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((1920, 1920) if quality == 'hd' else (960, 960), Image.Resampling.LANCZOS)
            if im.mode not in ('RGB', 'L'):
                bg = Image.new('RGB', im.size, 'white')
                if 'A' in im.getbands():
                    bg.paste(im, mask=im.getchannel('A'))
                else:
                    bg.paste(im.convert('RGB'))
                im = bg
            buf = io.BytesIO()
            im.convert('RGB').save(buf, 'JPEG', quality=87 if quality == 'hd' else 74, optimize=True)
            return buf.getvalue(), im.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ConversionError('An image could not be decoded.') from exc


def pdf_to_images(pdf: bytes, quality: str) -> list[bytes]:
    try:
        with fitz.open(stream=pdf, filetype='pdf') as doc:
            if doc.is_encrypted:
                raise ConversionError('Password-protected PDFs are not supported.')
            if len(doc) > MAX_SLIDES:
                raise ConversionError(f'Too many pages: limit is {MAX_SLIDES}.')
            zoom = 1.9 if quality == 'hd' else 1.0
            return [page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes('jpeg') for page in doc]
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError('The PDF could not be opened.') from exc


def images_to_files(raw_images: list[bytes], quality: str, fmt: str) -> dict[str, bytes]:
    if not raw_images or len(raw_images) > MAX_SLIDES:
        raise ConversionError('A document must contain between 1 and 80 pages.')
    normalized = [as_rgb_jpeg(data, quality) for data in raw_images]
    output = {}
    if fmt in ('pdf', 'both'):
        # Precise per-page aspect ratio; same information as each image.
        pdf = fitz.open()
        for jpeg, (w, h) in normalized:
            page = pdf.new_page(width=w * 72 / 144, height=h * 72 / 144)
            page.insert_image(page.rect, stream=jpeg)
        output['pdf'] = pdf.tobytes(deflate=True, garbage=3)
        pdf.close()
    if fmt in ('pptx', 'both'):
        pres = Presentation()
        for index, (jpeg, (w, h)) in enumerate(normalized):
            if index == 0:
                pres.slide_width = Inches(13.333)
                pres.slide_height = Inches(13.333 * h / w)
            slide = pres.slides.add_slide(pres.slide_layouts[6])
            # Contain images if an individual slide has a different aspect ratio.
            factor = min(pres.slide_width / w, pres.slide_height / h)
            sw, sh = int(w * factor), int(h * factor)
            slide.shapes.add_picture(io.BytesIO(jpeg), int((pres.slide_width - sw) / 2),
                                     int((pres.slide_height - sh) / 2), width=sw, height=sh)
        buf = io.BytesIO()
        pres.save(buf)
        output['pptx'] = buf.getvalue()
    return output


def pptx_to_pdf(raw: bytes) -> bytes:
    if shutil.which('libreoffice') is None:
        raise ConversionError('PPTX → PDF conversion requires LibreOffice on the server.')
    with tempfile.TemporaryDirectory(prefix='slideforge-') as temp:
        source = Path(temp) / 'presentation.pptx'
        source.write_bytes(raw)
        try:
            proc = subprocess.run(['libreoffice', '-env:UserInstallation=file://' + temp + '/lo-profile',
                                   '--headless', '--convert-to', 'pdf', '--outdir', temp, str(source)],
                                  check=False, timeout=35, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError('PowerPoint conversion exceeded the time limit.') from exc
        out = Path(temp) / 'presentation.pdf'
        if proc.returncode != 0 or not out.is_file():
            raise ConversionError('Could not export this PowerPoint to PDF.')
        return out.read_bytes()


def convert_source(src: Source | list[bytes], quality: str, fmt: str) -> dict[str, bytes]:
    if isinstance(src, list):
        return images_to_files(src, quality, fmt)
    data = src.data
    kind = src.kind.lower()
    if len(data) > MAX_INPUT_BYTES:
        raise ConversionError('Files must be smaller than 25 MB.')
    if kind == '.pdf' or data[:5] == b'%PDF-':
        try:
            with fitz.open(stream=data, filetype='pdf') as check:
                if len(check) > MAX_SLIDES:
                    raise ConversionError('PDF exceeds the 80-page limit.')
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError('Invalid PDF file.') from exc
        if fmt == 'pdf':
            return {'pdf': data}
        result = images_to_files(pdf_to_images(data, quality), quality, 'pptx')
        if fmt == 'both':
            result['pdf'] = data
        return result
    if kind == '.pptx' or data[:2] == b'PK':
        try:
            deck = Presentation(io.BytesIO(data))
            if len(deck.slides) > MAX_SLIDES:
                raise ConversionError('PowerPoint exceeds the 80-slide limit.')
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError('Invalid PowerPoint file.') from exc
        result = {}
        if fmt in ('pptx', 'both'):
            result['pptx'] = data
        if fmt in ('pdf', 'both'):
            result['pdf'] = pptx_to_pdf(data)
        return result
    if kind in ('.png', '.jpg', '.jpeg', '.webp') or data[:3] == b'\xff\xd8\xff' or data[:4] == b'\x89PNG':
        return images_to_files([data], quality, fmt)
    raise ConversionError('Supported inputs: PDF, PPTX, JPG, PNG, and WEBP.')
