"""scrapers/base_scraper.py testleri: yeniden deneme mantığı, charset ve yardımcılar."""

import unittest
from unittest.mock import PropertyMock, patch

import requests

import bot_config
import tests.support  # noqa: F401
from scrapers.base_scraper import BaseScraper


class ConcreteScraper(BaseScraper):
    def parse_announcements(self, soup):
        return []

    def fetch_announcement_content(self, url):
        return None


def make_response(status_code: int, content_type: str = 'text/html; charset=utf-8'):
    result = requests.Response()
    result.status_code = status_code
    result._content = b'<html></html>'
    if content_type:
        result.headers['Content-Type'] = content_type
    return result


class TestBaseScraper(unittest.TestCase):
    def setUp(self):
        self._patches = [
            patch.object(bot_config, 'MAX_RETRIES', 3),
            patch.object(bot_config, 'RETRY_DELAY', 0),
            patch.object(bot_config, 'REQUEST_DELAY_MS', 0),
        ]
        for p in self._patches:
            p.start()
        self.scraper = ConcreteScraper('https://example.test', 'Test')

    def tearDown(self):
        self.scraper.close()
        for p in reversed(self._patches):
            p.stop()

    def _stub_get(self, outcomes):
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            outcome = outcomes[min(len(calls), len(outcomes)) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        self.scraper.session.get = get
        return calls

    def test_client_errors_are_not_retried(self):
        for status in (400, 401, 403, 404, 410):
            with self.subTest(status=status):
                calls = self._stub_get([make_response(status)])
                with self.assertRaises(requests.exceptions.HTTPError):
                    self.scraper._fetch_url('https://example.test/x')
                self.assertEqual(len(calls), 1)

    def test_temporary_http_errors_are_retried_until_limit(self):
        for status in (429, 500, 502, 503):
            with self.subTest(status=status):
                calls = self._stub_get([make_response(status)])
                with self.assertRaisesRegex(Exception, 'deneme sonrası'):
                    self.scraper._fetch_url('https://example.test/x')
                self.assertEqual(len(calls), 3)

    def test_network_errors_are_retried_until_limit(self):
        for error in (
            requests.exceptions.Timeout('zaman aşımı'),
            requests.exceptions.ConnectionError('bağlantı koptu'),
        ):
            with self.subTest(error=type(error).__name__):
                calls = self._stub_get([error])
                with self.assertRaisesRegex(Exception, 'deneme sonrası'):
                    self.scraper._fetch_url('https://example.test/x')
                self.assertEqual(len(calls), 3)

    def test_recovers_after_temporary_failure(self):
        calls = self._stub_get([make_response(500), make_response(200)])

        result = self.scraper._fetch_url('https://example.test/x')

        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(calls), 2)

    def test_unexpected_errors_are_not_retried(self):
        calls = self._stub_get([ValueError('beklenmeyen')])
        with self.assertRaises(ValueError):
            self.scraper._fetch_url('https://example.test/x')
        self.assertEqual(len(calls), 1)

    def test_charset_header_skips_apparent_encoding_detection(self):
        resp_with_charset = make_response(200, 'text/html; charset=utf-8')
        self._stub_get([resp_with_charset])
        with patch.object(requests.Response, 'apparent_encoding', new_callable=PropertyMock) as mock_apparent:
            self.scraper._fetch_url('https://example.test/x')
            mock_apparent.assert_not_called()

        resp_without_charset = make_response(200, 'text/html')
        resp_without_charset.encoding = None
        self._stub_get([resp_without_charset])
        result = self.scraper._fetch_url('https://example.test/x')
        self.assertIsNotNone(result.encoding)

    def test_clean_text_collapses_whitespace(self):
        self.assertEqual(self.scraper._clean_text('  a \n\t b   c '), 'a b c')
        self.assertEqual(self.scraper._clean_text(''), '')
        self.assertEqual(self.scraper._clean_text(None), '')

    def test_generate_id_from_url_uses_last_segment(self):
        for url, expected in (
            ('/bilgisayar/Icerik/Duyuru_1', 'Duyuru_1'),
            ('/bilgisayar/Icerik/Duyuru_1/', 'Duyuru_1'),
            ('Duyuru_2', 'Duyuru_2'),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.scraper._generate_id_from_url(url), expected)


    def test_sanitize_url_encodes_turkish_characters_and_spaces_without_double_encoding(self):
        calls = self._stub_get([make_response(200), make_response(200)])

        raw_url = 'https://www.bilecik.edu.tr/muhendislik/Icerik/Mezun_izleme_ve_Değerlendirme Anketi?q=ğüşıöç İĞ'
        self.scraper._fetch_url(raw_url)
        encoded = calls[0]
        self.assertEqual(
            encoded,
            'https://www.bilecik.edu.tr/muhendislik/Icerik/Mezun_izleme_ve_De%C4%9Ferlendirme%20Anketi?q=%C4%9F%C3%BC%C5%9F%C4%B1%C3%B6%C3%A7%20%C4%B0%C4%9E',
        )

        # Zaten yüzde-kodlanmış URL tekrar kodlanmamalı
        self.scraper._fetch_url(encoded)
        self.assertEqual(calls[1], encoded)


if __name__ == '__main__':
    unittest.main()
