# scrapers/base_scraper.py
"""
Tüm scraper'lar için soyut (abstract) temel sınıf.

Bu sınıf, tüm scraper'lar için ortak olan şu işlevleri sağlar:
- `requests.Session` yönetimi (performans ve ortak header'lar için).
- `fetch_page`: Sayfayı `requests` ile çekme, 'retry' (yeniden deneme) mantığı.
- `scrape`: Ana orkestrasyon metodu (fetch -> parse).
- `_clean_text`, `_normalize_content`, `_generate_id_from_url` gibi yardımcı metotlar.

Bu sınıftan miras alan (inherit eden) her alt sınıf,
iki metodu @abstractmethod gereği EZMEK (override) zorundadır:
1. `parse_announcements`: Sayfa listesini (soup) alıp duyuru listesi döndürür.
2. `fetch_announcement_content`: Tek bir duyuru URL'ine gidip normalize edilmiş içerik metnini döndürür.
"""

import time
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from abc import ABC, abstractmethod  # Soyut sınıf için
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import bot_config
from core.logger import log_info, log_error, log_debug, log_scraper_error, log_scraper_success, log_warning


class BaseScraper(ABC):
    DIRECT_FILE_EXTENSIONS = (
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.odt', '.ods', '.odp', '.zip', '.rar', '.7z',
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.mp4', '.mp3',
    )
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

    def _fetch_url(self, url: str) -> requests.Response:
        """
        Yeniden deneme (retry) mantığı içeren HTTP GET yardımcısı.

        Tüm HTTP istekleri bu metodu kullanır. `bot_config`'deki
        'MAX_RETRIES' ve 'RETRY_DELAY' ayarlarına göre geçici hatalarda
        (Timeout, ConnectionError, 5xx, 429) yeniden dener.
        Kalıcı 4xx istemci hatalarında (429 hariç) yeniden denemeden hata fırlatır.

        Args:
            url: Çekilecek URL.

        Returns:
            requests.Response: Başarılı HTTP yanıtı (encoding düzeltilmiş).

        Raises:
            Exception: Max retry aşıldığında veya yeniden denenemez hata durumunda.
        """
        request_url = self._sanitize_url(url)
        retries = 0

        while retries < bot_config.MAX_RETRIES:
            try:
                # İstekler arası güvenlik gecikmesi
                time.sleep(bot_config.REQUEST_DELAY_MS / 1000.0)

                response = self.session.get(request_url, timeout=bot_config.REQUEST_TIMEOUT)

                # HTTP 4xx veya 5xx hata kodları için kontrol
                response.raise_for_status()

                # Sunucu Content-Type içinde charset bildirmediyse tahmini veya utf-8 kullan
                content_type = response.headers.get("Content-Type", "") if response.headers else ""
                if "charset" not in content_type.lower():
                    response.encoding = response.apparent_encoding or "utf-8"

                return response

            except requests.exceptions.HTTPError as e:
                # 4xx istemci hataları (429 Too Many Requests hariç) kalıcıdır
                status_code = e.response.status_code if e.response is not None else None
                if status_code and 400 <= status_code < 500 and status_code != 429:
                    log_warning(f"⚠️ [{self.name}] İstemci hatası ({status_code}). Yeniden denenmeyecek: {url}")
                    raise

                retries += 1
                log_warning(f"⚠️ [{self.name}] HTTP hatası ({status_code or e.__class__.__name__}). Retry {retries}/{bot_config.MAX_RETRIES}: {url}")
                if retries < bot_config.MAX_RETRIES:
                    time.sleep(bot_config.RETRY_DELAY)

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                retries += 1
                log_warning(f"⚠️ [{self.name}] Bağlantı hatası ({e.__class__.__name__}). Retry {retries}/{bot_config.MAX_RETRIES}: {url}")
                if retries < bot_config.MAX_RETRIES:
                    time.sleep(bot_config.RETRY_DELAY)

            except Exception as e:
                # Diğer beklenmeyen hatalar
                log_error(f"❌ [{self.name}] Beklenmeyen HTTP hatası: {url}, hata: {e}", exc_info=True)
                raise

        # Yeniden deneme sayısı aşıldı
        raise Exception(f"{self.name}: {bot_config.MAX_RETRIES} deneme sonrası URL çekilemedi: {url}")

    def fetch_page(self) -> BeautifulSoup:
        """
        Ana duyuru listesi sayfasının HTML'ini çeker ve 'soup' döndürür.

        `_fetch_url` ile retry destekli olarak sayfayı çeker,
        ardından BeautifulSoup ile parse eder.

        Returns:
            BeautifulSoup: Parse edilmiş HTML nesnesi.

        Raises:
            Exception: HTTP hatası veya max_retries aşıldığında.
        """
        log_debug(f"🌐 [{self.name}] Sayfa çekiliyor... ({self.url})")

        response = self._fetch_url(self.url)

        # lxml parser ile parse et (hızlı)
        soup = BeautifulSoup(response.text, "lxml")

        log_debug(f"✅ {self.name}: Sayfa başarıyla çekildi")
        return soup

    @abstractmethod
    def parse_announcements(self, soup: BeautifulSoup) -> List[Dict]:
        """
        [ZORUNLU] HTML (soup)'u parse ederek duyuru listesini döndürür.

        Bu metot, alt sınıflar tarafından mutlaka ezilmeli (override) ve
        o sitenin HTML yapısına göre yazılmalıdır.

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
                    'date': '2025-01-01' (ISO YYYY-MM-DD, opsiyonel)
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
        Döndürdüğü string, 'content_hash' oluşturmak ve saklamak için kullanılır;
        görünür metinle birlikte bağlantı ve medya adreslerini de içerecek
        şekilde normalize edilmiş olmalıdır.

        Args:
            url: Tek bir duyurunun tam URL'i.

        Returns:
            Optional[str]: Normalize edilmiş içerik metni.
                          Sayfa geldi ama içerik bulunamadıysa None döner.

        Raises:
            Exception: Sayfa çekilemezse (ağ/HTTP hatası) exception
                       FIRLATILMALIDIR, None döndürülmemelidir. Scheduler,
                       "içerik yok" ile "çekilemedi" durumlarını bu sayede ayırır.
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
            return []  # Hata durumunda boş liste döndür, scheduler devam etsin

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
        return text.strip()

    def _normalize_content(self, element: Optional[BeautifulSoup], base_url: Optional[str] = None) -> Optional[str]:
        """
        Bir HTML içerik bloğundan normalize edilmiş metin ve bağlantı özeti üretir.

        Script/style etiketlerini temizler, metindeki fazla boşlukları sadeleştirir
        ve yalnız bağlantı URL'lerinin (ör. PDF dosyaları) değiştiği durumların da
        algılanabilmesi için `href` ve `src` adreslerini çıktıya ekler.

        Args:
            element: İçeriği barındıran BeautifulSoup öğesi.
            base_url: Göreceli linklerin çözümleneceği temel URL.

        Returns:
            Normalize edilmiş içerik string'i veya içerik boşsa None.
        """
        if element is None:
            return None

        for tag in element.find_all(['script', 'style']):
            tag.decompose()

        root_url = base_url or self.url
        parts: List[str] = []

        text = self._clean_text(element.get_text(" "))
        if text:
            parts.append(text)

        for anchor in element.find_all('a', href=True):
            href = anchor['href'].strip()
            if not href or href.startswith('#') or href.lower().startswith('javascript:'):
                continue
            parts.append(f"link:{urljoin(root_url, href)}")

        for media_tag in element.find_all(['img', 'iframe'], src=True):
            src = media_tag['src'].strip()
            if not src:
                continue
            parts.append(f"media:{urljoin(root_url, src)}")

        return "\n".join(parts) if parts else None

    @classmethod
    def _is_direct_file_url(cls, url: str) -> bool:
        """URL path kısmı doğrudan bir belge, arşiv veya medya dosyasına işaret ediyorsa True döndürür."""
        path = urlsplit(url.strip()).path.lower().rstrip('/')
        return path.endswith(cls.DIRECT_FILE_EXTENSIONS)

    @staticmethod
    def _is_html_response(response: object) -> bool:
        """HTTP yanıtının Content-Type başlığı HTML/XML/metin ise (veya başlık yoksa) True döndürür."""
        headers = getattr(response, 'headers', None)
        if not headers:
            return True
        content_type = (headers.get('Content-Type') or '').lower()
        if not content_type:
            return True
        return any(token in content_type for token in ('text/html', 'application/xhtml', 'text/plain', 'xml'))

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """URL'in path ve query kısımlarındaki ASCII dışı karakterleri ve boşlukları RFC 3986 uyumlu kodlar."""
        parts = urlsplit(url.strip())
        safe_path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
        safe_query = quote(parts.query, safe="/%?:@!$&'()*+,;=-._~")
        return urlunsplit((parts.scheme, parts.netloc, safe_path, safe_query, parts.fragment))

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
        parts = url.rstrip("/").split("/")
        return parts[-1] if parts else url

    def close(self):
        """
        Scraper'a ait 'requests.Session'ı kapatır.
        Scheduler'ın 'shutdown' metodunda çağrılır.
        """
        if self.session:
            self.session.close()
            log_info(f"🔒 {self.name}: Session kapatıldı")
