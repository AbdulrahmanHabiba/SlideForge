"""Read the current presentation's public viewer metadata, never download keys."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import quote, urlparse


class ViewerError(ValueError):
    pass


class _PageData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == '__NEXT_DATA__':
            self.inside = True

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'script':
            self.inside = False


def public_slide_urls(html: str, page_url: str, quality: str, max_slides: int) -> tuple[str, list[str]]:
    parser = _PageData()
    parser.feed(html)
    try:
        deck = json.loads(''.join(parser.parts))['props']['pageProps']['slideshow']
    except (ValueError, KeyError, TypeError) as exc:
        raise ViewerError('SlideShare public viewer data is unavailable. The page may have changed or require sign-in.') from exc
    if not isinstance(deck, dict) or deck.get('isPrivate') is not False or deck.get('isViewable') is not True:
        raise ViewerError('This presentation is not publicly viewable. Private or sign-in-only presentations are not supported.')
    # Recommendations share the page; only the current slideshow can supply slides.
    requested_id = urlparse(page_url).path.rstrip('/').split('/')[-1]
    if requested_id.isdecimal() and str(deck.get('id')) != requested_id:
        raise ViewerError('SlideShare returned a different presentation than the requested link.')
    total = deck.get('totalSlides')
    if type(total) is not int or not 1 <= total <= max_slides:
        raise ViewerError(f'The presentation must contain between 1 and {max_slides} slides.')
    slides = deck.get('slides')
    if not isinstance(slides, dict) or slides.get('host') != 'https://image.slidesharecdn.com':
        raise ViewerError('The public viewer did not provide a supported slide image host.')
    location, title = slides.get('imageLocation'), slides.get('title')
    if not isinstance(location, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', location):
        raise ViewerError('The public viewer did not provide a valid slide image path.')
    if not isinstance(title, str) or not title or '/' in title or '\\' in title:
        raise ViewerError('The public viewer did not provide a valid slide image title.')
    sizes = slides.get('imageSizes', [])
    sizes = [size for size in sizes if isinstance(size, dict)
             and type(size.get('width')) is int and 1 <= size['width'] <= 4096
             and type(size.get('quality')) is int and 1 <= size['quality'] <= 100]
    if not sizes:
        raise ViewerError('No public slide image sizes were declared by the viewer.')
    smaller = [size for size in sizes if size['width'] <= 960]
    selected = max(sizes, key=lambda size: size['width']) if quality == 'hd' else max(smaller, key=lambda size: size['width']) if smaller else min(sizes, key=lambda size: size['width'])
    base = f"https://image.slidesharecdn.com/{location}/{selected['quality']}/{quote(title, safe='-_')}"
    urls = [f"{base}-{number}-{selected['width']}.jpg" for number in range(1, total + 1)]
    return str(deck.get('title') or title), urls
