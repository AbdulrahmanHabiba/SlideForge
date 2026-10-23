"""Render public SlideShare pages with an isolated JavaScript-enabled browser."""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

_browser_pool = asyncio.Semaphore(1)


async def render_public_slideshare(url: str) -> str:
    from .core import ConversionError, validate_url, _resolve_public
    url = validate_url(url)
    if urlparse(url).hostname not in {'slideshare.net', 'www.slideshare.net'}:
        raise ConversionError('Browser rendering is only available for SlideShare presentation links.')
    try:
        from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout, Error as BrowserError
    except ImportError as exc:
        raise ConversionError('This server needs the browser-enabled deployment to open SlideShare verification pages.') from exc

    async with _browser_pool:
        diagnostic_log = None
        try:
            async with asyncio.timeout(60):
                async with async_playwright() as playwright:
                    from .serverless_browser import launch_options
                    try:
                        options = await asyncio.to_thread(launch_options)
                    except Exception as exc:
                        logging.getLogger('slideforge').exception('Bundled browser initialization failed')
                        raise ConversionError(f'Browser package initialization failed ({type(exc).__name__}): {str(exc)[:240]}') from exc
                    diagnostic_log = options.pop('_diagnostic_log', None)
                    profile = None
                    browser = None
                    context = None
                    try:
                        if options.get('executable_path'):
                            profile = tempfile.TemporaryDirectory(prefix='slideforge-browser-')
                            context = await playwright.chromium.launch_persistent_context(
                                profile.name, timeout=15000, service_workers='block', **options)
                        else:
                            browser = await playwright.chromium.launch(timeout=15000, **options)
                            context = await browser.new_context(service_workers='block')
                        public_hosts = set()

                        async def public_request(route):
                            request = route.request
                            try:
                                target = validate_url(request.url)
                                host = urlparse(target).hostname
                                if (request.is_navigation_request()
                                        and request.frame == page.main_frame
                                        and host not in {'slideshare.net', 'www.slideshare.net'}):
                                    raise ConversionError('The viewer navigated away from SlideShare.')
                                if host not in public_hosts:
                                    await _resolve_public(host)
                                    public_hosts.add(host)
                            except (ValueError, ConversionError):
                                await route.abort()
                                return
                            await route.continue_()

                        await context.route('**/*', public_request)
                        page = context.pages[0] if options.get('executable_path') and context.pages else await context.new_page()
                        await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                        try:
                            await page.locator('script#__NEXT_DATA__').wait_for(state='attached', timeout=30000)
                        except BrowserTimeout:
                            logging.getLogger('slideforge').warning(
                                'Public viewer metadata timed out: url=%s title=%s',
                                page.url, await page.title())
                            raise
                        html = await page.content()
                        if len(html.encode('utf-8')) > 3 * 1024 * 1024:
                            raise ConversionError('The public viewer page exceeds the supported size.')
                        return html
                    finally:
                        if context is not None:
                            await context.close()
                        if browser is not None:
                            await browser.close()
                        if profile is not None:
                            profile.cleanup()
        except (TimeoutError, BrowserTimeout) as exc:
            raise ConversionError('SlideShare still requires browser verification. No slides were downloaded; interactive challenges cannot be completed automatically.') from exc
        except BrowserError as exc:
            logging.getLogger('slideforge').exception('Public viewer browser failed')
            lines = [line for line in str(exc).splitlines() if any(marker in line for marker in ('ERROR:', 'FATAL:', 'error while loading', 'exitCode=', 'signal=', 'Protocol error'))]
            if diagnostic_log and Path(diagnostic_log).is_file():
                native = Path(diagnostic_log).read_text(errors='replace')[-12000:]
                lines.extend(line for line in native.splitlines() if any(marker in line for marker in ('FATAL:', 'ERROR:', 'Check failed')))
            detail = ' '.join(lines)[-1400:] if lines else str(exc)[:500]
            raise ConversionError(f'The server browser failed ({type(exc).__name__}): {detail}') from exc

