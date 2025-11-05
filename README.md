# Duyuru-Bot
Duyuru sitelerini periyodik olarak tarayan ve yeni/güncellenmiş duyuruları bir Telegram kanalına gönderen Python botu. 


## Temel Özellikler
- **Periyodik Kontrol:** `APScheduler` kullanarak zamanlanmış (cron) görevler ile siteleri otomatik olarak kontrol eder.
- **Asenkron Bildirimler:** `python-telegram-bot` kütüphanesini ayrı bir `asyncio` event loop'unda (farklı bir thread'de) çalıştırarak ana scraper thread'lerini bloklamadan yüksek performanslı bildirim gönderir.
- **Thread-Safe Veritabanı:** `APScheduler`'ın her görev (scraper) için farklı thread'ler kullanma olasılığına karşı, `threading.local()` kullanarak her thread'in kendi izole SQLite bağlantısını yönetmesini sağlar. Bu, "database is locked" hatalarını engeller.
- **Akıllı Kontrol:** Sadece yeni duyuruları değil, mevcut duyuruların başlık veya içeriklerinde yapılan _güncellemeleri_ de tespit eder ve bildirir.
- **Optimizasyon:** Sunucuya gereksiz yük bindirmemek için, normal kontrollerde sadece en yeni N duyurunun içeriğini (hash) kontrol eder (`NORMAL_RUN_UPDATE_CHECK_LIMIT`).
- **"İlk Çalıştırma" Mantığı:** Bot veritabanı boşken ilk kez çalıştığında, kanalı eski duyurularla spamlememek için sadece en yeni 1 duyuruyu gönderir (`FIRST_RUN_SEND_LIMIT`).
- **Genişletilebilir Mimari:** `BaseScraper` soyut sınıfı sayesinde, farklı HTML yapılarına sahip yeni üniversite sitelerini eklemek son derece kolaydır.
- **Graceful Shutdown:** `CTRL+C` (SIGINT) sinyalini yakalayarak tüm veritabanı bağlantılarını, `requests` session'larını ve asenkron döngüyü güvenli bir şekilde kapatır.
- **Rotating Logs:** `TimedRotatingFileHandler` kullanarak log dosyalarını her gece yarısı otomatik olarak arşivler ve eskilerini siler.


## 🔧 Kurulum
Proje, hem Windows hem de Linux/macOS ortamları için kurulum scriptleri içermektedir.
1. Projeyi klonlayın: 
```bash
git clone https://github.com/Furkan-Pasa/Duyuru-Bot
cd Duyuru-Bot
```
2. (Önerilen) Gerekli bağımlılıkları ve sanal ortamı (`.venv`) kurun:
- **Windows için:** 
```dos
install_requirements.bat
```
veya
```dos
python -m venv .venv
.\.venv\Scripts\activate.bat
pip install -r requirements.txt
```
- **Linux/macOS için:**
```Bash
chmod +x install_requirements.sh
./install_requirements.sh
```
veya
```Bash
python3 -m venv .venv
source ./.venv/bin/activate
pip install -r requirements.txt
```


## ⚙️ Yapılandırma

Botun çalışması için gizli anahtarlarınızı ve ayarlarınızı yapılandırmanız gerekmektedir.

### 1. `.env` Dosyası
- ".env.example" dosyasının adını ".env" olarak değiştirin.
- ".env" dosyasını açın ve aşağıdaki değişkenleri doldurun:
  - `TELEGRAM_BOT_TOKEN` @BotFather'dan aldığınız token.
  - `CHANNEL1`, `CHANNEL2`: Bildirimlerin gönderileceği Telegram kanal ID'leri (genellikle -100... ile başlar).

### 2. `bot_config.py` Dosyası
- Botun hangi siteleri, hangi zamanlamayla kontrol edeceğini `SITES` listesinden yönetebilirsiniz.
- Yeni bir site buraya kolayca eklenebilir veya mevcut siteler enabled: `False` yapılarak pasifleştirilebilir.

> Şimdilik sadece "BSEU_Duyuru" scrapper hazır. Farklı bir site formatı için yeni bir scraper eklemek, BaseScraper soyut sınıfından miras alınarak ve BSEU_Duyuru.py dosyası referans alınarak kolayca yapılabilir. Gerekli adımlar dosya docstring'lerinde açıklanmıştır.


## ▶️ Çalıştırma
Gerekli yapılandırmalar yapıldıktan sonra botu başlatabilirsiniz.

- **Windows için:**
```dos
start_bot.bat
```
Bu script, `.env` dosyasındaki değişkenleri yükler, `.venv` sanal ortamını aktive eder ve `python bot_main.py` komutunu çalıştırır.

- **Linux/macOS için:**
```bash
chmod +x start_bot.sh
./start_bot.sh
```
Bu script, `.env` dosyasındaki değişkenleri yükler, `.venv` sanal ortamını aktive eder ve `python3 bot_main.py` komutunu çalıştırır.

Bot başladıktan sonra terminalde `"🤖 BOT ÇALIŞIYOR. Kapatmak için CTRL+C basın."` mesajını göreceksiniz.


## 🏛️ Proje Mimarisi

- `requirements.txt`: Gerekli Python kütüphaneleri.

- `bot_main.py`: Ana giriş noktası (entry point). Güvenli kapanış (signal handler) işlemlerini yönetir.

- `bot_config.py`: Siteler, zamanlamalar, log seviyeleri ve optimizasyon limitleri gibi tüm yapılandırmaları içerir.

- `core/database.py`: Thread-safe (`threading.local()`) SQLite veritabanı işlemlerini (CRUD) yönetir.

- `core/logger.py`: Merkezi ve dönen (rotating) loglama sistemini yönetir.

- `core/scheduler.py`: Botun beyni. `APScheduler`'ı yönetir, `bot_config.py`'yi okur, görevleri (scraper'ları) tetikler ve sonuçları Telegram'a gönderilmek üzere yönlendirir.

- `core/telegram_bot.py`: `APScheduler` (sync) ile `python-telegram-bot` (async) arasında bir köprü kurar. Kendi thread'inde bir `asyncio` event loop'u çalıştırır.

- `scrapers/base_scraper.py`: Tüm scraper'lar için ortak mantığı (hata denemesi, `requests.Session` yönetimi) içeren soyut (abstract) bir ana sınıftır.

- `scrapers/BSEU_Duyuru.py:` BaseScraper'ı miras alarak siteye özel HTML parse etme (kazıma) mantığını uygular.


## ⚖️ Lisans
Bu proje GNU General Public License v3 (GPL-3.0) altında lisanslanmıştır. Detaylar için `LICENSE` dosyasına bakınız.

[GNU GPLv3](https://choosealicense.com/licenses/gpl-3.0/)

  