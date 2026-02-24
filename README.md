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

- **Periyodik Kontrol:** `APScheduler` kullanarak zamanlanmış (cron) görevler ile siteleri otomatik olarak kontrol eder. Sunucunun yerel zaman dilimini kullanır.
- **Asenkron Bildirimler:** `python-telegram-bot` kütüphanesini ayrı bir `asyncio` event loop'unda (farklı bir thread'de) çalıştırarak ana scraper thread'lerini bloklamadan yüksek performanslı bildirim gönderir.
- **Thread-Safe Veritabanı:** `APScheduler`'ın her görev (scraper) için farklı thread'ler kullanma olasılığına karşı, `threading.local()` kullanarak her thread'in kendi izole SQLite bağlantısını yönetmesini sağlar. Bu, "database is locked" hatalarını engeller.
- **Akıllı Kontrol:** Sadece yeni duyuruları değil, mevcut duyuruların başlık veya içeriklerinde yapılan _güncellemeleri_ de tespit eder ve bildirir.
- **Retry Mekanizması:** Tüm HTTP istekleri (sayfa listesi ve duyuru içeriği) için ortak retry mantığı ile geçici ağ hatalarına karşı dayanıklıdır.
- **Optimizasyon:** Sunucuya gereksiz yük bindirmemek için, normal kontrollerde sadece en yeni N duyurunun içeriğini (hash) kontrol eder (`NORMAL_RUN_UPDATE_CHECK_LIMIT`).
- **"İlk Çalıştırma" Mantığı:** Bot veritabanı boşken ilk kez çalıştığında, kanalı eski duyurularla spamlememek için sadece en yeni 1 duyuruyu gönderir (`FIRST_RUN_SEND_LIMIT`).
- **Genişletilebilir Mimari:** `BaseScraper` soyut sınıfı sayesinde, farklı HTML yapılarına sahip yeni üniversite sitelerini eklemek son derece kolaydır.
- **Graceful Shutdown:** `CTRL+C` (SIGINT) sinyalini yakalayarak tüm veritabanı bağlantılarını, `requests` session'larını ve asenkron döngüyü güvenli bir şekilde kapatır.
- **Rotating Logs:** `TimedRotatingFileHandler` kullanarak log dosyalarını her gece yarısı otomatik olarak arşivler ve eskilerini siler.

## 🔧 Kurulum

Proje, **Windows**, **Linux** işletim sistemleriyle tam uyumludur. Kurulum sürecini otomatize etmek ve hızlandırmak için her platforma özel hazır scriptler (batch/shell) mevcuttur.

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

- ".env.example" dosyasının adını ".env" olarak değiştirin.
- ".env" dosyasını açın ve aşağıdaki değişkenleri doldurun:

```Bash
sudo nano .env
```

  - `TELEGRAM_BOT_TOKEN` @BotFather'dan aldığınız token.
  - `CHANNEL1`, `CHANNEL2`: Bildirimlerin gönderileceği Telegram kanal ID'leri (genellikle -100... ile başlar).

#### 2. `bot_config.py` Dosyası

- Botun hangi siteleri, hangi zamanlamayla kontrol edeceğini `SITES` listesinden yönetebilirsiniz.
- Yeni bir site buraya kolayca eklenebilir veya mevcut siteler enabled: `False` yapılarak pasifleştirilebilir.

> Şimdilik sadece "Scraper_BSEU" scraper'ı hazır. Farklı bir site formatı için yeni bir scraper eklemek, BaseScraper soyut sınıfından miras alınarak ve Scraper_BSEU.py dosyası referans alınarak kolayca yapılabilir. Gerekli adımlar dosya docstring'lerinde açıklanmıştır.

## ▶️ Çalıştırma

Gerekli yapılandırmalar yapıldıktan sonra botu başlatabilirsiniz.

- **Windows için:**

```dos
scripts\windows_start_bot.bat
```

Bu script, `.env` dosyasındaki değişkenleri yükler, `.venv` sanal ortamını aktive eder ve `python bot_main.py` komutunu çalıştırır.

- **Linux/macOS için:**

```bash
chmod +x scripts/linux_start_bot.sh
./scripts/linux_start_bot.sh
```

