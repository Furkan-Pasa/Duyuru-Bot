# core/database.py
"""
SQLite veritabanı işlemleri (CRUD) modülü.

Bu sınıf, duyuruların SQLite veritabanına kaydedilmesi,
kontrol edilmesi, bildirim kuyruğunun yönetilmesi ve sorgulanması
işlemlerini yönetir.

Eşzamanlılık: Paylaşılan tek bir SQLite bağlantısı (WAL modunda) kullanılır
ve tüm veritabanı işlemleri `threading.RLock` ile korunur.
"""

import os
import sqlite3
import hashlib
import threading
from typing import Dict, List, Optional

import bot_config
from core.logger import log_debug, log_info, log_critical, log_database_error

# Veritabanı şema sürümü (PRAGMA user_version)
SCHEMA_VERSION = 1

# Zaman damgaları SQLite'ın CURRENT_TIMESTAMP değeriyle (UTC) tutulur.
SCHEMA_SQL = '''
    CREATE TABLE IF NOT EXISTS announcements (
        id                   INTEGER PRIMARY KEY,
        site_key             TEXT NOT NULL,     -- Config'deki kalıcı site anahtarı
        announcement_id      TEXT NOT NULL,     -- Sitedeki duyuru kimliği
        title                TEXT NOT NULL,
        url                  TEXT NOT NULL,
        published_date       TEXT,              -- Yayın tarihi (ISO YYYY-MM-DD)
        content_text         TEXT,              -- Normalize edilmiş duyuru içeriği
        content_hash         TEXT,              -- İçeriğin SHA-256 hash'i (NULL: içerik bilinmiyor)
        pending_notification TEXT CHECK (pending_notification IN ('new', 'update')),  -- Gönderim bekleyen bildirim tipi
        notify_attempts      INTEGER NOT NULL DEFAULT 0,                              -- Başarısız gönderim denemesi sayısı
        first_seen_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at           TEXT,              -- Son başlık/içerik değişikliği
        notified_at          TEXT,              -- Son başarılı Telegram gönderimi
        UNIQUE (site_key, announcement_id)
    )
'''

PENDING_INDEX_SQL = '''
    CREATE INDEX IF NOT EXISTS idx_announcements_pending
        ON announcements (site_key, id)
        WHERE pending_notification IS NOT NULL
'''


