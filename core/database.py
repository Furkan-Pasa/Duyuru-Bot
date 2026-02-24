# core/database.py
"""
SQLite veritabanı işlemleri (CRUD) modülü.

Bu sınıf, duyuruların SQLite veritabanına kaydedilmesi,
kontrol edilmesi ve sorgulanması işlemlerini yönetir.

ÖNEMLİ: Thread-safe olması için 'threading.local()' kullanarak
her thread'e (örn: her scraper görevi) özel bir veritabanı bağlantısı sağlar.
"""

import os
import sqlite3
import hashlib
import threading
import bot_config
from typing import Dict, Optional
from core.logger import log_debug, log_info, log_warning, log_critical, log_database_error

class Database:
    def __init__(self):
        """Veritabanı yolunu ayarlar ve tabloları oluşturur/kontrol eder."""
        self.db_path = bot_config.DATABASE_PATH
        self.local_storage = threading.local()  # Thread-local depolama

        # Veritabanı dosyasının bulunduğu 'data' klasörünü kontrol et
        db_dir = os.path.dirname(self.db_path)
        
        # Eğer 'data' klasörü yoksa ve yol boş değilse, oluştur
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir)
                log_debug(f"📁 '{db_dir}' klasörü otomatik olarak oluşturuldu.")
            except Exception as e:
                log_critical(f"🛑 '{db_dir}' klasörü oluşturulamadı: {e}")
                raise

        self.create_tables()
        self._check_and_migrate_db()
    
    @property
    def conn(self) -> sqlite3.Connection:
        """
        Thread'e özel (thread-local) veritabanı bağlantısını yönetir.

        Bu property'ye her thread ilk kez eriştiğinde, o thread için
        yeni bir 'sqlite3.connect' bağlantısı oluşturur ve 'self.local_storage'
        üzerinde saklar. Sonraki erişimlerde mevcut bağlantıyı döndürür.

        Bu, 'BackgroundScheduler'daki her bir scraper iş parçacığının
        kendi izole bağlantısına sahip olmasını sağlar.
        """
        # Bu thread için 'conn' adında bir attribute yoksa
        if not hasattr(self.local_storage, 'conn'):
            try:
                # Yeni bir bağlantı oluştur ve bu thread'in deposuna kaydet
                connection = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False  # Gerekli (bağlantı thread-local)
                )
                connection.row_factory = sqlite3.Row  # Sonuçları dict gibi alabilmek için
                self.local_storage.conn = connection
                log_debug(f"✅ DB Bağlantısı (Thread: {threading.current_thread().name}) oluşturuldu.")
            except Exception as e:
                log_database_error("🛑 Veritabanı bağlantı", e)
                raise
        
        # Bu thread'in özel bağlantısını döndür
        return self.local_storage.conn

    def _check_and_migrate_db(self):
        """
        Veritabanı şemasını kontrol eder ve gerekirse (örn: yeni sütun) günceller.
        'raw_content' sütununun varlığını kontrol eder.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(announcements)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            # Eğer 'raw_content' sütunu yoksa, ekle
            if 'raw_content' not in columns:
                log_warning("⚠️ [DATABASE] 'raw_content' sütunu bulunamadı, tablo güncelleniyor (ALTER TABLE)...")
                cursor.execute("ALTER TABLE announcements ADD COLUMN raw_content TEXT")
                self.conn.commit()
                log_info("✅ [DATABASE] 'raw_content' sütunu eklendi.")
                
        except Exception as e:
            log_database_error("🛑 Veritabanı göç (migration)", e)
            self.conn.rollback()

    def create_tables(self):
        """
        'announcements' tablosunun var olmasını sağlar.
        (IF NOT EXISTS)
        """
        try:
            cursor = self.conn.cursor()
            
            # Ana duyuru tablosu
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    announcement_id TEXT NOT NULL,         -- Scraper'dan gelen ID (örn: '12345')
                    title TEXT NOT NULL,
                    url TEXT,
                    date TEXT,
                    content_hash TEXT,                     -- İçeriğin MD5 hash'i
                    raw_content TEXT,                      -- İçeriğin ham HTML'i (None olabilir)
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(site_name, announcement_id)     -- Bir site_name + ann_id çifti sadece 1 kez
                )
            ''')
            
            self.conn.commit()
            log_debug("✅ Veritabanı tabloları hazır")
        except Exception as e:
            log_database_error("🛑 Tablo oluşturma", e)
            raise
    
    def save_announcement(self, site_name: str, announcement: Dict) -> bool:
        """
        Yeni bir duyuruyu veritabanına kaydeder (veya görmezden gelir).

        'INSERT OR IGNORE' kullanır. Eğer 'UNIQUE(site_name, announcement_id)'
        kısıtlaması ihlal edilirse (kayıt zaten varsa), hata vermez,
        sadece işlem yapmaz ve 'cursor.rowcount' 0 döner.

        'content_hash' oluşturulurken `generate_hash` kullanılır; eğer
        'content' (içerik) yoksa 'title' (başlık) hash'lenir.
        
        Args:
            site_name: Site adı (örn: 'BŞEÜ Bilgisayar Müh.')
            announcement: Scraper'dan gelen duyuru sözlüğü. ('content' ham HTML veya None içerebilir)
            
        Returns:
            bool: Kayıt başarılı (yeni eklendi) ise True,
                  kayıt zaten vardı (ignore edildi) veya hata olduysa False.
        """
        try:
            cursor = self.conn.cursor()
            
            # 'content' None olabilir (örn: içerik bulunamadı)
            raw_html = announcement.get('content')
            
            # İçerik yoksa başlığı hash'le (fallback)
            content_hash = self.generate_hash(
                raw_html, # Bu None ise, fallback kullanılır
                fallback_text=announcement.get('title', '')
            )
            
            cursor.execute('''
                INSERT OR IGNORE INTO announcements
                (site_name, announcement_id, title, url, date, content_hash, raw_content)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                site_name,
                announcement.get('id'),
                announcement.get('title'),
                announcement.get('url'),
                announcement.get('date'),
                content_hash,
                raw_html
            ))
            
            self.conn.commit()
            # rowcount > 0 sadece yeni bir satır eklendiyse True döner
            return cursor.rowcount > 0
            
        except Exception as e:
            log_database_error(f"🛑 Duyuru kaydetme ({announcement.get('id')})", e)
            self.conn.rollback()
            return False
    
    
    def get_announcement_by_id(self, site_name: str, announcement_id: str) -> Optional[Dict]:
        """
        Belirli bir duyuruyu (site adı ve duyuru ID'si ile) veritabanından çeker.
        
        Args:
            site_name: Site adı
            announcement_id: Duyuru ID'si
            
        Returns:
            Duyuru bilgileri (dict) veya bulunamazsa None.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM announcements
                WHERE site_name = ? AND announcement_id = ?
            ''', (site_name, announcement_id))
            
            row = cursor.fetchone()
            # 'sqlite3.Row' nesnesini dict'e çevir
            return dict(row) if row else None
            
        except Exception as e:
            log_database_error("🛑 Duyuru getirme (by_id)", e)
            return None

    def update_announcement(self, site_name: str, announcement_id: str, new_title: str, new_hash: str, new_raw_content: Optional[str]) -> bool:
        """
        Mevcut bir duyurunun başlığını ve/veya hash'ini günceller.
        
        Args:
            site_name: Site adı
            announcement_id: Duyuru ID'si
            new_title: Yeni başlık
            new_hash: Yeni içerik hash'i
            new_raw_content: Yeni ham HTML (veya None)
            
        Returns:
            bool: Güncelleme başarılıysa True, değilse False.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE announcements
                SET title = ?, content_hash = ?, raw_content = ?, created_at = CURRENT_TIMESTAMP
                WHERE site_name = ? AND announcement_id = ?
            ''', (new_title, new_hash, new_raw_content, site_name, announcement_id))
            
            self.conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            log_database_error(f"🛑 Duyuru güncelleme ({announcement_id})", e)
            self.conn.rollback()
            return False

    def get_total_announcements(self, site_name: Optional[str] = None) -> int:
        """
        Veritabanındaki toplam duyuru sayısını döndürür.
        
        Args:
            site_name: Belirli bir site (None ise tüm siteler).
            
        Returns:
            Toplam duyuru sayısı.
        """
        try:
            cursor = self.conn.cursor()
            
            if site_name:
                cursor.execute('SELECT COUNT(*) as count FROM announcements WHERE site_name = ?', (site_name,))
            else:
                cursor.execute('SELECT COUNT(*) as count FROM announcements')
            
            result = cursor.fetchone()
            return result['count']
            
        except Exception as e:
            log_database_error("🛑 Sayım (get_total)", e)
            return 0

    def generate_hash(self, text: Optional[str], fallback_text: str = "") -> str:
        """
        Bir metin için MD5 hash üretir.

        Eğer ana 'text' (genellikle 'content') boş veya None ise,
        'fallback_text'i (genellikle 'title') hash'ler.
        Bu, içeriği çekilemeyen duyuruların (örn: ilk çalıştırma)
        başlık üzerinden takip edilebilmesini sağlar.
        
        Args:
            text: Hash'lenecek ana metin (içerik) (None olabilir)
            fallback_text: 'text' boşsa kullanılacak yedek metin (başlık).
            
        Returns:
            MD5 hash (hex digest).
        """
        data_to_hash = text if text else fallback_text
        return hashlib.md5(data_to_hash.encode('utf-8')).hexdigest()
    
    def close(self):
        """
        Thread'e özel veritabanı bağlantısını kapatır.
        
        Thread-local olduğu için her thread kendi bağlantısını kapatır.
        Aynı thread'den birden fazla çağrılması güvenlidir (hasattr kontrolü).
        """
        # Sadece bu thread'e ait bağlantı varsa kapat
        if hasattr(self.local_storage, 'conn'):
            self.local_storage.conn.close()
            del self.local_storage.conn
            log_info(f"🔒 DB Bağlantısı (Thread: {threading.current_thread().name}) kapatıldı.")