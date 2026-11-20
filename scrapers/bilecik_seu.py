# scrapers/bilecik_seu.py
"""
Bilecik Şeyh Edebali Üniversitesi (BŞEÜ) 'Liste Görünümü' Scraper'ı.

`BaseScraper`'ı implemente eder.
BŞEÜ'nün '.../arama/4' (Duyurular) formatındaki tüm siteleriyle uyumludur.
(Örn: Bilgisayar Müh., Mühendislik Fak., SKS)
"""

from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import urljoin
from .base_scraper import BaseScraper
from core.logger import log_debug, log_info, log_warning, log_error


class BilecikSEUScraper(BaseScraper):
    """
    BŞEÜ 'Liste Görünümü' (arama/4) sayfaları için scraper.

    `BaseScraper`'dan 'parse_announcements' ve 'fetch_announcement_content'
    metotlarını (o siteye özel) implemente eder.
    """

    # Göreceli URL'leri birleştirmede site URL'i yoksa kullanılacak varsayılan adres
    BASE_URL = 'https://www.bilecik.edu.tr'

    def __init__(self, url: str, name: str):
        """'BaseScraper'ın __init__'ini çağırır ve bu scraper'ın yüklendiğini loglar."""
        super().__init__(url=url, name=name)
        log_info(f"✅ {self.name} scraper yüklendi. URL: {self.url}")

    def fetch_announcement_content(self, url: str) -> Optional[str]:
        """
        [IMPLEMENTS BaseScraper]
        Tek bir duyuru URL'ine giderek normalize edilmiş ana içeriği döndürür.

        URL doğrudan bir dosya/belge (PDF, Office, arşiv vb.) adresine işaret
        ediyorsa ya da yanıt HTML değilse içerik indirilip parse edilmez; dosya
        adresi referans olarak döndürülür.

        Ağ/HTTP hataları burada yakalanmaz, çağırana (scheduler) iletilir.
        Böylece "içerik yok" (None) ile "içerik çekilemedi" (exception)
        durumları birbirinden ayrılabilir.
        """
        if self._is_direct_file_url(url):
            log_debug(f"📎 [{self.name}] Doğrudan dosya linki, içerik olarak kaydediliyor: {url}")
            return f"file:{self._sanitize_url(url)}"

        log_debug(f"🌐 [{self.name}] Duyuru İçeriği çekiliyor: {url}")
        response = self._fetch_url(url)  # Hata durumunda exception fırlatır

        if not self._is_html_response(response):
            log_debug(f"📎 [{self.name}] HTML dışı yanıt, dosya referansı döndürülüyor: {url}")
            return f"file:{self._sanitize_url(url)}"

        soup = BeautifulSoup(response.text, 'lxml')

        # 1. Önce iç-içe (spesifik) olan div'i ara
        content_div = soup.select_one('div.icerik-govde div.icerik-govde')
        if not content_div:
            # 2. Bulamazsa, ana (dış) 'icerik-govde' div'ini ara
            log_debug(f"⚠️ [{self.name}] İç-içe 'icerik-govde' bulunamadı. Ana 'icerik-govde' aranacak: {url}")
            content_div = soup.find('div', class_='icerik-govde')

        if content_div:
            return self._normalize_content(content_div, base_url=url)

        # 3. O da bulunamazsa None döndür.
        log_debug(f"⚠️ [{self.name}] 'icerik-govde' bulunamadı. URL: {url}")
        return None

    def parse_announcements(self, soup: BeautifulSoup) -> List[Dict]:
        """
        [IMPLEMENTS BaseScraper]
        Ana liste sayfasının HTML'ini (soup) parse ederek duyuru listesini çıkarır.

        BŞEÜ web sitesinin kart yapısını (div.icerik-eleman) baz alır.
        Her kart 'data-tarih' attribute'unda tarihi, 'data-icerikid' attribute'unda
        sabit kimliği ve içindeki 'a' tag'ında başlık ile linki barındırır.

        Args:
            soup: `fetch_page`'den gelen BeautifulSoup nesnesi.

        Returns:
            `BaseScraper` contract'ına uygun duyuru listesi (tarihler ISO YYYY-MM-DD).
        """
        announcements_list = []
        base_url = self.url or self.BASE_URL

        cards = soup.find_all('div', class_='icerik-eleman')

        if not cards:
            log_error(f"❌ {self.name}: 'icerik-eleman' class'lı div bulunamadı!")
            return []

        log_debug(f"📋 [{self.name}] Sayfada {len(cards)} adet kart bulundu.")

        for card in cards:
            try:
                raw_date = card.get('data-tarih', '')
                if raw_date:
                    try:
                        dt = datetime.fromisoformat(raw_date)
                        date = dt.strftime('%Y-%m-%d')
                    except ValueError:
                        date = raw_date.strip()
                else:
                    date = ''

                link_tag = card.select_one('h6.card-title a') or card.find('a')
                if not link_tag:
                    continue

                title = self._clean_text(link_tag.get_text())
                relative_url = link_tag.get('href')
                if not relative_url or not title:
                    continue

                full_url = urljoin(base_url, relative_url)

                # Karttaki stabil içerik ID'sini (data-icerikid) kullan;
                # bulunamazsa yedek olarak URL'den ID üret
                raw_id = card.get('data-icerikid')
                ann_id = str(raw_id).strip() if raw_id else ""
                if not ann_id:
                    ann_id = self._generate_id_from_url(relative_url)

                announcements_list.append({
                    'id': ann_id,
                    'title': title,
                    'url': full_url,
                    'date': date,
                })

            except Exception as e:
                log_warning(f"⚠️ {self.name}: Bir duyuru kartı parse edilirken hata: {e}")
                continue

        return announcements_list
