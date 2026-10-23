# Public SlideShare link downloads

The app first reads the public viewer over HTTPS. If SlideShare returns its
Client Challenge page, an isolated Chromium browser renders JavaScript and reads
the same public viewer. Public metadata must match the requested presentation,
declare the complete slide count, and mark it viewable and not private. Each
declared image is fetched before the PDF/PPTX and ZIP are returned.

Browser sessions are fresh and closed after use. The app does not load user
cookies, sign in, solve CAPTCHAs, use stealth extensions, or access private decks.
Interactive verification can still prevent a download; that remains an explicit
error, not a successful empty file.

## Vercel

Dockerfile.vercel packages Python, Playwright, Chromium headless shell and required
system libraries. The server listens on port 80. Vercel's Container Runtime detects
this filename and routes traffic to the container. This runtime is beta on all
plans; normal hosting usage limits and charges still apply.

https://vercel.com/docs/functions/runtimes/container
https://playwright.dev/python/docs/browsers

The regular Python runtime alone does not include a browser. After deployment,
GET /api/health should show version 2.2.0 and browser_fallback true. If it does not,
check that the deployment selected the container runtime rather than the old
Python function build. LibreOffice is not included in this browser image.

## Local run

    pip install -r requirements-browser.txt
    python -m playwright install --with-deps --only-shell chromium
    python run.py

## Verification

The workflow runs unit/API tests, the supplied 49-slide link, and a forced initial
HTTP-challenge case. In that forced case only the first HTTP response is simulated;
the browser's page, viewer metadata and all slide images are fetched live. A
separate job builds and starts Dockerfile.vercel, then repeats the live browser
download inside the production image. Captured viewer metadata is used only in a
clearly labeled diagnostic if the live test fails; it cannot make the live test pass.
