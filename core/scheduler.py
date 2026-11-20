# core/scheduler.py
"""
APScheduler kullanarak görev zamanlaması (Orkestrasyon).

Bu modül, `DuyuruScheduler` sınıfını içerir. Bu sınıfın sorumlulukları:
1. `bot_config`'i okuyarak tüm aktif scraper'ları dinamik olarak yüklemek.
2. `APScheduler`'ı başlatmak ve her scraper için periyodik cron görevi zamanlamak
    (başlangıçta kademeli ilk çalışma ile birlikte).
3. `_run_check` metodu ile scraper'ları tetiklemek, DB'yi kontrol etmek.
4. Yeni/güncel duyuruları bildirim kuyruğuna almak ve kuyruğu `telegram_bot` ile göndermek.
5. `shutdown` ile tüm kaynakları (DB, session'lar, thread'ler) güvenle kapatmak.
"""

import importlib
from datetime import datetime, timedelta
from typing import Dict, List, NamedTuple, Optional, Set, Tuple
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler

import bot_config
from core.database import Database
from scrapers.base_scraper import BaseScraper
from core.telegram_bot import send_admin_alert, send_to_telegram, start_telegram_loop, stop_telegram_loop
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
        module_path, class_name = path.rsplit('.', 1)
    except ValueError:
        log_error(f"❌ Geçersiz import yolu: '{path}'. Format: 'paket.modul.ClassAdi'")
        raise

    module = importlib.import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError:
        log_error(f"❌ '{module_path}' modülünde '{class_name}' sınıfı bulunamadı.")
        raise