class Database:
    def __init__(self):
        """Veritabanı yolunu ayarlar, klasörü (yoksa) oluşturur ve şemayı hazırlar."""
        self.db_path = bot_config.DATABASE_PATH
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None

        self._ensure_directory()
        self._create_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        """
        Paylaşılan SQLite bağlantısını (yoksa WAL modunda açarak) döndürür.

        Thread-safe erişim için `self._lock` ile korunur; `close()` sonrasında
        yeniden erişilirse bağlantı otomatik olarak yeniden açılır.
        """
        with self._lock:
            if self._conn is None:
                try:
                    connection = sqlite3.connect(
                        self.db_path,
                        check_same_thread=False
                    )
                    connection.row_factory = sqlite3.Row
                    connection.execute("PRAGMA journal_mode=WAL")
                    self._conn = connection
                    log_debug("✅ DB Bağlantısı (WAL modu) oluşturuldu.")
                except Exception as e:
                    log_database_error("🛑 Veritabanı bağlantı", e)
                    raise
            return self._conn

    def _ensure_directory(self):
        """Veritabanı dosyasının bulunacağı klasörü (yoksa) oluşturur."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir)
                log_debug(f"📁 '{db_dir}' klasörü otomatik olarak oluşturuldu.")
            except Exception as e:
                log_critical(f"🛑 '{db_dir}' klasörü oluşturulamadı: {e}")
                raise

    def _create_schema(self):
        """'announcements' tablosunu, kısmi kuyruk indeksini ve şema sürümünü oluşturur."""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute(SCHEMA_SQL)
                cursor.execute(PENDING_INDEX_SQL)
                cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self.conn.commit()
                log_debug(f"✅ Veritabanı şeması hazır (v{SCHEMA_VERSION})")
            except Exception as e:
                log_database_error("🛑 Şema oluşturma", e)
                raise

    def save_announcement(self, site_key: str, announcement: Dict, pending: Optional[str]) -> bool:
        """
        Yeni bir duyuruyu veritabanına kaydeder.

        'INSERT OR IGNORE' kullanır; (site_key, announcement_id) çifti zaten
        kayıtlıysa işlem yapılmaz. İçerik yoksa `content_hash` NULL kalır.

        Args:
            site_key: Config'deki site anahtarı (örn: 'bseu_bilgisayar').
            announcement: Scraper'dan gelen duyuru sözlüğü ('content' None olabilir).
            pending: Bildirim kuyruğuna alınacaksa 'new'; bildirimsiz kayıt için None.

        Returns:
            bool: Yeni kayıt eklendiyse True, kayıt zaten varsa veya hata olduysa False.
        """
        content = announcement.get('content')
        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO announcements
                        (site_key, announcement_id, title, url, published_date,
                         content_text, content_hash, pending_notification)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    site_key,
                    announcement['id'],
                    announcement['title'],
                    announcement['url'],
                    announcement.get('date') or None,
                    content,
                    self.generate_hash(content),
                    pending,
                ))
                self.conn.commit()
                return cursor.rowcount > 0

            except Exception as e:
                log_database_error(f"🛑 Duyuru kaydetme ({announcement.get('id')})", e)
                self.conn.rollback()
                return False

    def get_announcement_by_id(self, site_key: str, announcement_id: str) -> Optional[Dict]:
        """
        Belirli bir duyuruyu (site anahtarı ve duyuru ID'si ile) veritabanından çeker.

        Args:
            site_key: Config'deki site anahtarı.
            announcement_id: Duyuru ID'si.

        Returns:
            Duyuru bilgileri (dict) veya bulunamazsa None.
        """
        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT * FROM announcements
                    WHERE site_key = ? AND announcement_id = ?
                ''', (site_key, announcement_id))
                row = cursor.fetchone()
                return dict(row) if row else None

            except Exception as e:
                log_database_error("🛑 Duyuru getirme (by_id)", e)
                return None

    def update_announcement(
        self,
        site_key: str,
        announcement_id: str,
        title: str,
        url: str,
        content_hash: Optional[str],
        content_text: Optional[str],
        queue_update: bool,
    ) -> bool:
        """
        Mevcut bir duyurunun başlığını, URL'ini ve içeriğini günceller.

        Args:
            site_key: Config'deki site anahtarı.
            announcement_id: Duyuru ID'si.
            title: Güncel başlık.
            url: Güncel duyuru URL'i.
            content_hash: Güncel içerik hash'i (içerik bilinmiyorsa None).
            content_text: Güncel içerik (bilinmiyorsa None).
            queue_update: Bildirim gerektiren bir değişiklikse True; `updated_at`
                güncellenir ve kayıt 'update' bildirimi olarak kuyruğa alınır.
                Kayıt zaten kuyruktaysa mevcut bildirim tipi korunur (henüz
                gönderilmemiş bir 'new' bildirimi güncel bilgilerle 'new' olarak gider).
                False ise bildirim gerektirmeyen bir veri tamamlamasıdır
                (örn: içeriğin ilk kez alınması).

        Returns:
            bool: Güncelleme başarılıysa True, değilse False.
        """
        with self._lock:
            try:
                cursor = self.conn.cursor()
                # SET ifadelerinin tamamı satırın güncelleme öncesi değerleriyle hesaplanır.
                cursor.execute('''
                    UPDATE announcements
                    SET title                = :title,
                        url                  = :url,
                        content_hash         = :content_hash,
                        content_text         = :content_text,
                        updated_at           = CASE WHEN :queue THEN CURRENT_TIMESTAMP ELSE updated_at END,
                        notify_attempts      = CASE WHEN :queue AND pending_notification IS NULL
                                                    THEN 0 ELSE notify_attempts END,
                        pending_notification = CASE WHEN :queue
                                                    THEN COALESCE(pending_notification, 'update')
                                                    ELSE pending_notification END
                    WHERE site_key = :site_key AND announcement_id = :announcement_id
                ''', {
                    'title': title,
                    'url': url,
                    'content_hash': content_hash,
                    'content_text': content_text,
                    'queue': queue_update,
                    'site_key': site_key,
                    'announcement_id': announcement_id,
                })
                self.conn.commit()
                return cursor.rowcount > 0

            except Exception as e:
                log_database_error(f"🛑 Duyuru güncelleme ({announcement_id})", e)
                self.conn.rollback()
                return False

    def get_pending_notifications(self, site_key: str) -> List[Dict]:
        """
        Sitenin bildirim kuyruğundaki kayıtlarını kayıt sırasıyla döndürür.

        Args:
            site_key: Config'deki site anahtarı.

        Returns:
            Kuyruktaki duyuruların listesi (hata durumunda boş liste).
        """
        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT * FROM announcements
                    WHERE site_key = ? AND pending_notification IS NOT NULL
                    ORDER BY id
                ''', (site_key,))
                return [dict(row) for row in cursor.fetchall()]

            except Exception as e:
                log_database_error("🛑 Bildirim kuyruğu getirme", e)
                return []

    def mark_notification_sent(self, row_id: int) -> None:
        """Başarıyla gönderilen bildirimi kuyruktan çıkarır ve `notified_at` değerini günceller."""
        with self._lock:
            try:
                self.conn.execute('''
                    UPDATE announcements
                    SET pending_notification = NULL,
                        notify_attempts      = 0,
                        notified_at          = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (row_id,))
                self.conn.commit()

            except Exception as e:
                log_database_error(f"🛑 Bildirim gönderildi işaretleme (id={row_id})", e)
                self.conn.rollback()

    def record_notification_failure(self, row_id: int) -> int:
        """
        Başarısız bir gönderim denemesini kaydeder.

        Returns:
            Güncel başarısız deneme sayısı (hata durumunda 0).
        """
        with self._lock:
            try:
                self.conn.execute(
                    "UPDATE announcements SET notify_attempts = notify_attempts + 1 WHERE id = ?",
                    (row_id,),
                )
                self.conn.commit()
                row = self.conn.execute("SELECT notify_attempts FROM announcements WHERE id = ?", (row_id,)).fetchone()
                return row['notify_attempts'] if row else 0

            except Exception as e:
                log_database_error(f"🛑 Bildirim denemesi kaydetme (id={row_id})", e)
                self.conn.rollback()
                return 0

    def abandon_notification(self, row_id: int) -> None:
        """Bildirimi kuyruktan çıkarır; başarısız deneme sayısı inceleme için korunur."""
        with self._lock:
            try:
                self.conn.execute("UPDATE announcements SET pending_notification = NULL WHERE id = ?", (row_id,))
                self.conn.commit()

            except Exception as e:
                log_database_error(f"🛑 Bildirimden vazgeçme (id={row_id})", e)
                self.conn.rollback()

    def get_total_announcements(self, site_key: Optional[str] = None) -> int:
        """
        Veritabanındaki toplam duyuru sayısını döndürür.

        Args:
            site_key: Belirli bir site (None ise tüm siteler).

        Returns:
            Toplam duyuru sayısı.
        """
        with self._lock:
            try:
                cursor = self.conn.cursor()
                if site_key:
                    cursor.execute('SELECT COUNT(*) AS count FROM announcements WHERE site_key = ?', (site_key,))
                else:
                    cursor.execute('SELECT COUNT(*) AS count FROM announcements')
                return cursor.fetchone()['count']

            except Exception as e:
                log_database_error("🛑 Sayım (get_total)", e)
                return 0

    @staticmethod
    def generate_hash(text: Optional[str]) -> Optional[str]:
        """
        İçerik için SHA-256 hash üretir.

        Args:
            text: Hash'lenecek içerik (None veya boş olabilir).

        Returns:
            Hex digest; içerik yoksa None (içerik bilinmiyor).
        """
        if not text:
            return None
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def close(self):
        """Açık veritabanı bağlantısını kapatır."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
                log_info("🔒 Veritabanı bağlantısı kapatıldı.")
