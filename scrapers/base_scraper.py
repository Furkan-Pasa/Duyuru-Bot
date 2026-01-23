# scrapers/base_scraper.py
"""
Tüm scraper'lar için soyut (abstract) temel sınıf.

Bu sınıf, tüm scraper'lar için ortak olan şu işlevleri sağlar:
- `requests.Session` yönetimi (performans ve ortak header'lar için).
- `fetch_page`: Sayfayı `requests` ile çekme, 'retry' (yeniden deneme) mantığı.
- `scrape`: Ana orkestrasyon metodu (fetch -> parse).
- `_clean_text`, `_generate_id_from_url` gibi yardımcı (utility) metotlar.

Bu sınıftan miras alan (inherit eden) her alt sınıf,
iki metodu @abstractmethod gereği EZMEK (override) zorundadır:
1. `parse_announcements`: Sayfa listesini (soup) alıp duyuru listesi döndürür.
2. `fetch_announcement_content`: Tek bir duyuru URL'ine gidip içerik metnini/HTML'ini döndürür.
"""

import time
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from abc import ABC, abstractmethod  # Soyut sınıf için

import bot_config
from core.logger import log_info, log_error, log_debug, log_scraper_error, log_scraper_success, log_warning


class BaseScraper(ABC):
    """
    Soyut temel scraper sınıfı.
    (Yukarıdaki modül docstring'ini inceleyin)
    """

    def __init__(self, url: str, name: str):
        """
        Scraper'ı başlatır ve HTTP session'ı oluşturur.

        Args:
            url (str): Scrape edilecek ana liste URL'si.
            name (str): Scraper adı (loglama ve DB için).
        """
        self.url = url
        self.name = name
        # HTTP oturumunu (session) başlat
        self.session = self._create_session()
        log_debug(f"🔧 {self.name} scraper hazırlandı")

    def _create_session(self) -> requests.Session:
        """
        Ortak header'ları (User-Agent vb.) olan bir 'requests.Session' oluşturur.
        
        Session kullanmak, TCP bağlantılarını yeniden kullanarak
        performansı artırır (HTTP Keep-Alive).
        """
        session = requests.Session()

        # Standart tarayıcı gibi görün (bot engeline takılmamak için)
        session.headers.update({
            "User-Agent": bot_config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })

        return session

    def fetch_page(self) -> BeautifulSoup:
        """
        Ana duyuru listesi sayfasının HTML'ini çeker ve 'soup' döndürür.

        `bot_config`'deki 'MAX_RETRIES' ve 'RETRY_DELAY' ayarlarına göre
        hata durumunda (Timeout, ConnectionError, HTTPError) yeniden dener.
        
        Returns:
            BeautifulSoup: Parse edilmiş HTML nesnesi.
            
        Raises:
            Exception: HTTP 4xx/5xx hatası veya max_retries aşıldığında.
        """
        retries = 0

        while retries < bot_config.MAX_RETRIES:
            try:
                # Güvenlik duvarına takılmamak için gecikme
                time.sleep(bot_config.REQUEST_DELAY_MS / 1000.0)
                
                log_debug(f"🌐 [{self.name}] Sayfa çekiliyor... ({self.url})")

                response = self.session.get(
                    self.url, timeout=bot_config.REQUEST_TIMEOUT
                )

                # HTTP 4xx veya 5xx hata kodları için (örn: 404, 500)
                response.raise_for_status()

                # Encoding kontrolü (Türkçe karakter sorunları için)
                response.encoding = response.apparent_encoding

                # lxml parser ile parse et (hızlı)
                soup = BeautifulSoup(response.text, "lxml")

                log_debug(f"✅ {self.name}: Sayfa başarıyla çekildi")
                return soup

            # Yeniden denenebilir hatalar (Timeout, Bağlantı, HTTP Hataları)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
                retries += 1
                log_warning(f"⚠️ [{self.name}] Sayfa çekme hatası ({e.__class__.__name__}). Tekrar deneniyor... ({retries}/{bot_config.MAX_RETRIES})")
                time.sleep(bot_config.RETRY_DELAY)

            except Exception as e:
                # Diğer beklenmeyen (yeniden denenemez) hatalar
                log_error(f"❌ [{self.name}] Sayfa çekilirken beklenmeyen hata: {e}", exc_info=True)
                raise # Bu hatayı yeniden fırlat, scrape() yakalasın

        # While döngüsü bittiyse (retries aşıldı)
        log_scraper_error(self.name, Exception(f"{bot_config.MAX_RETRIES} deneme sonrası sayfa çekilemedi!"))
        raise Exception(f"{self.name}: {bot_config.MAX_RETRIES} deneme sonrası sayfa çekilemedi!")
    
    @abstractmethod
    def parse_announcements(self, soup: BeautifulSoup) -> List[Dict]:
        """
        [ZORUNLU] HTML (soup) 'u parse ederek duyuru listesini döndürür.

        Bu metot, alt sınıflar (örn: Scraper.py) tarafından
        mutlaka ezilmeli (override) ve o sitenin HTML yapısına
        göre yazılmalıdır.

        Args:
            soup: `fetch_page`'den gelen BeautifulSoup nesnesi.

        Returns:
            Duyuru sözlüklerinin listesi.
            Sözlük yapısı (contract) şöyle olmalı:
            [
                {
                    'id': 'benzersiz_duyuru_id',
                    'title': 'Duyuru başlığı',
                    'url': 'https://... (tam URL)',
                    'date': '01.01.2025' (opsiyonel)
                },
                ...
            ]
        """
        pass

    @abstractmethod
    def fetch_announcement_content(self, url: str) -> Optional[str]:
        """
        [ZORUNLU] Tek bir duyurunun URL'ine giderek içeriğini çeker.

        Bu metot, alt sınıflar tarafından mutlaka ezilmelidir.
        Döndürdüğü string, 'content_hash' oluşturmak için kullanılır.
        Genellikle duyurunun ana metnini/HTML'ini içeren
        div'in (örn: 'div.icerik-govde') 'str()' hali olmalıdır.

        Args:
            url: Tek bir duyurunun tam URL'i.

        Returns:
            Optional[str]: Hash'lenecek içerik (genellikle ham HTML string'i).
                          İçerik çekilemezse None döner.
        """
        pass

    def scrape(self) -> List[Dict]:
        """
        Ana scraping orkestrasyon metodu.
        
        Sırasıyla `fetch_page()` ve `parse_announcements()`'i çağırır.
        Tüm süreci yönetir ve duyuru listesini döndürür.
        Scheduler bu metodu çağırır.

        Returns:
            Duyuru listesi (veya hata durumunda boş liste).
        """
        try:
            # 1. Sayfayı çek (retry mantığı içerir)
            soup = self.fetch_page()

            # 2. Duyuruları parse et (alt sınıfın mantığı)
            announcements = self.parse_announcements(soup)

            log_scraper_success(self.name, len(announcements))
            return announcements

        except Exception as e:
            # fetch_page veya parse_announcements'dan gelen hatalar
            log_scraper_error(self.name, e)
            return [] # Hata durumunda boş liste döndür, scheduler devam etsin

    def _clean_text(self, text: str) -> str:
        """
        Yardımcı metot: Metni (genellikle başlıkları) temizler.
        Fazla boşlukları, satır başlarını vb. kaldırır.

        Args:
            text: Ham metin (örn: "\n\n   Başlık \r\n  ")

        Returns:
            Temizlenmiş metin (örn: "Başlık")
        """
        if not text:
            return ""

        # 'str.split()' tüm whitespace'leri (space, \n, \t, \r) ayırır,
        # ' '.join() ile tek boşlukla birleştirir.
        text = " ".join(text.split())

        # strip() sadece baştaki/sondakini alır, ama split/join daha garanti
        text = text.strip()

        return text

    def _generate_id_from_url(self, url: str) -> str:
        """
        Yardımcı metot: URL'den basit bir ID üretmeye çalışır.

        Genellikle URL'nin son parçasını (/.../Icerik/12345) alır.
        Bu, ID'nin net olarak verilmediği siteler için bir 'fallback'tir.

        Args:
            url: Duyuru URL'i (göreceli veya tam olabilir).

        Returns:
            ID string (örn: "12345").
        """
        # URL'nin sonundaki '/' (trailing slash) varsa kaldır
        # ve '/' karakterine göre böl
        parts = url.rstrip("/").split("/")
        
        # Son parçayı ID olarak kullan
        return parts[-1] if parts else url

    def close(self):
        """
        Scraper'a ait 'requests.Session'ı kapatır.
        Scheduler'ın 'shutdown' metodunda çağrılır.
        """
        if self.session:
            self.session.close()
            log_info(f"🔒 {self.name}: Session kapatıldı")
