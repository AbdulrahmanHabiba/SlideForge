# Deploy SlideForge

## Why it is not a static HTML upload

This application includes server-side document processing, so the backend must run somewhere. Opening `index.html` directly does **not** enable conversions. Scribd and SlideShare do not provide unrestricted public download APIs. There is no fully reliable, unlimited-cost-free way to host unlimited large conversions.

## Docker hosting

Run on a machine with Docker:

```bash
docker build -t slideforge .
docker run --rm -p 8000:8080 --memory=1g --cpus=2 slideforge
```

Browse http://localhost:8000 . For a public deployment, use a Python/Docker hosting service, HTTPS reverse proxy, rate limiting, memory/CPU limits, a pinned-IP egress proxy to eliminate DNS-rebinding SSRF, and abuse monitoring. Cap concurrency and job sizes according to available infrastructure. DNS preflight is useful but not sufficient as an SSRF defense for public arbitrary URL fetching.

## Cost / free-tier reality

The code is free and ad-free. Running it on your own computer is free apart from your electricity/Internet. Public hosting depends on the selected provider's free-tier rules and may cost money. Many serverless platforms cap response payload to a few MB; batch HD decks can exceed those limits. For 10 large decks, deploy to a worker/container host rather than a typical serverless function.

## Live smoke test

1. Open the website.
2. Upload `samples/sample-deck.pdf`.
3. Choose **PDF + PPTX**, **HD**, and **Convert documents**.
4. Download both results or the ZIP.
5. Try mixed batches, duplicates and invalid URLs; a failed item must never silently appear as a success.

Do not claim external SlideShare/Scribd coverage before testing against authorized **current** public URLs from those sites. This environment cannot directly access those domains, so online extraction is unverified.
