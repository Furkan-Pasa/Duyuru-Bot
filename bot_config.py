# bot_config.py
"""
Duyuru Botu için merkezi konfigürasyon dosyası.
Token'lar, site listeleri, veritabanı yolu, log seviyesi vb.
bu dosyadan okunur, '.env' dosyasından gizli bilgileri yükler.
"""

import os
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# ===================================================
# TELEGRAM AYARLARI
# Token'ı .env dosyasından oku
# ===================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN bulunamadı! Lütfen .env dosyasını kontrol et.")

# ===================================================
# SITE AYARLARI
# Bot'un kontrol edeceği tüm sitelerin listesi.
# Scheduler bu listeyi okuyarak görevleri zamanlar.
# ===================================================
SITES = [
    {
        'url': 'https://www.bilecik.edu.tr/bilgisayar/arama/4',
        'name': 'BŞEÜ Bilgisayar Müh.',
        'scraper_path': 'scrapers.Scraper_BSEU.BSEU_Duyuru',
        'telegram_channel_id': os.getenv("CHANNEL1"),
        'schedule_minutes': ['05', '35'],
        'enabled': True
    },
    {
        'url': 'https://bilecik.edu.tr/muhendislik/arama/4',
        'name': 'BŞEÜ Mühendislik Fak.',
        'scraper_path': 'scrapers.Scraper_BSEU.BSEU_Duyuru',
        'telegram_channel_id': os.getenv("CHANNEL1"),
        'schedule_minutes': ['15', '45'],
        'enabled': True
    },
    {
        'url': 'https://www.bilecik.edu.tr/sks/arama/4',
        'name': 'BŞEÜ SKS',
        'scraper_path': 'scrapers.Scraper_BSEU.BSEU_Duyuru',
        'telegram_channel_id': os.getenv("CHANNEL1"),
        'schedule_minutes': ['25', '55'],
        'enabled': True
    },
    # Yeni site eklemek için aşağıdaki şablonu kopyalayıp doldurun:
    # {
    #     'url': 'https://...',
    #     'name': 'Site Adı',
    #     'scraper_path': 'scrapers.Scraper_XXX.XXX_Duyuru',
    #     'telegram_channel_id': os.getenv("CHANNEL_X"),
    #     'schedule_minutes': ['00', '30'],
    #     'enabled': True
    # },
]

# Aktif sitelerin channel_id kontrolü
for _site in SITES:
    if _site.get('enabled') and not _site.get('telegram_channel_id'):
        raise ValueError(f"'{_site['name']}' için 'telegram_channel_id' bulunamadı! .env dosyasını kontrol et.")

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
#    BU AYARLARI BOT İLK DEFA ÇALIŞTIKTAN SONRA
#         !!! DİKKATLİ DEĞİŞTİRİN !!!
# NORMAL_RUN_UPDATE_CHECK_LIMIT <= NORMAL_RUN_TOTAL_CHECK_LIMIT
# NORMAL_RUN_TOTAL_CHECK_LIMIT <= FIRST_RUN_FETCH_LIMIT
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
