# scrapers/Scraper_BSEU.py
"""
Bilecik Üniversitesi (BŞEÜ) 'Liste Görünümü' Scraper'ı.

`BaseScraper`'ı implemente eder. 
BŞEÜ'nün '.../arama/4' (Duyurular) formatındaki tüm siteleriyle uyumludur.
(Örn: Bilgisayar Müh., Mühendislik Fak., SKS)
"""

from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import urljoin  # Göreceli linkleri tam linke çevirmek için
from .base_scraper import BaseScraper
from core.logger import log_debug, log_info, log_warning, log_error 

class BSEU_Duyuru(BaseScraper):
    """
    BŞEÜ 'Liste Görünümü' (arama/4) sayfaları için scraper.
    
    `BaseScraper`'dan 'parse_announcements' ve 'fetch_announcement_content'
    metotlarını (o siteye özel) implemente eder.
    """
    
    # Göreceli URL'leri (örn: /bilgisayar/Icerik/...) tam URL'e çevirmek için
    BASE_URL = 'https://www.bilecik.edu.tr'

    def __init__(self, url: str, name: str):
        """
        'BaseScraper'ın __init__'ini çağırır ve bu scraper'ın yüklendiğini loglar.
        """
        # BaseScraper'a URL ve ismi iletiyor
        super().__init__(url=url, name=name)
        log_info(f"✅ {self.name} scraper yüklendi. URL: {self.url}")


    def fetch_announcement_content(self, url: str) -> Optional[str]:
        """
        [IMPLEMENTS BaseScraper]
        Tek bir duyuru URL'ine giderek hash'lenecek ana içeriği (HTML) çeker.
        
        `BaseScraper._fetch_url()` sayesinde retry desteği vardır.
        
        1. 'icerik-govde' içindeki 'icerik-govde'yi (iç div) öncelikli arar.
        2. İçerik bulunamazsa (resim, yönlendirme vb.) 'None' döndürür.
        """
        try:
            log_debug(f"🌐 [{self.name}] Duyuru İçeriği çekiliyor: {url}")
            response = self._fetch_url(url)
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 1. Önce iç-içe (spesifik) olan div'i ara
            content_div = soup.select_one('div.icerik-govde div.icerik-govde')
            if content_div:
                return str(content_div)
            
            # 2. Bulamazsa, ana (dış) 'icerik-govde' div'ini ara
            log_debug(f"⚠️ [{self.name}] İç-içe 'icerik-govde' bulunamadı. Ana 'icerik-govde' aranacak: {url}")
            content_div = soup.find('div', class_='icerik-govde')
            if content_div:
                return str(content_div)
            
            # 3. O da bulunamazsa None döndür.
            log_debug(f"⚠️ [{self.name}] 'icerik-govde' bulunamadı. Hash için başlık kullanılacak. URL: {url}")
            return None

        except Exception as e:
            log_error(f"❌ [{self.name}] Duyuru içeriği çekilirken hata: {url}, hata: {e}", exc_info=True)
            return None
        

    def parse_announcements(self, soup: BeautifulSoup) -> List[Dict]:
        """
        [IMPLEMENTS BaseScraper]
        Ana liste sayfasının HTML'ini (soup) parse ederek duyuru listesini çıkarır.
        
        BŞEÜ web sitesinin yeni kart yapısını (div.icerik-eleman) baz alır.
        Her kart 'data-tarih' attribute'unda tarihi, içindeki 'a' tag'ında
        başlık ve linki barındırır.
        
        Args:
            soup: `fetch_page`'den gelen BeautifulSoup nesnesi.
            
        Returns:
            `BaseScraper` contract'ına uygun duyuru listesi.
        """
        announcements_list = []
        
        # Yeni HTML yapısı: div.icerik-eleman kartları
        # Her kart data-tarih, data-icerikid gibi attribute'lara sahip
        cards = soup.find_all('div', class_='icerik-eleman')
        
        if not cards:
            log_error(f"❌ {self.name}: 'icerik-eleman' class'lı div bulunamadı!")
            return []
        
        log_debug(f"📋 [{self.name}] Sayfada {len(cards)} adet kart bulundu.")

        # Her bir kartı (duyuruyu) işle
        for card in cards:
            try:
                # 1. Tarihi al (data-tarih attribute'undan)
                #    Örn: "2026-01-20T11:50:00"
                raw_date = card.get('data-tarih', '')
                
                # Tarihi insan okunabilir formata çevir (2026-01-20T11:50:00 -> 20.01.2026)
                if raw_date:
                    try:
                        dt = datetime.fromisoformat(raw_date)
                        date = dt.strftime('%d.%m.%Y')
                    except ValueError:
                        date = raw_date  # Parse edilemezse olduğu gibi kullan
                else:
                    date = ''
                
                # 2. Kart içindeki linki bul (card-title veya card-body içinde)
                #    h6.card-title içindeki a veya doğrudan kart içindeki ilk a
                link_tag = card.select_one('h6.card-title a') or card.find('a')
                
                if not link_tag:
                    continue  # Link yoksa bu kartı atla
                    
                # 3. Verileri ayıkla
                title = self._clean_text(link_tag.get_text())
                relative_url = link_tag.get('href')
                
                if not relative_url or not title:
                    continue  # href veya başlık yoksa atla
                    
                # Göreceli URL'i (örn: /bilgisayar/Icerik/...) tam adrese çevir
                full_url = urljoin(self.BASE_URL, relative_url)
                
                # URL'den ID üret (BaseScraper'daki yardımcı fonksiyon)
                # ID için göreceli URL'i kullanmak daha temiz bir ID sağlar
                ann_id = self._generate_id_from_url(relative_url)
                
                # 4. Sözlüğü oluştur ve listeye ekle
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
