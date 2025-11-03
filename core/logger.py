# core/logger.py
"""
Merkezi Logging Yapılandırması.
Bu modül, bot genelinde kullanılacak 'Singleton' bir logger (BotLogger) oluşturur.
"""

import os
import logging
import logging.handlers
import bot_config

class BotLogger:
    """
    Tüm bot'ta tek bir instance (Singleton) olmasını sağlayan logger sınıfı.
    `__new__` ile sadece bir kez oluşturulur.
    `get_logger` ile yapılandırılmış logger nesnesi alınır.
    """
    _instance = None
    _logger = logging.getLogger('DuyuruBot')
    
    def __new__(cls):
        """Singleton pattern'i uygular."""
        if cls._instance is None:
            cls._instance = super(BotLogger, cls).__new__(cls)
            cls._instance._setup_logger()
        return cls._instance
    
    def _setup_logger(self):
        """
        Logger'ı ve handler'ları (işleyicileri) yapılandırır.

        1. File Handler (TimedRotatingFileHandler):
           - `bot_config.LOG_FILE`'a yazar.
           - Seviye: `bot_config.LOG_LEVEL` (örn: DEBUG).
           - Her gece yarısı (`when='midnight'`) döner, 30 gün (`backupCount=30`) saklar.

        2. Console Handler (StreamHandler):
           - Seviye: INFO. (Konsolu `DEBUG` ile boğmamak için)
        """
        
        self._logger.setLevel(logging.DEBUG) # En düşük seviye (handler'lar filtreler)
        
        # Handler'lar zaten eklendiyse (örn: re-init) tekrar ekleme
        if self._logger.handlers:
            return
        
        # Log klasörünü (örn: 'logs/') oluştur
        log_dir = os.path.dirname(bot_config.LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 1. DOSYA HANDLER (Tüm loglar, dönen)
        log_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=bot_config.LOG_FILE,
            when=bot_config.LOG_ROTATION_WHEN,
            interval=bot_config.LOG_ROTATION_INTERVAL,
            backupCount=bot_config.LOG_ROTATION_BACKUP_COUNT,
            encoding=bot_config.LOG_ENCODING
        )
        file_handler.setLevel(getattr(logging, bot_config.LOG_LEVEL))
        file_handler.setFormatter(log_format)
        self._logger.addHandler(file_handler)
        
        # 2. KONSOL HANDLER (Sadece INFO ve üstü)
        
        
        # 2. KONSOL HANDLER (Sadece INFO ve üstü)
        console_format = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_format)
        self._logger.addHandler(console_handler)
        
        self._logger.info("=" * 60)
        self._logger.info("DUYURU BOT BAŞLATILDI")
        self._logger.info("=" * 60)
    
    def get_logger(self):
        """Yapılandırılmış logger nesnesini döndürür."""
        return self._logger


# --- Global Logger Instance ---
# Diğer modüller `from core.logger import logger` yerine
# `log_info, log_error` gibi yardımcı fonksiyonları kullanmalı.
_bot_logger = BotLogger()
logger = _bot_logger.get_logger()


# --- Genel Kısayol Fonksiyonları ---

def log_info(message: str):
    """Info seviyesinde log atar."""
    logger.info(message)

def log_warning(message: str):
    """Warning seviyesinde log atar."""
    logger.warning(message)

def log_error(message: str, exc_info: bool = False):
    """
    Kısayol: Error seviyesinde log atar.

    Args:
        message (str): Hata mesajı.
        exc_info (bool): True ise exception traceback'ini de loglar.
    """
    logger.error(message, exc_info=exc_info)

def log_debug(message: str):
    """
    Kısayol: Debug seviyesinde log atar.
    
    (Konsol seviyesi INFO olduğu için bu sadece dosyaya yazılır)
    """
    logger.debug(message)

def log_critical(message: str, exc_info: bool = False):
    """
    Kısayol: Critical (çökme) seviyesinde log atar.
    
    Args:
        message (str): Hata mesajı.
        exc_info (bool): True ise exception traceback'ini de loglar.
    """
    logger.critical(message, exc_info=exc_info)


# --- Uygulamaya Özel Log Kısayolları ---

# core/database.py
def log_database_error(operation: str, error: Exception):
    """Veritabanı işlemi sırasında hata alındığını (ERROR) loglar."""
    logger.error(f"🛑 [DATABASE] {operation} hatası: {error}", exc_info=True)
    
# scrapers/base_scraper.py
def log_scraper_success(site_name: str, count: int):
    """Bir scraper'ın sayfayı başarıyla okuduğunu (DEBUG) loglar."""
    logger.debug(f"✅ [{site_name}] Sayfada {count} duyuru bulundu")

def log_scraper_error(site_name: str, error: Exception):
    """Bir scraper'ın görev sırasında hata aldığını (ERROR) loglar."""
    logger.error(f"🛑 [{site_name}] Scraping hatası: {error}", exc_info=True)

# core/telegram_bot.py
def log_telegram_sent(site_name: str, title: str):
    """Bir duyurunun Telegram'a başarıyla gönderildiğini (INFO) loglar."""
    logger.info(f"📨 [{site_name}] Yeni duyuru Telegram'a gönderildi: {title[:5]}...")

def log_telegram_error(site_name: str, error: str):
    """Telegram'a gönderim sırasında hata alındığını (ERROR) loglar."""
    logger.error(f"🛑 [{site_name}] Telegram hatası: {error}")

# core/scheduler.py
def log_scraper_start(site_name: str):
    """Bir scraper'ın başladığını (DEBUG) loglar."""
    logger.debug(f"🚀 [{site_name}] Scraping başlatıldı")

def log_new_announcement(site_name: str, title: str):
    """Yeni bir duyuru bulunduğunu (INFO) loglar."""
    logger.info(f"🔔 [{site_name}] YENİ DUYURU: {title[:60]}...")

def log_task_finish(site_name: str, new_count: int, updated_count: int = 0):
    """
    Bir scraper görevinin bittiğini loglar (Her zaman INFO).
    """
    if new_count > 0 or updated_count > 0:
        logger.info(f"✅ [{site_name}] Görev tamamlandı (Yeni: {new_count}, Güncellenen: {updated_count})")
    else:
        # Değişiklik olmasa da (rutin kontrol) konsolda görebilmek için INFO
        logger.info(f"✅ [{site_name}] Görev tamamlandı (Değişiklik yok)")