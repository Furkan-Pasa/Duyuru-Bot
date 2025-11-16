# core/scheduler.py
"""
APScheduler kullanarak görev zamanlaması (Orkestrasyon).

Bu modül, `DuyuruScheduler` sınıfını içerir. Bu sınıfın sorumlulukları:
1. `bot_config`'i okuyarak tüm aktif scraper'ları dinamik olarak yüklemek.
2. `APScheduler`'ı başlatmak ve her scraper için 2 görev kurmak:
    - Biri 'cron' (periyodik) görev (örn: her saat '01' ve '31'de).
    - Biri 'date' (ilk çalıştırma) görevi (bot başlar başlamaz).
3. `_run_check` metodu ile scraper'ları tetiklemek, DB'yi kontrol etmek.
4. Yeni/güncel duyuruları `telegram_bot`'a göndermek.
5. `shutdown` ile tüm kaynakları (DB, session'lar, thread'ler) güvenle kapatmak.
"""

import importlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler

import bot_config
from core.database import Database
from scrapers.base_scraper import BaseScraper
from core.telegram_bot import send_to_telegram, start_telegram_loop, stop_telegram_loop
from core.logger import (
    log_debug, log_info, log_error, log_warning, log_scraper_start, 
    log_task_finish, log_new_announcement, log_critical 
)

def import_from_string(path: str):
    """
    'paket.modul.ClassAdi' formatındaki bir yolu dinamik olarak import eder.
    
    Örnek:
        'scrapers.BSEU_Duyuru.Scraper1' -> Scraper1 class'ını döndürür.
        
    Returns:
        Yüklenen Class nesnesi.
    """
    try:
        # Yolu, modül ve class adı olarak ayırır
        # (örn: 'scrapers.BSEU_Duyuru', 'Scraper1')
        module_path, class_name = path.rsplit('.', 1)
    except ValueError:
        log_error(f"❌ Geçersiz import yolu: '{path}'. Format: 'paket.modul.ClassAdi'")
        raise
    
    # Modülü import et
    module = importlib.import_module(module_path)
    
    # Class'ı modülden al
    try:
        ScraperClass = getattr(module, class_name)
        return ScraperClass
    except AttributeError:
        log_error(f"❌ '{module_path}' modülünde '{class_name}' sınıfı bulunamadı.")
        raise

