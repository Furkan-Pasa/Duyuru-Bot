# Duyuru-Bot

![Version](https://img.shields.io/github/v/release/Furkan-Pasa/Duyuru-Bot?include_prereleases&sort=semver&style=flat-square&label=version)
![License](https://img.shields.io/github/license/Furkan-Pasa/Duyuru-Bot?style=flat-square)
![Python](https://img.shields.io/badge/python-3.13-blue?style=flat-square&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-020202?style=flat-square)
![Last Commit](https://img.shields.io/github/last-commit/Furkan-Pasa/Duyuru-Bot?style=flat-square)
![Issues](https://img.shields.io/github/issues/Furkan-Pasa/Duyuru-Bot?style=flat-square)
![Repo Size](https://img.shields.io/github/repo-size/Furkan-Pasa/Duyuru-Bot?style=flat-square)

Duyuru sitelerini periyodik olarak tarayan ve yeni/güncellenmiş duyuruları bir Telegram kanalına gönderen Python botu.

## Temel Özellikler

- **Periyodik Kontrol:** `APScheduler` kullanarak her site için tekil zamanlanmış (`CronTrigger`) görevlerle siteleri kontrol eder; `max_instances=1` ve `coalesce=True` ile aynı sitenin paralel çalışmasını engeller.
- **Asenkron Bildirimler & Flood Koruması:** `python-telegram-bot` kütüphanesini ayrı bir `asyncio` event loop'unda (farklı bir thread'de) çalıştırır. Telegram flood limiti (`RetryAfter`) durumunda kısa beklemeleri otomatik yönetir.
- **Bildirim Kuyruğu (Outbox):** Yeni ve güncellenen duyurular önce veritabanında kuyruğa alınır, ardından kayıt sırasıyla gönderilir. Telegram geçici olarak erişilemez olduğunda duyuru kaybolmaz, sonraki turlarda tekrar denenir (`MAX_NOTIFY_ATTEMPTS`).
- **Thread-Safe Veritabanı (WAL + RLock):** Paylaşılan SQLite bağlantısı `WAL` modunda ve `threading.RLock` koruması altında çalışır. Şema sürümü `PRAGMA user_version` ile takip edilir.
- **Akıllı Güncelleme Kontrolü:** Yalnızca yeni duyuruları değil, mevcut duyuruların başlık veya içeriklerinde yapılan güncellemeleri de tespit eder. İçerikler script/style ve fazla boşluklardan arındırılarak (bağlantı ve medya adresleri korunarak) SHA-256 ile karşılaştırılır; geçici ağ hataları sahte güncelleme bildirimi üretmez.
- **Yönetici Bildirimleri:** `ADMIN_CHAT_ID` tanımlandığında, ardışık tarama hatalarında (`ADMIN_ALERT_THRESHOLD`) ve maksimum deneme sonrası vazgeçilen bildirimlerde yöneticiye uyarı gönderir; erişim düzelince tekrar bilgilendirir.
- **Retry Mekanizması:** Tüm HTTP isteklerinde geçici hatalar (Timeout, ConnectionError, 5xx ve 429) için yeniden deneme yapar; kalıcı 4xx istemci hatalarında beklemeden hata döndürür.
- **Optimizasyon:** Sunucuya gereksiz yük bindirmemek için, normal kontrollerde sadece en yeni N duyurunun içeriğini kontrol eder (`NORMAL_RUN_UPDATE_CHECK_LIMIT`).
- **"İlk Çalıştırma" Mantığı:** Veritabanı boşken kanalı eski duyurularla doldurmamak için yalnızca en yeni N duyuruyu (`FIRST_RUN_SEND_LIMIT`) gönderir; kalanları referans olarak sessizce kaydeder.
- **Genişletilebilir Mimari:** `BaseScraper` soyut sınıfı sayesinde farklı HTML yapılarına sahip yeni siteleri eklemek son derece kolaydır.
- **Graceful Shutdown:** `CTRL+C` (SIGINT) / `SIGTERM` sinyallerini yakalayarak veritabanı bağlantısını, `requests` session'larını ve asenkron döngüyü güvenli bir şekilde kapatır.
- **Rotating Logs:** `TimedRotatingFileHandler` kullanarak log dosyalarını periyodik olarak arşivler ve eskilerini siler.

## 🔧 Kurulum

Proje **Windows** ve **Linux** işletim sistemleriyle uyumludur. Kurulum sürecini otomatize etmek için her platforma özel hazır scriptler mevcuttur.

> [!IMPORTANT]
> Bu proje **Python 3.13** sürümü kullanılarak geliştirilmiştir.

1. Projeyi klonlayın:

```bash
cd /opt
sudo mkdir duyuru-bot
sudo chown $USER:$USER duyuru-bot
cd duyuru-bot
git clone https://github.com/Furkan-Pasa/Duyuru-Bot .
```

- **Windows için:**

```dos
scripts\windows_install_requirements.bat
```

> **Not:** Eğer `python` komutu hata verirse veya Microsoft Store açılırsa, Windows Ayarları'ndan **"App Execution Aliases"** (Uygulama Yürütme Takma Adları) menüsüne gidin ve `python.exe`/`python3.exe` seçeneklerini **KAPATIN**. Alternatif olarak komutlarda `python` yerine `py` kullanabilirsiniz.

- **Linux/macOS için:**

```Bash
chmod +x scripts/linux_install_requirements.sh
./scripts/linux_install_requirements.sh
```

> **Not:** Kurulum scripti otomatik olarak gerekli dizinleri (`logs`, `data`) oluşturur ve dosya izinlerini ayarlar.

## ⚙️ Yapılandırma

Botun çalışması için gizli anahtarlarınızı ve ayarlarınızı yapılandırmanız gerekmektedir.

#### 1. `.env` Dosyası

- `.env.example` dosyasının adını `.env` olarak değiştirin.
- `.env` dosyasını açın ve aşağıdaki değişkenleri doldurun:

```Bash
sudo nano .env
```

  - `TELEGRAM_BOT_TOKEN`: `@BotFather`'dan aldığınız bot token'ı.
  - `CHANNEL1`: Bildirimlerin gönderileceği Telegram kanal/grup ID'si (genellikle `-100...` ile başlar).
  - `ADMIN_CHAT_ID` *(opsiyonel)*: Ardışık tarama hataları ve vazgeçilen bildirimler hakkında uyarı almak için yönetici chat ID'si.

#### 2. `bot_config.py` Dosyası

- Botun hangi siteleri, hangi zamanlamayla kontrol edeceğini `SITES` listesinden yönetebilirsiniz.
- Her site için benzersiz ve kalıcı bir `key` (küçük harf, rakam ve `_`), `url`, `name`, `scraper_path`, `telegram_channel_id` ve `schedule_minutes` tanımlanır.
- Bildirim ve uyarı davranışlarını `MAX_NOTIFY_ATTEMPTS` (varsayılan `6`) ve `ADMIN_ALERT_THRESHOLD` (varsayılan `6`) ayarlarıyla özelleştirebilirsiniz.
- Bot açılışında tüm site anahtarları, zamanlama dakikaları ve limit sıralaması (`validate_config()`) otomatik olarak doğrulanır.

> Şimdilik `BilecikSEUScraper` (`scrapers/bilecik_seu.py`) hazırdır. Farklı bir site formatı için yeni bir scraper eklemek, `BaseScraper` soyut sınıfından miras alınarak ve `scrapers/bilecik_seu.py` dosyası referans alınarak kolayca yapılabilir.

## ▶️ Çalıştırma

Gerekli yapılandırmalar yapıldıktan sonra botu başlatabilirsiniz. Başlatma scriptleri `.venv` sanal ortamını aktive eder; `.env` değişkenleri `bot_config.py` tarafından yüklenir.

- **Windows için:**

```dos
scripts\windows_start_bot.bat
```

- **Linux/macOS için:**

```bash
chmod +x scripts/linux_start_bot.sh
./scripts/linux_start_bot.sh
```

Bot başladıktan sonra terminalde `"🤖 BOT ÇALIŞIYOR. Kapatmak için CTRL+C basın."` mesajını göreceksiniz.

### 🚀 Linux Sunucu Kurulumu (Production)

Linux sunucularda botu arka planda ve sürekli çalışır halde tutmak için iki yöntem mevcuttur.

#### Yöntem 1: PM2 ile Çalıştırma (Önerilen)

PM2, uygulamanızı yöneten, bellek optimizasyonu yapan ve çökme durumunda otomatik yeniden başlatan gelişmiş bir araçtır.

1.  **PM2'yi Yükleyin:**

    ```bash
    sudo npm install pm2 -g
    ```

2.  **Botu Başlatın:**

    ```bash
    pm2 start ecosystem.config.js
    ```

    > `ecosystem.config.js` yapılandırması sayesinde bot, maksimum 300MB bellek kullanacak şekilde ve otomatik restart özelliğiyle açılır. PM2 çıktı logları devre dışıdır (bot kendi loglama sistemini kullanır), sadece hata logları `logs/pm2/` altında tutulur.

3.  **Sunucu Yeniden Başladığında Otomatik Açılma:**
    Sunucu reboot edildiğinde botun tekrar çalışması için:

    ```bash
    # 1. Şu komutu çalıştırın:
    pm2 startup

    # 2. Terminalde size "sudo env PATH=..." ile başlayan uzun bir komut verecek.
    #    O satırı kopyalayın ve terminale yapıştırıp çalıştırın.

    # 3. Son olarak mevcut listeyi kaydedin:
    pm2 save
    ```

---

#### Yöntem 2: Systemd Servisi (Alternatif)

Harici bir araç (npm/pm2) kurmak istemiyorsanız, Linux'un yerleşik servis yöneticisini kullanabilirsiniz.

1.  **Servisi Kurun ve Başlatın:**

    ```bash
    chmod +x scripts/linux_service_install.sh
    sudo ./scripts/linux_service_install.sh
    ```

## 🏛️ Proje Mimarisi

- `requirements.txt`: Gerekli Python kütüphaneleri.

- `bot_main.py`: Ana giriş noktası (entry point). Güvenli kapanış (signal handler) işlemlerini yönetir.

- `bot_config.py`: Siteler (`key`, URL, zamanlama), limitler, log seviyeleri ve doğrulama kurallarını içerir.

- `core/database.py`: WAL modunda, `RLock` korumalı SQLite veritabanı işlemlerini, şema sürüm kontrolünü (`PRAGMA user_version`) ve bildirim kuyruğunu yönetir.

- `core/logger.py`: Merkezi ve dönen (rotating) loglama sistemini yönetir.

- `core/scheduler.py`: Botun orkestrasyon merkezi. `APScheduler` görevlerini yönetir, scraper'ları tetikler, bildirim kuyruğunu işler ve yönetici uyarılarını koordine eder.

- `core/telegram_bot.py`: `APScheduler` (sync) ile `python-telegram-bot` (async) arasında köprü kurar; duyuru mesajlarını biçimlendirir, flood limitlerini ve yönetici bildirimlerini yönetir.

- `scrapers/base_scraper.py`: Tüm scraper'lar için ortak mantığı (retry mekanizması, `requests.Session` yönetimi, içerik normalizasyonu) içeren soyut (abstract) temel sınıftır.

- `scrapers/bilecik_seu.py`: `BaseScraper`'ı miras alarak BŞEÜ duyuru sayfalarını parse etme ve içerik çekme mantığını (`BilecikSEUScraper`) uygular.

- `tests/`: Standart `unittest` tabanlı birim testleri ve HTML test fixture'ları.

## ⚖️ Lisans

Bu proje GNU General Public License v3 (GPL-3.0) altında lisanslanmıştır. Detaylar için `LICENSE` dosyasına bakınız.

[GNU GPLv3](https://choosealicense.com/licenses/gpl-3.0/)

---

[🛠️ Bakım, Güncelleme ve Kaldırma Rehberi (MAINTENANCE.md)](MAINTENANCE.md)