Bu script, `.env` dosyasındaki değişkenleri yükler, `.venv` sanal ortamını aktive eder ve `python3 bot_main.py` komutunu çalıştırır.

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

3.  **Yararlı Komutlar:**

| Açıklama                | Komut                             |
| :---------------------- | :-------------------------------- |
| **Durumu Gör**          | `pm2 list`                        |
| **Canlı Kaynak İzleme** | `pm2 monit`                       |
| **Logları İzle**        | `pm2 logs duyuru-bot --lines 100` |
| **Botu Durdur**         | `pm2 stop duyuru-bot`             |
| **Botu Yeniden Başlat** | `pm2 restart duyuru-bot`          |
| **Uygulamayı Sil**      | `pm2 delete duyuru-bot`           |

4.  **Sunucu Yeniden Başladığında Otomatik Açılma:**
    Sunucu reboot edildiğinde botun tekrar çalışması için:

    ```bash
    # 1. Şu komutu çalıştırın:
    pm2 startup

    # 2. Terminalde size "sudo env PATH=..." ile başlayan uzun bir komut verecek.
    #    O satırı kopyalayın ve terminale yapıştırıp çalıştırın.

    # 3. Son olarak mevcut listeyi kaydedin:
    pm2 save
    ```

5.  **Log Rotation Ayarı:**
    PM2 loglarının büyümesini önlemek için `pm2-logrotate` eklentisini kurun:

    ```bash
    pm2 install pm2-logrotate

    # Haftalık döndür (her Pazar gece yarısı)
    pm2 set pm2-logrotate:rotateInterval '0 0 * * 0'
    # 4 haftalık log dosyası sakla
    pm2 set pm2-logrotate:retain 4
    # Eski logları sıkıştır
    pm2 set pm2-logrotate:compress true
    ```

---

#### Yöntem 2: Systemd Servisi (Alternatif)

Harici bir araç (npm/pm2) kurmak istemiyorsanız, Linux'un yerleşik servis yöneticisini kullanabilirsiniz.

1.  **Servisi Kurun ve Başlatın:**

    ```bash
    chmod +x scripts/linux_service_install.sh
    sudo ./scripts/linux_service_install.sh
    ```

2.  **Kontrol etmek için:**

    ```bash
    sudo systemctl status duyuru-bot
    sudo journalctl -u duyuru-bot -f
    ```

3.  **Servisi kaldırmak için:**
    ```bash
    chmod +x scripts/linux_service_uninstall.sh
    sudo ./scripts/linux_service_uninstall.sh
    ```

## 🏛️ Proje Mimarisi

- `requirements.txt`: Gerekli Python kütüphaneleri.

- `bot_main.py`: Ana giriş noktası (entry point). Güvenli kapanış (signal handler) işlemlerini yönetir.

- `bot_config.py`: Siteler, zamanlamalar, log seviyeleri ve optimizasyon limitleri gibi tüm yapılandırmaları içerir.

- `core/database.py`: Thread-safe (`threading.local()`) SQLite veritabanı işlemlerini (CRUD) yönetir.

- `core/logger.py`: Merkezi ve dönen (rotating) loglama sistemini yönetir.

- `core/scheduler.py`: Botun beyni. `APScheduler`'ı yönetir, `bot_config.py`'yi okur, görevleri (scraper'ları) tetikler ve sonuçları Telegram'a gönderilmek üzere yönlendirir.

- `core/telegram_bot.py`: `APScheduler` (sync) ile `python-telegram-bot` (async) arasında bir köprü kurar. Kendi thread'inde bir `asyncio` event loop'u çalıştırır.

- `scrapers/base_scraper.py`: Tüm scraper'lar için ortak mantığı (retry mekanizması, `requests.Session` yönetimi) içeren soyut (abstract) bir ana sınıftır.

- `scrapers/Scraper_BSEU.py`: BaseScraper'ı miras alarak siteye özel HTML parse etme (kazıma) mantığını uygular.

## ⚖️ Lisans

Bu proje GNU General Public License v3 (GPL-3.0) altında lisanslanmıştır. Detaylar için `LICENSE` dosyasına bakınız.

[GNU GPLv3](https://choosealicense.com/licenses/gpl-3.0/)