class DuyuruScheduler:
    """
    Scraper'ları yükler, görevleri zamanlar ve bot döngüsünü yönetir.
    """
    def __init__(self):
        """
        Scheduler'ı, veritabanını ve scraper'ları hazırlar.
        Async Telegram loop'unu (ayrı thread'de) başlatır.
        """
        log_debug("⏳ Scheduler başlatılıyor...")
        self.scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
        self.db = Database()
        
        # Async işlemleri yönetecek arkaplan thread'ini başlat
        start_telegram_loop()
        
        # Aktif scraper instance'larını tutar
        self.scrapers = {}
        self._load_scrapers()

    def _load_scrapers(self):
        """
        `bot_config.SITES` listesini okur, 'enabled' olan scraper'ları
        dinamik olarak import eder ve `self.scrapers`'a yükler.
        """
        log_info("⏳ Scheduler | Scraper'lar yükleniyor...")
        
        for site_config in bot_config.SITES:
            # Pasif siteleri atla
            if not site_config.get('enabled', False):
                log_info(f"⚠️ {site_config['name']} pasif, atlanıyor.")
                continue
                
            try:
                site_url = site_config.get('url')
                site_name = site_config['name']
                scraper_path = site_config.get('scraper_path')
                
                # Config kontrolleri
                if not site_url:
                    log_error(f"❌ {site_name} için config'de 'url' bulunamadı. Atlanıyor.")
                    continue
                if not scraper_path:
                    log_error(f"❌ {site_name} için config'de 'scraper_path' eksik. Atlanıyor.")
                    continue
                
                # 'scrapers.BSEU_Duyuru.Scraper1' yolundan Scraper1 class'ını import et
                ScraperClass = import_from_string(scraper_path)
                
                # Scraper'dan bir instance oluştur (BaseScraper __init__ çağrılır)
                scraper_instance: BaseScraper = ScraperClass(url=site_url, name=site_name)
                
                # Hazır scraper'ı sözlüğe ekle
                self.scrapers[site_name] = {
                    'instance': scraper_instance,
                    'config': site_config
                }
                log_debug(f"✅ Scheduler | Scraper hazır: [{site_name}]")
                
            except ImportError as e:
                log_error(f"❌ Scheduler | Scraper import hatası ({site_config['name']}): {e}", exc_info=True)
            except Exception as e:
                log_error(f"❌  Scheduler | Scraper yüklenemedi ({site_config['name']}): {e}", exc_info=True)

    def start(self):
        """
        Zamanlayıcıyı yapılandırır, görevleri ekler ve arkaplan thread'inde başlatır.
        
        Her site için 2 görev ekler:
        1. `CronTrigger`: `config.py`'deki dakikalarda (örn: '01', '31') her saat çalışır.
        2. `date`: Bot başlar başlamaz "bir kerelik" çalışır. (Staggered)
        """
        if not self.scrapers:
            log_warning("⚠️ Scheduler | Hiç aktif scraper bulunamadı. Lütfen config.py dosyasını kontrol edin.")
            return

        log_info("⏰ Scheduler | Zamanlayıcı görevleri ayarlanıyor...")
        
        # Botun ilk görevini çalıştırması için başlangıç gecikmesi (saniye)
        # Görevlerin birbirini boğmaması için 'stagger' (kademeli başlatma) yapılır
        initial_run_delay_seconds = 2
        
        for site_name, data in self.scrapers.items():
            site_config = data['config']
            scraper_instance = data['instance']
        
            # --- GÖREV 1: DÜZENLİ (CRON) GÖREVİ ---
            # Bu, config'de belirtilen dakikalarda (örn: '01', '31') her saat çalışır
            minutes = ','.join(site_config['schedule_minutes'])
            self.scheduler.add_job(
                self._run_check,
                trigger=CronTrigger(minute=minutes, hour='*'),
                args=[site_name, scraper_instance, site_config],
                name=f"Check_{site_name}",
                misfire_grace_time=120  # Görev gecikirse 120 saniyeye kadar yine çalıştır
            )
            log_info(f"📅 Scheduler | Görev eklendi: [{site_name}] (Her saatin {minutes} dakikalarında)")

            # --- GÖREV 2: İLK ÇALIŞTIRMA (DATE) GÖREVİ ---
            # Bot başladıktan 'initial_run_delay_seconds' saniye sonra "bir kerelik" çalışır.
            run_time = datetime.now() + timedelta(seconds=initial_run_delay_seconds)
            
            self.scheduler.add_job(
                self._run_check,
                trigger='date', # 'date' trigger'ı "bir kerelik" demektir
                run_date=run_time,
                args=[site_name, scraper_instance, site_config],
                name=f"InitialRun_{site_name}"
            )
            log_debug(f"🚀 Scheduler | İlk-çalıştırma görevi eklendi: [{site_name}] (Çalışma zamanı: {run_time.strftime('%H:%M:%S')})")
            
            # Bir sonraki scraper'ın ilk çalıştırması 5 saniye sonra olsun
            initial_run_delay_seconds += 5
            
        # Tüm görevler eklendi, şimdi scheduler'ı BAŞLAT
        self.scheduler.start()
        log_info("⏳ Scheduler | Zamanlayıcı BAŞLATILDI. Görevler arkaplanda çalışacak.")

    def shutdown(self, from_start_loop: bool = False):
        """
        Scheduler'ı ve kaynakları (DB, session'lar, async loop) güvenli bir şekilde kapatır.
        
        `main.py`'deki signal_handler (CTRL+C) tarafından çağrılır.
        
        Args:
            from_start_loop (bool): Kapatmanın `main.py`'deki ana döngüden
                                    gelip gelmediğini belirtir (normalde False).
        """
        log_debug("⏳ Scheduler | Güvenli kapatma başlatıldı...")
        
        # 1. APScheduler'ı kapat (yeni görev almayı durdur, çalışanları bitir)
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                log_debug("🔒 Scheduler | APScheduler görevleri durduruldu.")
        except Exception as e:
            log_error(f"🛑 Scheduler kapatılırken hata: {e}")

        # 2. Async Telegram thread'ini kapat
        stop_telegram_loop()
        
        # 3. Veritabanı bağlantılarını (thread-local) kapat
        try:
            self.db.close()
        except Exception as e:
            log_error(f"🛑 Veritabanı kapatılırken hata: {e}")
        
        # 4. Tüm scraper'ların (BaseScraper) 'requests.Session'larını kapat
        log_debug("⏳ Scheduler | Scraper session'ları kapatılıyor...")
        for site_name, data in self.scrapers.items():
            try:
                data['instance'].close()
            except Exception as e:
                log_error(f"🛑 [{site_name}] scraper session kapatılırken hata: {e}")
                
        log_info("🔒 Scheduler | Tüm kaynaklar serbest bırakıldı. Kapatıldı.")
        
        # Eğer bu çağrı main.py'den (signal_handler) geliyorsa, main.py'deki sys.exit() kapatmayı tamamlayacaktır.
        if from_start_loop:
            import sys
            sys.exit(0)
                    
    def _run_check(self, site_name: str, scraper: BaseScraper, site_config: Dict):
        """
        Bir site için kontrol işlemini yürüten ana fonksiyon (APScheduler bunu tetikler).
        
        1. `scraper.scrape()` ile duyuru listesini çeker.
        2. DB'de bu site için kayıt olup olmadığını kontrol eder.
        3. DB boşsa (`total_in_db == 0`): `_process_first_run`'ı çalıştırır.
        4. DB doluysa: `_process_normal_run`'ı çalıştırır.
        5. Sonucu 'stats' tablosuna kaydeder.
        """
        log_scraper_start(site_name)
        new_count = 0
        updated_count = 0
        
        try:
            # 1. Scrape et (Sadece liste geliyor)
            announcements = scraper.scrape()
            
            if not announcements:
                log_warning(f"⚠️ Scheduler | [{site_name}]: Sayfada duyuru bulunamadı.")
                return

            # 2. Bu site için ilk çalıştırma mı?
            total_in_db = self.db.get_total_announcements(site_name=site_name)
            
            if total_in_db == 0 and announcements:
                # --- İLK ÇALIŞTIRMA MANTIĞI ---
                log_info(f"✨ [{site_name}]: Veritabanı boş. İlk çalıştırma ayarlanıyor.")
                new_count = self._process_first_run(scraper, site_config, announcements)
            else:
                # --- NORMAL ÇALIŞTIRMA MANTIĞI ---
                new_count, updated_count = self._process_normal_run(scraper, site_config, announcements)

            # --- GÖREV TAMAMLANDI ---
            log_task_finish(site_name, new_count, updated_count)
            
        # _run_check'in çökmemesi kritik, bu yüzden broad-except
        except Exception as e:
            log_critical(f"🚨 [{site_name}] GÖREVİNDE BÜYÜK HATA: {e}", exc_info=True)
                
    def _process_first_run(self, scraper: BaseScraper, site_config: Dict, announcements: List[Dict]) -> int:
        """
        İlk çalıştırma: DB'yi spam'sız doldurma.
        
        Scraper'dan gelen tüm duyuruları alır.
        (FIRST_RUN_FETCH_LIMIT) kadarını db ekler.
        Returns:
            Gönderilen duyuru sayısı (int).
        """
        limit_to_save = bot_config.FIRST_RUN_FETCH_LIMIT
        limit_to_send = bot_config.FIRST_RUN_SEND_LIMIT
        
        # 'announcements' listesi en yeniden eskiye sıralı varsayılıyor.
        # Sadece kaydetmek istediğimiz kadarını al
        announcements_to_save = announcements[:limit_to_save]
        
        total_found = len(announcements)
        total_to_save = len(announcements_to_save)
        
        log_info(f"✨ [{scraper.name}] Sayfada {total_found} duyuru bulundu. Sadece en yeni {total_to_save} tanesi DB'ye ekleniyor...")
        
        for ann in announcements_to_save:
            try:
                # content_text ham HTML veya None olabilir
                content_text = scraper.fetch_announcement_content(ann['url'])
                ann['content'] = content_text
                self.db.save_announcement(scraper.name, ann)
            except Exception as e:
                log_error(f"❌ [{scraper.name}] (İlk Çalıştırma) Kaydetme/Çekme hatası: {e} - URL: {ann['url']}")
                
        log_info(f"✨ [{scraper.name}]: Toplam {total_to_save} duyuru DB'ye eklendi. En son {limit_to_send} tanesi gönderiliyor.")
        
        sent_count = 0
    
        # Gönderilecekler, 'announcements_to_save' listesinin içinden ilk 'limit_to_send' kadar olmalı
        # reversed() kullanıyoruz ki (eğer 1'den fazla gönderilecekse) eskiden yeniye gitsin.
        for ann in reversed(announcements_to_save[:limit_to_send]):
            send_to_telegram(
                channel_id=site_config['telegram_channel_id'],
                site_name=scraper.name,
                announcement=ann,
                message_type='new'
            )
            sent_count += 1
            
        return sent_count     
    
    def _process_normal_run(self, scraper: BaseScraper, site_config: Dict, announcements: List[Dict]) -> Tuple[int, int]:
        """
        Normal çalıştırma: Yeni/güncel duyuruları kontrol eder.
        
        Liste ters çevrilir (eskiden yeniye) ve DB ile karşılaştırılır:
        1. DB'de yoksa -> YENİ (fetch_content, save, send).
        2. DB'de varsa -> GÜNCELLEME KONTROLÜ (_check_announcement_update).
        
        Returns:
            (yeni_sayısı, güncel_sayısı) tuple'ı.
        """
        new_announcements_count = 0
        updated_announcements_count = 0
        site_name = scraper.name
        
        # 1. Listeyi ters çevir (eskiden yeniye doğru kontrol etmek için)
        reversed_ann_list = list(reversed(announcements))

        # 2. Config'den TOPLAM limiti al
        total_check_limit = bot_config.NORMAL_RUN_TOTAL_CHECK_LIMIT
        
        # 3. Eskiden-yeniye listenin SADECE son 'X' tanesini al
        announcements_to_check = reversed_ann_list[-total_check_limit:]
        
        # 4. Döngü ve hash hesabı için limitleri ayarla
        total_being_checked = len(announcements_to_check)
        recent_announcements_limit = bot_config.NORMAL_RUN_UPDATE_CHECK_LIMIT
        
        log_debug(f"[{site_name}] Normal çalıştırma: Sayfadaki {len(announcements)} duyurudan {total_being_checked} tanesi (son {recent_announcements_limit} tanesinin içeriği) kontrol edilecek.")
        
        # 5. Artık 'reversed_ann_list' yerine 'announcements_to_check' listesi üzerinde dön
        for index, ann in enumerate(announcements_to_check):
            ann_id = ann.get('id')
            if not ann_id:
                log_warning(f"⚠️ [{site_name}]: ID'siz duyuru bulundu, atlanıyor: {ann.get('title')}")
                continue
            
            # DB'de bu ID var mı?
            db_record = self.db.get_announcement_by_id(site_name, ann_id)
            
            if db_record is None:
                # --- DURUM 1: YENİ DUYURU ---
                # NOT: Bu durum, 'NORMAL_RUN_TOTAL_CHECK_LIMIT' ayarı
                # 'FIRST_RUN_FETCH_LIMIT' ayarından küçük olduğu sürece
                # (ve site 10 duyurudan fazlasını birden yayınlamadığı sürece)
                # "eski" duyurular için tetiklenmemelidir.
                
                log_new_announcement(site_name, ann.get('title', 'Başlıksız'))
                try:
                    # Yeni duyurunun içeriğini çek
                    content_text = scraper.fetch_announcement_content(ann['url'])
                    ann['content'] = content_text
                except Exception as e:
                    log_error(f"❌ [{site_name}] (Yeni) İçerik çekilemedi: {ann['url']}, hata: {e}")
                    ann['content'] = None # İçerik olmasa da başlık hash'i ile kaydet
                
                # DB'ye kaydet (eğer zaten eklenmediyse True döner)
                # save_announcement None içeriği ve başlıktan hash'i yönetir
                if self.db.save_announcement(site_name, ann):
                    send_to_telegram(
                        channel_id=site_config['telegram_channel_id'],
                        site_name=site_name,
                        announcement=ann,
                        message_type='new'
                    )
                    new_announcements_count += 1
            
            else:
                # --- DURUM 2: MEVCUT DUYURU (Güncelleme kontrolü) ---
                
                # Optimizasyon: Sadece sayfadaki "en yeni Y" duyurunun içeriğini kontrol et
                is_recent = (index >= total_being_checked - recent_announcements_limit)
                is_updated, updated_content = self._check_announcement_update(scraper, ann, db_record, is_recent)
                
                if is_updated:
                    ann['content'] = updated_content # Mesaj için içeriği (None veya str) ekle
                    
                    # DB'deki hash'i güncelle
                    new_hash = self.db.generate_hash(
                        updated_content, 
                        fallback_text=ann['title']
                    )
                    
                    # DB'yi (hem hash hem raw_content ile) güncelle
                    self.db.update_announcement(
                        site_name=site_name, 
                        announcement_id=ann_id, 
                        new_title=ann['title'], 
                        new_hash=new_hash,
                        new_raw_content=updated_content # Bu None veya ham HTML olabilir
                    )
                    
                    send_to_telegram(
                        channel_id=site_config['telegram_channel_id'],
                        site_name=site_name,
                        announcement=ann,
                        message_type='update'
                    )
                    updated_announcements_count += 1
                    
        return new_announcements_count, updated_announcements_count    

    def _check_announcement_update(self, scraper: BaseScraper, ann: Dict, db_record: Dict, is_recent: bool) -> Tuple[bool, Optional[str]]:
        """
        Bir duyurunun başlığının veya içeriğinin güncellenip güncellenmediğini kontrol eder.
        
        Optimizasyon: 
        İçerik (hash) kontrolü sadece 'is_recent' (örn: son X) ise yapılır. 
        Başlık kontrolü her zaman yapılır.
        
        Returns: 
            (bool: Güncelleme bulundu mu?, Optional[str]: Çekilen içerik (eğer çekildiyse veya None))
        """
        new_title = ann['title']
        content_text: Optional[str] = None
        update_found = False

        # 1. Başlık kontrolü (Her zaman, HTTP isteği gerekmez)
        if new_title != db_record['title']:
            log_info(f"🔄 [{scraper.name}] BAŞLIK GÜNCELLENDİ: {ann['id']}")
            update_found = True
        
        # 2. "Son X" kuralı: Sadece son X ise İÇERİK kontrolü yap (HTTP isteği)
        if is_recent:
            try:
                log_debug(f"🌐 [{scraper.name}] (Son {bot_config.NORMAL_RUN_UPDATE_CHECK_LIMIT}) İçerik kontrolü yapılıyor: {ann['id']}")
                content_text = scraper.fetch_announcement_content(ann['url'])
                
                # İçerik None ise başlığı fallback olarak kullanarak hash'le
                new_hash = self.db.generate_hash(
                    content_text,
                    fallback_text=new_title # Başlığın yenisini kullan
                )
                
                if new_hash != db_record['content_hash']:
                    log_info(f"🔄 [{scraper.name}] İÇERİK GÜNCELLENDİ: {ann['id']}")    
                    update_found = True
                    
            except Exception as e:
                log_debug(f"❌ [{scraper.name}] (Son {bot_config.NORMAL_RUN_UPDATE_CHECK_LIMIT}) İçerikten birisi çekilemedi: {ann['url']}")

        # 3. Güncelleme BAŞLIKTA bulunduysa, ama 'is_recent' olmadığı için
        # içerik henüz çekilmediyse, Telegram'a göndermek için içeriği şimdi çek.
        if update_found and content_text is None and not is_recent:
            try:
                log_debug(f"🌐 [{scraper.name}] (Başlık günc.) İçerik çekiliyor: {ann['id']}")
                content_text = scraper.fetch_announcement_content(ann['url'])
            except Exception as e:
                log_error(f"🛑 [{scraper.name}] (Başlık Günc.) İçerik çekilemedi: {ann['url']}, hata: {e}")
                content_text = None  # Hata durumunda None
        
        return update_found, content_text