class UpdateCheckResult(NamedTuple):
    """`_check_announcement_update` sonucu."""
    is_updated: bool             # 'update' bildirimi olarak kuyruğa alınacak mı?
    needs_save: bool             # DB'ye yazılacak mı? (bildirimsiz referans kaydı dahil)
    content_hash: Optional[str]  # DB'ye yazılacak içerik hash'i (içerik bilinmiyorsa None)
    content_text: Optional[str]  # DB'ye yazılacak içerik (bilinmiyorsa None)


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

        # Aktif scraper'ları site anahtarına ('key') göre tutar
        self.scrapers: Dict[str, Dict] = {}
        self._load_scrapers()

        # Arka arkaya başarısız olan taramaları ve yöneticiye bildirilen siteleri izler
        self.failure_counts: Dict[str, int] = {}
        self.alerted_sites: Set[str] = set()

    def _load_scrapers(self):
        """
        `bot_config.SITES` listesini okur, 'enabled' olan scraper'ları
        dinamik olarak import eder ve `self.scrapers`'a yükler.
        """
        log_info("⏳ Scheduler | Scraper'lar yükleniyor...")

        for site_config in bot_config.SITES:
            if not site_config.get('enabled', False):
                log_info(f"⚠️ {site_config['name']} pasif, atlanıyor.")
                continue

            try:
                site_url = site_config.get('url')
                site_name = site_config['name']
                scraper_path = site_config.get('scraper_path')

                if not site_url:
                    log_error(f"❌ {site_name} için config'de 'url' bulunamadı. Atlanıyor.")
                    continue
                if not scraper_path:
                    log_error(f"❌ {site_name} için config'de 'scraper_path' eksik. Atlanıyor.")
                    continue

                ScraperClass = import_from_string(scraper_path)
                scraper_instance: BaseScraper = ScraperClass(url=site_url, name=site_name)

                self.scrapers[site_config['key']] = {
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
        initial_run_delay_seconds = 2

        for site_key, data in self.scrapers.items():
            site_config = data['config']
            scraper_instance = data['instance']
            site_name = site_config['name']
            minutes = ','.join(site_config['schedule_minutes'])

            # İlk çalıştırma zamanı (kademeli gecikme ile)
            first_run_time = datetime.now() + timedelta(seconds=initial_run_delay_seconds)

            self.scheduler.add_job(
                self._run_check,
                trigger=CronTrigger(minute=minutes, hour='*'),
                args=[site_key, scraper_instance, site_config],
                id=f"check_{site_key}",
                name=f"Check_{site_key}",
                next_run_time=first_run_time,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=120
            )
            log_info(f"📅 Scheduler | Görev eklendi: [{site_name}] (Her saatin {minutes} dakikalarında, ilk çalışma: {first_run_time.strftime('%H:%M:%S')})")

            initial_run_delay_seconds += 5

        self.scheduler.start()
        log_info("⏳ Scheduler | Zamanlayıcı BAŞLATILDI. Görevler arkaplanda çalışacak.")

    def shutdown(self):
        """
        Scheduler'ı ve kaynakları (DB, session'lar, async loop) güvenli bir şekilde kapatır.

        `bot_main.py`'deki signal_handler (CTRL+C) tarafından çağrılır.
        """
        log_debug("⏳ Scheduler | Güvenli kapatma başlatıldı...")

        # 1. APScheduler'ı kapat
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                log_debug("🔒 Scheduler | APScheduler görevleri durduruldu.")
        except Exception as e:
            log_error(f"🛑 Scheduler kapatılırken hata: {e}")

        # 2. Async Telegram thread'ini kapat
        stop_telegram_loop()

        # 3. Veritabanı bağlantısını kapat
        try:
            self.db.close()
        except Exception as e:
            log_error(f"🛑 Veritabanı kapatılırken hata: {e}")

        # 4. Tüm scraper'ların 'requests.Session'larını kapat
        log_debug("⏳ Scheduler | Scraper session'ları kapatılıyor...")
        for data in self.scrapers.values():
            try:
                data['instance'].close()
            except Exception as e:
                log_error(f"🛑 [{data['config']['name']}] scraper session kapatılırken hata: {e}")

        log_info("🔒 Scheduler | Tüm kaynaklar serbest bırakıldı. Kapatıldı.")

    def _record_scrape_failure(self, site_key: str, site_name: str, reason: str) -> None:
        """Ardışık tarama hatalarını sayar; eşik aşılınca yöneticiye bir kez uyarı gönderir."""
        count = self.failure_counts.get(site_key, 0) + 1
        self.failure_counts[site_key] = count
        if count >= bot_config.ADMIN_ALERT_THRESHOLD and site_key not in self.alerted_sites:
            self.alerted_sites.add(site_key)
            send_admin_alert(
                f"[{site_name}] art arda {count} kontrolde taranamadı. Son neden: {reason}"
            )

    def _record_scrape_success(self, site_key: str, site_name: str) -> None:
        """Başarılı taramada hata sayacını sıfırlar; önceden uyarı gönderildiyse düzelme bildirir."""
        self.failure_counts[site_key] = 0
        if site_key in self.alerted_sites:
            self.alerted_sites.remove(site_key)
            send_admin_alert(f"[{site_name}] erişimi normale döndü.")

    def _run_check(self, site_key: str, scraper: BaseScraper, site_config: Dict):
        """
        Bir site için kontrol işlemini yürüten ana fonksiyon (APScheduler bunu tetikler).

        1. `scraper.scrape()` ile duyuru listesini çeker.
        2. DB boşsa (`total_in_db == 0`): `_process_first_run`'ı çalıştırır.
        3. DB doluysa: `_process_normal_run`'ı çalıştırır.
        4. `_send_pending` ile bildirim kuyruğunu gönderir. Bu adım, site
           taranamasa bile önceki turlardan kalan bildirimler için çalışır.
        """
        site_name = scraper.name
        log_scraper_start(site_name)

        try:
            announcements = scraper.scrape()

            if not announcements:
                log_warning(f"⚠️ Scheduler | [{site_name}]: Sayfada duyuru bulunamadı.")
                self._record_scrape_failure(
                    site_key,
                    site_name,
                    "Sayfada duyuru bulunamadı veya sayfa çekilemedi."
                )
            else:
                if self.db.get_total_announcements(site_key=site_key) == 0:
                    log_info(f"✨ [{site_name}]: Veritabanı boş. İlk çalıştırma ayarlanıyor.")
                    queued_count = self._process_first_run(scraper, site_config, announcements)
                    log_task_finish(site_name, queued_count, 0)
                else:
                    new_count, updated_count = self._process_normal_run(scraper, site_config, announcements)
                    log_task_finish(site_name, new_count, updated_count)
                self._record_scrape_success(site_key, site_name)

        # _run_check'in çökmemesi kritik, bu yüzden broad-except
        except Exception as e:
            log_critical(f"🚨 [{site_name}] GÖREVİNDE BÜYÜK HATA: {e}", exc_info=True)
            self._record_scrape_failure(site_key, site_name, f"Beklenmeyen tarama hatası: {e}")

        try:
            self._send_pending(site_key, site_name, site_config)
        except Exception as e:
            log_critical(f"🚨 [{site_name}] Bildirim kuyruğu işlenirken hata: {e}", exc_info=True)

    def _fetch_content(self, scraper: BaseScraper, ann: Dict) -> Optional[str]:
        """
        Yeni bir duyurunun içeriğini çeker.

        Returns:
            Normalize edilmiş içerik; çekilemezse None (içerik bilinmiyor olarak kaydedilir).
        """
        try:
            return scraper.fetch_announcement_content(ann['url'])
        except Exception as e:
            log_error(f"❌ [{scraper.name}] İçerik çekilemedi: {ann['url']}, hata: {e}")
            return None

    def _process_first_run(self, scraper: BaseScraper, site_config: Dict, announcements: List[Dict]) -> int:
        """
        İlk çalıştırma: Veritabanını başlangıç verisiyle doldurur.

        Scraper'dan gelen duyurulardan en yeni `FIRST_RUN_FETCH_LIMIT` kadarı kaydedilir.
        Bunlardan en yeni `FIRST_RUN_SEND_LIMIT` tanesi 'new' bildirimi olarak kuyruğa
        alınır, diğerleri bildirimsiz kaydedilir; böylece kanal eski duyurularla dolmaz.

        Returns:
            Bildirim kuyruğuna alınan duyuru sayısı (int).
        """
        site_key = site_config['key']
        send_limit = bot_config.FIRST_RUN_SEND_LIMIT

        # 'announcements' listesi en yeniden eskiye sıralı varsayılıyor
        announcements_to_save = announcements[:bot_config.FIRST_RUN_FETCH_LIMIT]
        log_info(f"✨ [{scraper.name}] Sayfada {len(announcements)} duyuru bulundu. En yeni {len(announcements_to_save)} tanesi kaydediliyor...")

        saved_count = 0
        queued_count = 0
        # Kayıtlar eskiden yeniye eklenir; kuyruk kayıt sırasıyla gönderildiği için
        # birden fazla bildirim kronolojik sırada gider.
        for index in reversed(range(len(announcements_to_save))):
            ann = announcements_to_save[index]
            ann['content'] = self._fetch_content(scraper, ann)
            pending = 'new' if index < send_limit else None
            if self.db.save_announcement(site_key, ann, pending=pending):
                saved_count += 1
                if pending:
                    queued_count += 1

        log_info(f"✨ [{scraper.name}]: {saved_count}/{len(announcements_to_save)} duyuru DB'ye eklendi, {queued_count} tanesi bildirim kuyruğuna alındı.")
        return queued_count

    def _process_normal_run(self, scraper: BaseScraper, site_config: Dict, announcements: List[Dict]) -> Tuple[int, int]:
        """
        Normal çalıştırma: Yeni/güncel duyuruları kontrol eder.

        Liste ters çevrilir (eskiden yeniye) ve DB ile karşılaştırılır:
        1. DB'de yoksa -> YENİ: içerik çekilir, kayıt 'new' bildirimi olarak kuyruğa alınır.
        2. DB'de varsa -> GÜNCELLEME KONTROLÜ (_check_announcement_update):
           bildirim gerektiren değişiklikler 'update' bildirimi olarak kuyruğa alınır.

        Returns:
            (yeni_sayısı, güncel_sayısı) tuple'ı.
        """
        new_announcements_count = 0
        updated_announcements_count = 0
        site_key = site_config['key']
        site_name = scraper.name

        reversed_ann_list = list(reversed(announcements))
        total_check_limit = bot_config.NORMAL_RUN_TOTAL_CHECK_LIMIT
        announcements_to_check = reversed_ann_list[-total_check_limit:]

        total_being_checked = len(announcements_to_check)
        recent_announcements_limit = bot_config.NORMAL_RUN_UPDATE_CHECK_LIMIT

        log_debug(f"[{site_name}] Normal çalıştırma: Sayfadaki {len(announcements)} duyurudan {total_being_checked} tanesi (son {recent_announcements_limit} tanesinin içeriği) kontrol edilecek.")

        for index, ann in enumerate(announcements_to_check):
            ann_id = ann.get('id')
            if not ann_id:
                log_warning(f"⚠️ [{site_name}]: ID'siz duyuru bulundu, atlanıyor: {ann.get('title')}")
                continue

            db_record = self.db.get_announcement_by_id(site_key, ann_id)

            if db_record is None:
                log_new_announcement(site_name, ann.get('title', 'Başlıksız'))
                ann['content'] = self._fetch_content(scraper, ann)
                if self.db.save_announcement(site_key, ann, pending='new'):
                    new_announcements_count += 1
            else:
                is_recent = (index >= total_being_checked - recent_announcements_limit)
                check = self._check_announcement_update(scraper, ann, db_record, is_recent)

                if check.needs_save:
                    self.db.update_announcement(
                        site_key=site_key,
                        announcement_id=ann_id,
                        title=ann['title'],
                        url=ann['url'],
                        content_hash=check.content_hash,
                        content_text=check.content_text,
                        queue_update=check.is_updated
                    )
                    if check.is_updated:
                        updated_announcements_count += 1

        return new_announcements_count, updated_announcements_count

    def _send_pending(self, site_key: str, site_name: str, site_config: Dict) -> int:
        """
        Sitenin bildirim kuyruğundaki duyuruları kayıt sırasıyla Telegram'a gönderir.

        - Başarılı gönderimde kayıt kuyruktan çıkarılır.
        - Başarısız gönderimde deneme sayısı artırılır ve kuyruğun geri kalanı
          sonraki tura bırakılır: Telegram'a ulaşılamıyorsa sonraki mesajlar da
          başarısız olur, ayrıca gönderim sırası korunur.
        - `MAX_NOTIFY_ATTEMPTS` denemeye ulaşan bildirimden vazgeçilir,
          yönetici uyarılır ve kuyruğun geri kalanıyla devam edilir.

        Returns:
            Başarıyla gönderilen bildirim sayısı.
        """
        pending = self.db.get_pending_notifications(site_key)
        if not pending:
            return 0

        sent_count = 0
        for record in pending:
            announcement = {
                'id': record['announcement_id'],
                'title': record['title'],
                'url': record['url'],
                'date': record['published_date'] or '',
            }
            is_sent = send_to_telegram(
                channel_id=site_config['telegram_channel_id'],
                site_name=site_name,
                announcement=announcement,
                message_type=record['pending_notification']
            )
            if is_sent:
                self.db.mark_notification_sent(record['id'])
                sent_count += 1
                continue

            attempts = self.db.record_notification_failure(record['id'])
            if attempts >= bot_config.MAX_NOTIFY_ATTEMPTS:
                self.db.abandon_notification(record['id'])
                log_critical(f"🚨 [{site_name}] Bildirim {attempts} denemede gönderilemedi, vazgeçildi: {record['title']} ({record['url']})")
                send_admin_alert(
                    f"[{site_name}] Bildirim {attempts} denemede gönderilemediği için vazgeçildi: "
                    f"{record['title']} ({record['url']})"
                )
                continue

            log_warning(f"⚠️ [{site_name}] Bildirim gönderilemedi (deneme {attempts}/{bot_config.MAX_NOTIFY_ATTEMPTS}), kuyruk sonraki turda tekrar denenecek: {record['announcement_id']}")
            break

        log_info(f"📨 [{site_name}] Bildirim kuyruğu: {sent_count}/{len(pending)} gönderildi.")
        return sent_count

    def _check_announcement_update(self, scraper: BaseScraper, ann: Dict, db_record: Dict, is_recent: bool) -> UpdateCheckResult:
        """
        Bir duyurunun başlığının veya içeriğinin güncellenip güncellenmediğini kontrol eder.

        İçerik (hash) kontrolü sadece 'is_recent' (örn: son X) ise veya başlık
        değiştiyse yapılır. Başlık kontrolü her zaman yapılır.

        İçerik açısından yalnızca "bilinen içerik -> farklı içerik" değişimi
        güncelleme sayılır (DB'de `content_hash` NULL ise içerik bilinmiyordur):
        - İçerik çekilemezse (ağ hatası): içerik kontrolü atlanır, DB'deki
          hash/içerik korunur.
        - İçerik bilinmiyordu, şimdi geldi: sessizce referans olarak kaydedilir
          (önceki çekim başarısız olmuş olabilir), bildirim gönderilmez.
        - İçerik biliniyordu, şimdi içerik bloğu bulunamadı: geçici/hatalı sayfa
          olabilir, önceki içerik korunur, bildirim gönderilmez.

        Returns:
            UpdateCheckResult (bildirim gerekip gerekmediği ve DB'ye yazılacak değerler).
        """
        new_title = ann['title']
        old_hash = db_record['content_hash']

        final_hash, final_text = old_hash, db_record['content_text']
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
                    # Sayfa geldi ama içerik bloğu yok
                    if old_hash is not None:
                        log_warning(f"⚠️ [{scraper.name}] İçerik bulunamadı (önceden vardı), önceki içerik korunuyor: {ann['id']}")
                else:
                    new_hash = self.db.generate_hash(content_text)
                    if old_hash is None:
                        # DB'de karşılaştırılacak içerik yok: bildirimsiz referans kaydı
                        log_debug(f"📝 [{scraper.name}] İçerik ilk kez alındı, referans olarak kaydediliyor (bildirimsiz): {ann['id']}")
                        baseline_only = True
                    elif new_hash != old_hash:
                        log_info(f"🔄 [{scraper.name}] İÇERİK GÜNCELLENDİ: {ann['id']}")
                        content_changed = True
                    final_hash, final_text = new_hash, content_text

        is_updated = title_changed or content_changed
        return UpdateCheckResult(
            is_updated=is_updated,
            needs_save=is_updated or baseline_only,
            content_hash=final_hash,
            content_text=final_text,
        )
