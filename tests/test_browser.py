"""Exercise the real renderer's routing without network or a browser install."""
import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.browser import render_public_slideshare


class BrowserRoutingTests(unittest.TestCase):
    def run_request(self, url, *, navigation=False, main=False, restricted=False):
        class ConversionError(ValueError):
            pass

        def validate(value):
            if not value.startswith('https://'):
                raise ConversionError('HTTPS required')
            return value

        async def resolve(host):
            if restricted:
                raise ConversionError('Restricted network')

        core = types.ModuleType('app.core')
        core.ConversionError = ConversionError
        core.validate_url = validate
        core._resolve_public = AsyncMock(side_effect=resolve)
        page = Mock()
        page.main_frame = object()
        page.content = AsyncMock(return_value='<script id="__NEXT_DATA__">{}</script>')
        page.locator.return_value.wait_for = AsyncMock()
        request = Mock(url=url, resource_type='image')
        request.is_navigation_request.return_value = navigation
        request.frame = page.main_frame if main else object()
        route = Mock(request=request, abort=AsyncMock(), continue_=AsyncMock())
        context = Mock(new_page=AsyncMock(return_value=page), close=AsyncMock())

        async def register(pattern, handler):
            context.handler = handler

        async def goto(*args, **kwargs):
            await context.handler(route)

        context.route = AsyncMock(side_effect=register)
        page.goto = AsyncMock(side_effect=goto)
        browser = Mock(new_context=AsyncMock(return_value=context), close=AsyncMock())
        playwright = Mock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        manager = Mock(__aenter__=AsyncMock(return_value=playwright),
                       __aexit__=AsyncMock(return_value=False))
        api = types.ModuleType('playwright.async_api')
        api.async_playwright = Mock(return_value=manager)
        api.TimeoutError = type('BrowserTimeout', (Exception,), {})
        api.Error = type('BrowserError', (Exception,), {})
        with patch('app.serverless_browser.launch_options', return_value={}), patch.dict(sys.modules, {'app.core': core, 'playwright.async_api': api}):
            html = asyncio.run(render_public_slideshare('https://www.slideshare.net/slideshow/demo/123'))
        self.assertIn('__NEXT_DATA__', html)
        browser.close.assert_awaited_once()
        return route, core

    def test_public_images_are_loaded_and_validated(self):
        route, core = self.run_request('https://image.slidesharecdn.com/slide.jpg')
        route.continue_.assert_awaited_once()
        core._resolve_public.assert_awaited_once_with('image.slidesharecdn.com')

    def test_public_subframe_navigation_is_allowed(self):
        route, _ = self.run_request('https://public.example.com/frame', navigation=True)
        route.continue_.assert_awaited_once()

    def test_main_frame_cannot_leave_slideshare(self):
        route, _ = self.run_request('https://public.example.com/frame', navigation=True, main=True)
        route.abort.assert_awaited_once()

    def test_private_subframe_is_blocked(self):
        route, _ = self.run_request('https://private.example.com/frame', navigation=True, restricted=True)
        route.abort.assert_awaited_once()

    def test_non_https_resource_is_blocked(self):
        route, _ = self.run_request('http://public.example.com/image.jpg')
        route.abort.assert_awaited_once()
