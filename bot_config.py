# bot_config.py
"""
Duyuru Botu için merkezi konfigürasyon dosyası.
Token'lar, site listeleri, veritabanı yolu, log seviyesi vb.
bu dosyadan okunur, '.env' dosyasından gizli bilgileri yükler.
"""

import os
import re

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path: str = ".env") -> bool:
        if not os.path.exists(dotenv_path):
            return False
        with open(dotenv_path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
        return True

# .env dosyasını yükle
load_dotenv()

# ===================================================
# TELEGRAM AYARLARI
# Token'ı .env dosyasından oku
# ===================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN bulunamadı! Lütfen .env dosyasını kontrol et.")

# Yönetici bildirimleri için opsiyonel chat/kanal ID'si (boş bırakılırsa sadece log yazılır)
ADMIN_CHAT_ID = (os.getenv("ADMIN_CHAT_ID") or "").strip() or None

# ===================================================
# SITE AYARLARI
# Bot'un kontrol edeceği tüm sitelerin listesi.
# Scheduler bu listeyi okuyarak görevleri zamanlar.
#
# 'key': Sitenin veritabanındaki kalıcı kimliği. Küçük harf, rakam ve '_'
#        içerebilir. Bot çalışmaya başladıktan sonra DEĞİŞTİRİLMEMELİDİR;
#        değiştirilirse site yeni bir site gibi baştan kaydedilir.
# 'name': Telegram mesajlarında ve loglarda görünen ad; serbestçe değiştirilebilir.
# ===================================================
SITES = [
    {
        'key': 'bseu_bilgisayar',
        'url': 'https://www.bilecik.edu.tr/bilgisayar/arama/4',
        'name': 'BŞEÜ Bilgisayar Müh.',
        'scraper_path': 'scrapers.bilecik_seu.BilecikSEUScraper',
        'telegram_channel_id': os.getenv("CHANNEL1"),
        'schedule_minutes': ['05', '35'],
        'enabled': True
    },
    {
        'key': 'bseu_muhendislik',
        'url': 'https://www.bilecik.edu.tr/muhendislik/arama/4',
        'name': 'BŞEÜ Mühendislik Fak.',
        'scraper_path': 'scrapers.bilecik_seu.BilecikSEUScraper',
        'telegram_channel_id': os.getenv("CHANNEL1"),
        'schedule_minutes': ['15', '45'],
        'enabled': True
    },
    {
        'key': 'bseu_sks',
        'url': 'https://www.bilecik.edu.tr/sks/arama/4',
        'name': 'BŞEÜ SKS',
        'scraper_path': 'scrapers.bilecik_seu.BilecikSEUScraper',
        'telegram_channel_id': os.getenv("CHANNEL1"),
        'schedule_minutes': ['25', '55'],
        'enabled': True
    },
    # Yeni site eklemek için aşağıdaki şablonu kopyalayıp doldurun:
    # {
    #     'key': 'site_anahtari',
    #     'url': 'https://...',
    #     'name': 'Site Adı',
    #     'scraper_path': 'scrapers.uludag_u.UludagUScraper',
    #     'telegram_channel_id': os.getenv("CHANNEL_X"),
    #     'schedule_minutes': ['00', '30'],
    #     'enabled': True
    # },
]

# ===================================================
# SQLite VERİTABANI AYARLARI
# ===================================================
DATABASE_PATH = 'data/duyurular.db'

# ===================================================
# LOG AYARLARI
# ===================================================
LOG_FILE = 'logs/bot.log'
LOG_ENCODING = 'utf-8'

# Dosyaya yazılacak minimum log seviyesi (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL = 'DEBUG'

# Örn: when='midnight' ve interval=1 ise her gün (varsayılan).
# Log dosyalarının ne zaman döneceğini (değişeceğini) belirtir.
LOG_ROTATION_WHEN = 'midnight'
# 'when' parametresine bağlı olarak dönüş sıklığı saat (Integer).
LOG_ROTATION_INTERVAL = 1
# Saklanacak eski log dosyası sayısı.
LOG_ROTATION_BACKUP_COUNT = 7

# ===================================================
# SCRAPING AYARLARI
# ===================================================
# Bir sayfayı çekerken maksimum bekleme süresi (saniye)
REQUEST_TIMEOUT = 30
# Standart tarayıcı user agent'ı (bot gibi görünmemek için)
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
# HTTP hatası durumunda maksimum yeniden deneme sayısı
MAX_RETRIES = 3
# Yeniden denemeler arası bekleme süresi (saniye)
RETRY_DELAY = 5
# Her HTTP isteği (GET) arası güvenlik beklemesi (milisaniye)
REQUEST_DELAY_MS = 500

# ===================================================
# BİLDİRİM AYARLARI
# ===================================================
# Bir bildirimin gönderimi kaç turda başarısız olursa vazgeçilsin.
# Her tur sitenin kontrol aralığına bağlıdır (30 dk aralıkla 6 deneme ≈ 3 saat).
MAX_NOTIFY_ATTEMPTS = 6
# Bir site art arda kaç kontrolde taranamazsa yöneticiye uyarı gönderilsin
ADMIN_ALERT_THRESHOLD = 6


# ===================================================
#    BU AYARLARI BOT İLK DEFA ÇALIŞTIKTAN SONRA
#         !!! DİKKATLİ DEĞİŞTİRİN !!!
# 0 <= FIRST_RUN_SEND_LIMIT <= FIRST_RUN_FETCH_LIMIT
# 1 <= NORMAL_RUN_UPDATE_CHECK_LIMIT <= NORMAL_RUN_TOTAL_CHECK_LIMIT <= FIRST_RUN_FETCH_LIMIT
# ===================================================

# ===================================================
#     SCRAPING AYARLARI (NORMAL ÇALIŞTIRMA)
# ===================================================
# Son kaç duyuru için "içerik güncellemesi" (hash) kontrolü yapılsın.
NORMAL_RUN_UPDATE_CHECK_LIMIT = 5
# Son kaç duyuru için "Başlık" (hash) kontrolü yapılsın.
NORMAL_RUN_TOTAL_CHECK_LIMIT = 10

# ===================================================
#     SCRAPING AYARLARI (İLK ÇALIŞTIRMA)
# ===================================================
# İlk çalıştırmada Telegram'a gönderilecek en yeni duyuru sayısı
FIRST_RUN_SEND_LIMIT = 1
# İlk çalıştırmada (DB boşken) içeriği çekilecek maksimum duyuru sayısı
FIRST_RUN_FETCH_LIMIT = 10
# ===================================================


def validate_config() -> None:
    """Site yapılandırmalarını ve sayısal limitleri doğrular."""
    seen_keys = set()
    for site in SITES:
        key = site.get('key')
        if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9_]+', key):
            raise ValueError(
                f"'{site.get('name')}' için geçerli bir 'key' tanımlanmalı (küçük harf, rakam ve '_')."
            )
        if key in seen_keys:
            raise ValueError(
                f"'{key}' site anahtarı birden fazla sitede kullanılıyor; her site için benzersiz olmalı."
            )
        seen_keys.add(key)

        if not site.get('enabled'):
            continue

        site_label = site.get('name') or key
        for field in ('url', 'name', 'scraper_path', 'telegram_channel_id'):
            if not site.get(field):
                raise ValueError(
                    f"'{site_label}' için '{field}' eksik veya boş! Lütfen bot_config.py ve .env dosyalarını kontrol et."
                )

        schedule_minutes = site.get('schedule_minutes')
        if not isinstance(schedule_minutes, (list, tuple)) or not schedule_minutes:
            raise ValueError(f"'{site_label}' için 'schedule_minutes' boş olmayan bir liste olmalı.")
        for raw_minute in schedule_minutes:
            try:
                minute = int(raw_minute)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"'{site_label}' için geçersiz dakika değeri: {raw_minute!r}"
                ) from exc
            if not (0 <= minute <= 59):
                raise ValueError(
                    f"'{site_label}' için dakika değeri 0-59 arasında olmalı: {raw_minute!r}"
                )

    if not (0 <= FIRST_RUN_SEND_LIMIT <= FIRST_RUN_FETCH_LIMIT):
        raise ValueError(
            f"Limit kuralı ihlali: 0 <= FIRST_RUN_SEND_LIMIT ({FIRST_RUN_SEND_LIMIT}) "
            f"<= FIRST_RUN_FETCH_LIMIT ({FIRST_RUN_FETCH_LIMIT}) olmalı."
        )

    if not (1 <= NORMAL_RUN_UPDATE_CHECK_LIMIT <= NORMAL_RUN_TOTAL_CHECK_LIMIT <= FIRST_RUN_FETCH_LIMIT):
        raise ValueError(
            f"Limit kuralı ihlali: 1 <= NORMAL_RUN_UPDATE_CHECK_LIMIT ({NORMAL_RUN_UPDATE_CHECK_LIMIT}) "
            f"<= NORMAL_RUN_TOTAL_CHECK_LIMIT ({NORMAL_RUN_TOTAL_CHECK_LIMIT}) "
            f"<= FIRST_RUN_FETCH_LIMIT ({FIRST_RUN_FETCH_LIMIT}) olmalı."
        )

    if MAX_NOTIFY_ATTEMPTS < 1:
        raise ValueError(f"MAX_NOTIFY_ATTEMPTS en az 1 olmalı (mevcut: {MAX_NOTIFY_ATTEMPTS}).")

    if ADMIN_ALERT_THRESHOLD < 1:
        raise ValueError(f"ADMIN_ALERT_THRESHOLD en az 1 olmalı (mevcut: {ADMIN_ALERT_THRESHOLD}).")


validate_config()
