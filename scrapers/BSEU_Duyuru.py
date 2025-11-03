# scrapers/BSEU_Duyuru.py
"""
Bilecik Üniversitesi (BŞEÜ) 'Liste Görünümü' Scraper'ı.

`BaseScraper`'ı implemente eder. 
BŞEÜ'nün '.../arama/4' (Duyurular) formatındaki tüm siteleriyle uyumludur.
(Örn: Bilgisayar Müh., Mühendislik Fak., SKS)
"""

import time
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import urljoin  # Göreceli linkleri tam linke çevirmek için
import bot_config
from .base_scraper import BaseScraper
from core.logger import log_debug, log_info, log_warning, log_error 

class Scraper1(BaseScraper):
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
        
        1. 'icerik-govde' içindeki 'icerik-govde'yi (iç div) öncelikli arar.
        2. İçerik bulunamazsa (resim, yönlendirme vb.) 'None' döndürür.
        """
        try:
            time.sleep(bot_config.REQUEST_DELAY_MS / 1000.0)
            log_debug(f"🌐 [{self.name}] Duyuru İçeriği çekiliyor: {url}")
            response = self.session.get(url, timeout=20)

            response.raise_for_status()
            response.encoding = response.apparent_encoding
            
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
            log_error(f"❌ [{self.name}] Duyuru içeriği çekilirken hata: {url}")
            log_error(f"❌ [{self.name}] {e}")
            raise   # Hatayı _run_check'e (scheduler) geri fırlat
        

    def parse_announcements(self, soup: BeautifulSoup) -> List[Dict]:
        """
        [IMPLEMENTS BaseScraper]
        Ana liste sayfasının HTML'ini (soup) parse ederek duyuru listesini çıkarır.
        
        BŞEÜ'nün 'liste-gorunum' ID'li 'div'i içindeki 'tbody' > 'tr'
        yapısını baz alır.
        
        Args:
            soup: `fetch_page`'den gelen BeautifulSoup nesnesi.
            
        Returns:
            `BaseScraper` contract'ına uygun duyuru listesi.
        """
        announcements_list = []
        
        # HTML'de "Liste" görünümünün ID'si 'liste-gorunum'
        list_view = soup.find('div', id='liste-gorunum')
        
        if not list_view:
            log_error(f"❌ {self.name}: 'liste-gorunum' ID'li ana div bulunamadı!")
            return []

        # Bu div içindeki tablo gövdesini (tbody) bul
        table_body = list_view.find('tbody')
        
        if not table_body:
            log_error(f"❌ {self.name}: 'tbody' elementi bulunamadı!")
            return []
            
        # tbody içindeki tüm satırları (tr) al
        rows = table_body.find_all('tr')
        
        if not rows:
            log_error(f"❌ {self.name}: 'tbody' içinde 'tr' (satır) bulunamadı!")
            return []

        # Her bir satırı (duyuruyu) işle
        for row in rows:
            try:
                # Satırdaki tüm hücreleri (td) al
                cells = row.find_all('td')
                
                # Beklenen yapıda en az 2 hücre olmalı (Tarih, Başlık)
                if len(cells) < 2:
                    continue
                    
                # 1. Tarihi al (ilk hücre)
                #    BaseScraper'daki _clean_text'i kullan
                date = self._clean_text(cells[0].get_text())
                
                # 2. Başlık ve linki al (ikinci hücre)
                link_tag = cells[1].find('a')
                
                if not link_tag:
                    continue # Link yoksa bu satırı atla
                    
                # 3. Verileri ayıkla
                title = self._clean_text(link_tag.get_text())
                relative_url = link_tag.get('href')
                
                if not relative_url:
                    continue # 'href' attribute'u boşsa atla
                    
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
                log_warning(f"⚠️ {self.name}: Bir duyuru satırı parse edilirken hata: {e}")
                continue
        
        return announcements_list