"""Current viewer metadata must describe one complete public presentation."""
import json
import unittest

from app.slideshare import ViewerError, public_slide_urls

URL = 'https://www.slideshare.net/slideshow/sample/123'


class PublicViewerTests(unittest.TestCase):
    def page(self, **changes):
        deck = {'id': '123', 'title': 'Sample', 'isPrivate': False, 'isViewable': True,
                'allowDownloads': False, 'totalSlides': 3,
                'slides': {'host': 'https://image.slidesharecdn.com',
                           'imageLocation': 'sample-123', 'title': 'Sample',
                           'imageSizes': [{'quality': 85, 'width': 638}, {'quality': 75, 'width': 2048}]}}
        deck.update(changes)
        data = {'props': {'pageProps': {'slideshow': deck}}}
        return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(data) + '</script>'

    def test_public_view_export_is_separate_from_original_file_download(self):
        title, urls = public_slide_urls(self.page(), URL, 'hd', 80)
        self.assertEqual(title, 'Sample')
        self.assertEqual(len(urls), 3)
        self.assertTrue(urls[0].endswith('/75/Sample-1-2048.jpg'))
        self.assertTrue(urls[-1].endswith('/75/Sample-3-2048.jpg'))

    def test_sd_uses_declared_smaller_images(self):
        _, urls = public_slide_urls(self.page(), URL, 'sd', 80)
        self.assertTrue(urls[0].endswith('/85/Sample-1-638.jpg'))

    def test_private_or_inaccessible_viewer_rejected(self):
        for change in [{'isPrivate': True}, {'isPrivate': None}, {'isViewable': False}]:
            with self.assertRaises(ViewerError):
                public_slide_urls(self.page(**change), URL, 'hd', 80)

    def test_wrong_presentation_rejected(self):
        with self.assertRaises(ViewerError):
            public_slide_urls(self.page(id='456'), URL, 'hd', 80)

    def test_invalid_count_never_silently_truncates(self):
        for count in [0, 81, '3', True]:
            with self.assertRaises(ViewerError):
                public_slide_urls(self.page(totalSlides=count), URL, 'hd', 80)

    def test_untrusted_image_host_rejected(self):
        with self.assertRaises(ViewerError):
            public_slide_urls(self.page(slides={'host': 'https://localhost'}), URL, 'hd', 80)

    def test_missing_metadata_rejected(self):
        with self.assertRaises(ViewerError):
            public_slide_urls('<html>Sign in</html>', URL, 'hd', 80)


if __name__ == '__main__':
    unittest.main()
