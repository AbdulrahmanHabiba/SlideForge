# SlideForge — Test report

Tested on 22 October 2026 in the local container.

## Backend (pytest)

**12 passed**: API health/frontend serving; HTTPS/SSRF validation; SlideShare permission flags; extraction / slide ordering / resolution selection; image-to-PDF/PPTX conversion; PDF-original preservation; PDF-to-PPTX conversion; PPTX-to-PDF conversion using LibreOffice; ZIP packaging; partial batch failures; rejection of >10 items; Scribd restrictions; invalid PDF error path.

## Browser tests (Chromium / Playwright)

- Desktop 1440 px: UI rendered, no horizontal overflow.
- Mobile 390 px: responsive UI rendered, no horizontal overflow.
- Two typed links incremented the counter; clear restored it to zero.
- File input accepted an image and updated the selected files and counter.
- Quality selector switched successfully to Standard.
- Browser parsed an actual backend-created ZIP and displayed PDF / PPTX download buttons.
- Individual PDF download completed with the expected file name: `demo.pdf`.

## NOT verified

- Actual live SlideShare URLs: the test environment cannot fetch SlideShare pages, and publisher download-permission metadata can change.
- Actual live Scribd URLs: not supported as remote document fetches; official authorized uploads are supported.
- Production server stability, cost and public deployment: not deployed; deployment requires hosting and live integration testing.

Do not advertise unrestricted SlideShare/Scribd downloading based only on these tests.
