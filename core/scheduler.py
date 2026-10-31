# core/scheduler.py
"""
APScheduler kullanarak görev zamanlaması (Orkestrasyon).

Bu modül, `DuyuruScheduler` sınıfını içerir. Bu sınıfın sorumlulukları:
1. `bot_config`'i okuyarak tüm aktif scraper'ları dinamik olarak yüklemek.
2. `APScheduler`'ı başlatmak ve her scraper için periyodik cron görevi zamanlamak
    (başlangıçta kademeli ilk çalışma ile birlikte).
3. `_run_check` metodu ile scraper'ları tetiklemek, DB'yi kontrol etmek.
4. Yeni/güncel duyuruları `telegram_bot`'a göndermek.
5. `shutdown` ile tüm kaynakları (DB, session'lar, thread'ler) güvenle kapatmak.
"""

import importlib
from datetime import datetime, timedelta
from typing import Dict, List, NamedTuple, Optional, Tuple
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
        'scrapers.Scraper.Scraper1' -> Scraper1 class'ını döndürür.
        
    Returns:
        Yüklenen Class nesnesi.
    """
    try:
        # Yolu, modül ve class adı olarak ayırır
        # (örn: 'scrapers.Scraper', 'Scraper1')
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

class UpdateCheckResult(NamedTuple):
    """`_check_announcement_update` sonucu."""
    is_updated: bool             # Telegram'a "güncellendi" bildirimi gönderilecek mi?
    needs_save: bool             # DB'ye yazılacak mı? (bildirimsiz referans kaydı dahil)
    content_hash: str            # DB'ye yazılacak hash
    raw_content: Optional[str]   # DB'ye yazılacak ham HTML (veya None)

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
        self.scheduler = BackgroundScheduler()  # Sunucunun yerel zaman dilimini kullanır
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
                
                # 'scrapers.Scraper.Scraper1' yolundan Scraper1 class'ını import et
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
        
        Her site için `CronTrigger` tabanlı tek bir görev tanımlanır.
        `next_run_time` parametresi ile bot açılışında kademeli ilk çalıştırma
        sağlanır; ardından görev belirlenen cron dakikalarında periyodik olarak devam eder.
        `max_instances=1` ve `coalesce=True` ile aynı scraper'ın eşzamanlı çalışması engellenir.
        """
        if not self.scrapers:
            log_warning("⚠️ Scheduler | Hiç aktif scraper bulunamadı. Lütfen bot_config.py dosyasını kontrol edin.")
            return

        log_info("⏰ Scheduler | Zamanlayıcı görevleri ayarlanıyor...")
        
        # Botun ilk görevini çalıştırması için başlangıç gecikmesi (saniye)
        # Görevlerin birbirini boğmaması için kademeli başlatma (stagger) yapılır
        initial_run_delay_seconds = 2
        
        for site_name, data in self.scrapers.items():
            site_config = data['config']
            scraper_instance = data['instance']
            minutes = ','.join(site_config['schedule_minutes'])
            
            # İlk çalıştırma zamanı (kademeli gecikme ile)
            first_run_time = datetime.now() + timedelta(seconds=initial_run_delay_seconds)
            
            self.scheduler.add_job(
                self._run_check,
                trigger=CronTrigger(minute=minutes, hour='*'),
                args=[site_name, scraper_instance, site_config],
                id=f"check_{site_name}",
                name=f"Check_{site_name}",
                next_run_time=first_run_time,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=120
            )
            log_info(f"📅 Scheduler | Görev eklendi: [{site_name}] (Her saatin {minutes} dakikalarında, ilk çalışma: {first_run_time.strftime('%H:%M:%S')})")
            
            # Bir sonraki scraper'ın ilk çalıştırması için kademeli gecikme
            initial_run_delay_seconds += 5
            
        # Tüm görevler eklendi, şimdi scheduler'ı BAŞLAT
        self.scheduler.start()
        log_info("⏳ Scheduler | Zamanlayıcı BAŞLATILDI. Görevler arkaplanda çalışacak.")

    def shutdown(self):
        """
        Scheduler'ı ve kaynakları (DB, session'lar, async loop) güvenli bir şekilde kapatır.
        
        `bot_main.py`'deki signal_handler (CTRL+C) tarafından çağrılır.
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
                    
    def _run_check(self, site_name: str, scraper: BaseScraper, site_config: Dict):
        """
        Bir site için kontrol işlemini yürüten ana fonksiyon (APScheduler bunu tetikler).
        
        1. `scraper.scrape()` ile duyuru listesini çeker.
        2. DB'de bu site için kayıt olup olmadığını kontrol eder.
        3. DB boşsa (`total_in_db == 0`): `_process_first_run`'ı çalıştırır.
        4. DB doluysa: `_process_normal_run`'ı çalıştırır.
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
        İlk çalıştırma: Veritabanını başlangıç verisiyle doldurur ve en güncel duyuruları gönderir.
        
        Scraper'dan gelen duyurulardan `FIRST_RUN_FETCH_LIMIT` kadarı işlenir:
        - Bildirim gönderilmeyecek eski duyurular doğrudan veritabanına kaydedilir.
        - Bildirim gönderilecek en yeni `FIRST_RUN_SEND_LIMIT` duyuru ise yalnızca
          Telegram gönderimi başarılı olduğunda veritabanına kaydedilir.
        
        Returns:
            Başarıyla gönderilen duyuru sayısı (int).
        """
        limit_to_save = bot_config.FIRST_RUN_FETCH_LIMIT
        limit_to_send = bot_config.FIRST_RUN_SEND_LIMIT
        
        # 'announcements' listesi en yeniden eskiye sıralı varsayılıyor
        announcements_to_process = announcements[:limit_to_save]
        
        total_found = len(announcements)
        total_to_process = len(announcements_to_process)
        
        log_info(f"✨ [{scraper.name}] Sayfada {total_found} duyuru bulundu. En yeni {total_to_process} tanesi işleniyor...")
        
        for ann in announcements_to_process:
            try:
                # content_text ham HTML veya None olabilir
                content_text = scraper.fetch_announcement_content(ann['url'])
                ann['content'] = content_text
            except Exception as e:
                log_error(f"❌ [{scraper.name}] (İlk Çalıştırma) İçerik çekme hatası: {e} - URL: {ann['url']}")
                ann['content'] = None  # İçerik çekilemese de başlık hash'i ile kaydet
        
        # Gönderilecek (en yeni) ve sadece kaydedilecek (daha eski) duyuruları ayır
        announcements_to_send = announcements_to_process[:limit_to_send]
        announcements_seed_only = announcements_to_process[limit_to_send:]
        
        saved_count = 0
        for ann in announcements_seed_only:
            if self.db.save_announcement(scraper.name, ann):
                saved_count += 1
        
        sent_count = 0
        # Birden fazla duyuru gönderilecekse eskiden yeniye doğru sırala
        for ann in reversed(announcements_to_send):
            is_sent = send_to_telegram(
                channel_id=site_config['telegram_channel_id'],
                site_name=scraper.name,
                announcement=ann,
                message_type='new'
            )
            if is_sent:
                if self.db.save_announcement(scraper.name, ann):
                    saved_count += 1
                sent_count += 1
            else:
                log_warning(f"⚠️ [{scraper.name}] İlk çalıştırma duyurusu gönderilemedi, sonraki turda tekrar denenecek: {ann.get('id')}")
                
        log_info(f"✨ [{scraper.name}]: {saved_count}/{total_to_process} duyuru DB'ye eklendi, {sent_count}/{len(announcements_to_send)} duyuru Telegram'a gönderildi.")
        return sent_count     
    
    def _process_normal_run(self, scraper: BaseScraper, site_config: Dict, announcements: List[Dict]) -> Tuple[int, int]:
        """
        Normal çalıştırma: Yeni/güncel duyuruları kontrol eder.
        
        Liste ters çevrilir (eskiden yeniye) ve DB ile karşılaştırılır:
        1. DB'de yoksa -> YENİ (içeriği çek, Telegram'a gönder, başarılıysa DB'ye kaydet).
        2. DB'de varsa -> GÜNCELLEME KONTROLÜ (_check_announcement_update).
           Bildirim gerektiren güncellemeler yalnızca Telegram gönderimi başarılıysa DB'ye işlenir.
        
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
            
            # DB'de bu ID (veya aynı URL) var mı?
            db_record = self.db.get_announcement_by_id(site_name, ann_id, url=ann.get('url'))
            
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
                
                # Önce Telegram'a gönder; yalnızca başarılı olursa DB'ye kaydet
                is_sent = send_to_telegram(
                    channel_id=site_config['telegram_channel_id'],
                    site_name=site_name,
                    announcement=ann,
                    message_type='new'
                )
                if is_sent:
                    if self.db.save_announcement(site_name, ann):
                        new_announcements_count += 1
                else:
                    log_warning(f"⚠️ [{site_name}] Yeni duyuru gönderilemedi, sonraki turda tekrar denenecek: {ann_id}")
            
            else:
                # --- DURUM 2: MEVCUT DUYURU (Güncelleme kontrolü) ---
                
                # Optimizasyon: Sadece sayfadaki "en yeni Y" duyurunun içeriğini kontrol et
                is_recent = (index >= total_being_checked - recent_announcements_limit)
                check = self._check_announcement_update(scraper, ann, db_record, is_recent)
                
                if check.is_updated:
                    ann['content'] = check.raw_content # Mesaj için içeriği (None veya str) ekle
                    is_sent = send_to_telegram(
                        channel_id=site_config['telegram_channel_id'],
                        site_name=site_name,
                        announcement=ann,
                        message_type='update'
                    )
                    if is_sent:
                        self.db.update_announcement(
                            site_name=site_name, 
                            announcement_id=ann_id, 
                            new_title=ann['title'], 
                            new_hash=check.content_hash,
                            new_raw_content=check.raw_content,
                            new_url=ann.get('url')
                        )
                        updated_announcements_count += 1
                    else:
                        log_warning(f"⚠️ [{site_name}] Güncelleme bildirimi gönderilemedi, sonraki turda tekrar denenecek: {ann_id}")
                elif check.needs_save:
                    # Bildirimsiz referans kaydı
                    self.db.update_announcement(
                        site_name=site_name, 
                        announcement_id=ann_id, 
                        new_title=ann['title'], 
                        new_hash=check.content_hash,
                        new_raw_content=check.raw_content,
                        new_url=ann.get('url')
                    )
                    
        return new_announcements_count, updated_announcements_count    

    def _check_announcement_update(self, scraper: BaseScraper, ann: Dict, db_record: Dict, is_recent: bool) -> UpdateCheckResult:
        """
        Bir duyurunun başlığının veya içeriğinin güncellenip güncellenmediğini kontrol eder.
        
        Optimizasyon: 
        İçerik (hash) kontrolü sadece 'is_recent' (örn: son X) ise veya başlık
        değiştiyse yapılır. Başlık kontrolü her zaman yapılır.
        
        İçerik açısından yalnızca "mevcut içerik -> farklı içerik" değişimi
        güncelleme sayılır:
        - İçerik çekilemezse (ağ hatası): içerik kontrolü atlanır, DB'deki
          hash/içerik korunur.
        - DB'de içerik yok, şimdi geldi: sessizce referans olarak kaydedilir
          (önceki çekim başarısız olmuş olabilir), bildirim gönderilmez.
        - DB'de içerik var, şimdi 'icerik-govde' bulunamadı: geçici/hatalı sayfa
          olabilir, önceki içerik korunur, bildirim gönderilmez.
        
        Returns: 
            UpdateCheckResult (bildirim gerekip gerekmediği ve DB'ye yazılacak değerler).
        """
        new_title = ann['title']
        old_hash = db_record['content_hash']
        old_raw = db_record.get('raw_content')
        
        # Varsayılan: DB'deki mevcut değerleri koru
        final_hash, final_raw = old_hash, old_raw
        content_changed = False
        baseline_only = False

        # 1. Başlık kontrolü (Her zaman, HTTP isteği gerekmez)
        title_changed = new_title != db_record['title']
        if title_changed:
            log_info(f"🔄 [{scraper.name}] BAŞLIK GÜNCELLENDİ: {ann['id']}")
        
        # 2. İçerik kontrolü: Sadece "son X" ise veya başlık değiştiyse (HTTP isteği)
        if is_recent or title_changed:
            try:
                log_debug(f"🌐 [{scraper.name}] İçerik kontrolü yapılıyor: {ann['id']}")
                content_text = scraper.fetch_announcement_content(ann['url'])
            except Exception as e:
                # İçerik çekilemedi: karşılaştırma yapılmaz, mevcut değerler korunur
                log_warning(f"⚠️ [{scraper.name}] İçerik çekilemedi, içerik kontrolü atlanıyor: {ann['url']}, hata: {e}")
            else:
                if content_text is None:
                    # Sayfa geldi ama içerik div'i yok
                    if old_raw:
                        log_warning(f"⚠️ [{scraper.name}] İçerik bulunamadı (önceden vardı), önceki içerik korunuyor: {ann['id']}")
                else:
                    new_hash = self.db.generate_hash(content_text)
                    if not old_raw:
                        # DB'de karşılaştırılacak içerik yok: bildirimsiz referans kaydı
                        log_debug(f"📝 [{scraper.name}] İçerik ilk kez alındı, referans olarak kaydediliyor (bildirimsiz): {ann['id']}")
                        baseline_only = True
                    elif new_hash != old_hash:
                        log_info(f"🔄 [{scraper.name}] İÇERİK GÜNCELLENDİ: {ann['id']}")
                        content_changed = True
                    final_hash, final_raw = new_hash, content_text
        
        is_updated = title_changed or content_changed
        return UpdateCheckResult(
            is_updated=is_updated,
            needs_save=is_updated or baseline_only,
            content_hash=final_hash,
            raw_content=final_raw,
        )
