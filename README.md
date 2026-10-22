# SlideForge — an ad-free document conversion workspace

A responsive browser interface + stateless FastAPI conversion server. Supports **up to 10 input items** per batch, **PDF / PPTX / both**, **SD / HD** quality for image-based exports, per-file downloads and a batch ZIP. No accounts, paid APIs, analytics, third-party JavaScript, databases or application ads.

## Run locally

Requirements: Python 3.11+, and LibreOffice for original PPTX → PDF conversion.

```bash
cd slideforge
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:8000**. With LibreOffice missing, PDF → PPTX, image → PDF/PPTX and same-format files still work; PPTX → PDF shows an informative error.

Run tests:

```bash
python -m pytest -q tests
```

## Accepted inputs

| Input | Supported | Details |
| --- | --- | --- |
| Uploaded PDF, PPTX, PNG, JPG, WEBP | Yes | Up to 25 MB per file, 80 pages/slides per document. |
| Public direct HTTPS link to a supported file | Yes, when accessible | No logins, credentials, private IP ranges, or protected URLs. |
| SlideShare page | Conditional | Only when HTML positively confirms download is permitted and contains complete publicly accessible slide-image URLs. Fails closed otherwise. External site layout changes may break detection. |
| Scribd document page | Not as a raw link | Scribd does not provide a supported free public-download API; use an official authorized downloaded file and upload it. |

Rebuilt image-based PPTX slides are **not natively editable**. Original PPTX uploaded and downloaded in PPTX is preserved verbatim. PDF uploaded and downloaded in PDF is preserved verbatim. Choosing SD/HD affects only reconstructed content, not original files.

## Architecture

- `/app/static/`: no-build responsive UI, vanilla JavaScript, zero client dependencies.
- `/app/main.py`: async FastAPI batch orchestration, 3 concurrent jobs and per-source result manifest.
- `/app/core.py`: validation, bounded public fetches, metadata-based SlideShare extraction, safe conversions.
- Server returns a **single ZIP_STORED** archive with `manifest.json`. Browser extracts individual files from this ZIP with a tiny built-in parser — avoids temporary download URLs, job state, storage, and an external JS ZIP library.
- Images are downloaded concurrently (max five per deck), processed with Pillow, then exported via PyMuPDF / python-pptx.
- No permanent file storage; uploaded files are held in memory until conversion returns.

## Production / limitations

A truly unlimited free, reliable downloader for *every* SlideShare/Scribd URL is not realistic: the providers control download permissions, change their frontend, may throttle traffic, and sometimes require subscriptions. SlideShare publicly retired its API in 2026. **Do not bypass platform permissions or download content without the necessary rights.**

For production deployment prefer a Python-capable host with a **persistent worker**, LibreOffice installed, streaming/time/size limits, and rate limiting per IP. Free serverless providers often cap request duration and response sizes, so bulk 10× HD decks may exceed those limits. This project has basic SSRF checks (HTTPS-only, no local/IP targets, DNS preflight including redirect checks), but **DNS rebinding requires a pinned public-IP egress proxy** before exposing arbitrary external URLs to untrusted users at Internet scale.

**Current tests are local only.** External SlideShare/Scribd downloads cannot be guaranteed without access to live pages, and no public hosted URL is implied by this source package.

## Sources

- https://support.scribd.com/hc/en-us/articles/53231623793684-Slideshare-API-errors-the-public-API-has-been-retired
- https://support.scribd.com/hc/en-us/articles/30718664900500-Downloading-documents-from-Scribd
- https://support.scribd.com/hc/en-us/articles/360055662871-Managing-your-Slideshare-download-permissions
- https://github.com/chaman-k/shareslide
- https://github.com/disbitski/create-from-slideshare


## v2 changes (2026-10-23)
- Batch limit raised to 100 combined links/uploads; up to three conversion tasks are processed concurrently. This remains memory intensive for very large decks.
- Paste consecutive URLs (http:// or https://) without line breaks, or use separate lines. Duplicates removed in browser.
- Academia.edu links are recognized but require the free official download to be completed by the owner and then uploaded; we do not automate logged-in paper access.
- Production hosting is not included; this project requires a persistent Python backend.
