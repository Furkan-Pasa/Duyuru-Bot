"""scrapers/bilecik_seu.py testleri (gerçek bs4/lxml ile, ağ kullanmadan)."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests
from bs4 import BeautifulSoup

import tests.support  # noqa: F401
from scrapers.bilecik_seu import BilecikSEUScraper
from tests.support import FIXTURES_DIR


def make_card(title='Başlık', href='/bilgisayar/Icerik/Slug_1', icerik_id='100', tarih='2026-01-20T11:50:00'):
    id_attr = f' data-icerikid="{icerik_id}"' if icerik_id is not None else ''
    return (
        f'<div class="icerik-eleman" data-tarih="{tarih}"{id_attr}>'
        f'<h6 class="card-title"><a href="{href}">{title}</a></h6></div>'
    )


def fake_response(html: str):
    return SimpleNamespace(text=html)


class TestScraperBSEU(unittest.TestCase):
    def setUp(self):
        self.scraper = BilecikSEUScraper(url='https://www.bilecik.edu.tr/bilgisayar/arama/4', name='Test')

    def tearDown(self):
        self.scraper.close()

    def _parse(self, html: str):
        return self.scraper.parse_announcements(BeautifulSoup(html, 'lxml'))

    # ----------------------------------------------------------- Liste sayfası

    def test_parses_real_list_page(self):
        html = (FIXTURES_DIR / 'bseu_liste.html').read_text(encoding='utf-8')

        announcements = self._parse(html)

        self.assertEqual(len(announcements), 21)
        self.assertEqual(announcements[0], {
            'id': '37353',
            'title': '2025-2026 Güz Dönemi Bütünleme Sınavı Programı Hk.',
            'url': (
                'https://www.bilecik.edu.tr/bilgisayar/Icerik/'
                '2025_2026_Güz_Dönemi_Bütünleme_Sınavı_Programı_Hk__89962'
            ),
            'date': '2026-01-20',
        })
        self.assertEqual(len({item['id'] for item in announcements}), len(announcements))
        self.assertTrue(all(item['id'].isdigit() for item in announcements))
        self.assertTrue(all(item['title'] and item['url'].startswith('https://') for item in announcements))

    def test_uses_data_icerikid_as_id(self):
        result = self._parse(make_card(icerik_id='37353', href='/bilgisayar/Icerik/Baska_Slug'))
        self.assertEqual(result[0]['id'], '37353')

    def test_falls_back_to_url_slug_without_icerikid(self):
        result = self._parse(make_card(icerik_id=None, href='/bilgisayar/Icerik/Yedek_Slug_123'))
        self.assertEqual(result[0]['id'], 'Yedek_Slug_123')

    def test_title_whitespace_is_normalized(self):
        result = self._parse(make_card(title='  Uzun \n   başlık  '))
        self.assertEqual(result[0]['title'], 'Uzun başlık')

    def test_unparsable_date_is_kept_as_is(self):
        result = self._parse(make_card(tarih=' yarın '))
        self.assertEqual(result[0]['date'], 'yarın')

    def test_cards_without_link_or_title_are_skipped(self):
        html = (
            '<div class="icerik-eleman" data-icerikid="1"><p>bağlantı yok</p></div>'
            + make_card(title='', icerik_id='2')
            + make_card(title='Geçerli', icerik_id='3')
        )
        self.assertEqual([item['id'] for item in self._parse(html)], ['3'])

    def test_page_without_cards_returns_empty_list(self):
        self.assertEqual(self._parse('<html><body><p>duyuru yok</p></body></html>'), [])

    # --------------------------------------------------------- Duyuru içeriği

    def test_content_prefers_nested_block(self):
        html = '<div class="icerik-govde"><div class="icerik-govde"><p>iç</p></div><p>dış</p></div>'
        with patch.object(self.scraper, '_fetch_url', return_value=fake_response(html)):
            content = self.scraper.fetch_announcement_content('https://www.bilecik.edu.tr/bilgisayar/Icerik/1')

        self.assertEqual(content, 'iç')

    def test_content_falls_back_to_outer_block(self):
        html = '<div class="icerik-govde"><p>yalnız dış</p></div>'
        with patch.object(self.scraper, '_fetch_url', return_value=fake_response(html)):
            content = self.scraper.fetch_announcement_content('https://www.bilecik.edu.tr/bilgisayar/Icerik/1')

        self.assertEqual(content, 'yalnız dış')

    def test_content_normalizes_whitespace_scripts_and_links(self):
        html = '''
        <div class="icerik-govde">
            <style>.x { color: red; }</style>
            <script>var token = "123";</script>
            <p>Sınav   programı   için
               <a href="/dosya/sinav_v2.pdf">tıklayınız</a>.
            </p>
            <a href="#top">Başa dön</a>
            <a href="javascript:void(0)">JS</a>
            <img src="ek.png" />
            <iframe src="https://example.test/embed"></iframe>
        </div>
        '''
        url = 'https://www.bilecik.edu.tr/bilgisayar/Icerik/123'
        with patch.object(self.scraper, '_fetch_url', return_value=fake_response(html)):
            content = self.scraper.fetch_announcement_content(url)

        self.assertEqual(content, (
            'Sınav programı için tıklayınız . Başa dön JS\n'
            'link:https://www.bilecik.edu.tr/dosya/sinav_v2.pdf\n'
            'media:https://www.bilecik.edu.tr/bilgisayar/Icerik/ek.png\n'
            'media:https://example.test/embed'
        ))
        self.assertNotIn('token', content)
        self.assertNotIn('color', content)
        self.assertNotIn('#top', content)
        self.assertNotIn('javascript:', content)

    def test_empty_content_block_returns_none(self):
        html = '<div class="icerik-govde">   <script>var a=1;</script>  </div>'
        with patch.object(self.scraper, '_fetch_url', return_value=fake_response(html)):
            self.assertIsNone(self.scraper.fetch_announcement_content('https://www.bilecik.edu.tr/1'))

    def test_content_is_none_when_block_missing(self):
        with patch.object(self.scraper, '_fetch_url', return_value=fake_response('<html><body></body></html>')):
            self.assertIsNone(self.scraper.fetch_announcement_content('https://www.bilecik.edu.tr/1'))

    def test_content_fetch_errors_propagate(self):
        with patch.object(self.scraper, '_fetch_url', side_effect=requests.exceptions.ConnectionError('bağlantı koptu')):
            with self.assertRaises(requests.exceptions.ConnectionError):
                self.scraper.fetch_announcement_content('https://www.bilecik.edu.tr/1')


    def test_direct_file_url_skips_fetch_and_returns_file_reference(self):
        pdf_url = 'https://www.bilecik.edu.tr/dosya/Sınav Programı.PDF'
        with patch.object(self.scraper, '_fetch_url') as mock_fetch:
            content = self.scraper.fetch_announcement_content(pdf_url)

        mock_fetch.assert_not_called()
        self.assertEqual(content, 'file:https://www.bilecik.edu.tr/dosya/S%C4%B1nav%20Program%C4%B1.PDF')

    def test_non_html_content_type_returns_file_reference_without_parsing(self):
        url = 'https://www.bilecik.edu.tr/dosya/indir?id=42'
        resp = SimpleNamespace(text='%PDF-1.4...', headers={'Content-Type': 'application/pdf'})
        with patch.object(self.scraper, '_fetch_url', return_value=resp):
            content = self.scraper.fetch_announcement_content(url)

        self.assertEqual(content, f'file:{url}')


if __name__ == '__main__':
    unittest.main()
