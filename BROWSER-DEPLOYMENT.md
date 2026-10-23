# SlideShare downloads with a JavaScript browser fallback

The app first reads the public viewer over HTTPS. A Client Challenge triggers
an isolated Chromium session with JavaScript enabled. Private decks, sign-in
flows, interactive CAPTCHAs and original-file download restrictions are not bypassed.
Results are clearly labeled as PDF/PPTX rebuilt from public slide images.

## Vercel's existing Python runtime

vercel.json runs tools/install_serverless_chromium.py during the build. It fetches
the exact @sparticuz/chromium 153.0.0 package from npm and verifies its pinned
SHA-512 integrity before bundling only compressed browser assets and its license.
No browser download happens during a user's request. app/serverless_browser.py
expands the assets into the instance's temporary directory when first needed.
The normal Python deployment stays in use; no container beta or new account
connection is required.

After deployment, /api/health should show version 2.3.0, browser_fallback true,
and browser_bundle true. Browser requests validate public HTTPS destinations.
Sessions close after each use, concurrency is bounded, and runtime limits apply.

Sources:
https://github.com/Sparticuz/chromium
https://playwright.dev/python/docs/browsers
https://vercel.com/docs/functions/runtimes/python

## Local and Docker

Without bundled serverless assets, Playwright uses its normally installed
Chromium. requirements-browser.txt and Dockerfile.vercel remain available for
local/container runs. The container image listens on port 80. LibreOffice is
not included.

## Verification

CI bundles the serverless assets and tests the real 49-slide URL through the API.
A second test simulates only the initial HTTP challenge, then fetches the browser
page, metadata and all images live. Unit tests also cover public resource
validation and private-deck rejection. A separate job builds and starts the
container variant and repeats its browser download. Captured metadata is used
only in a clearly labeled failure diagnostic; it cannot make a live test pass.
