# Bakım, Güncelleme ve Kaldırma Rehberi

VDS (Linux) sunucuda veya yerel ortamda çalışan Duyuru-Bot'un durumunu izleme, durdurma, güncelleme, veri/log temizleme ve sistemden tamamen kaldırma adımları aşağıda yer almaktadır.

---

## 📊 Durum Kontrolü ve Log İzleme

Bot kendi uygulama loglarını `logs/bot.log` dosyasına yazar ve gece yarısı otomatik döndürür. VDS üzerinde merkezi log yapısı kullanılıyorsa `/opt/duyuru-bot/logs` klasörü `/opt/log/duyuru-bot` dizinine sembolik bağlantı (symlink) olarak bağlanır; bu durumda her iki yol da aynı dosyayı gösterir.

- **Uygulama loglarını canlı izlemek için:**

  ```bash
  tail -f /opt/duyuru-bot/logs/bot.log
  # veya merkezi log dizininden:
  tail -f /opt/log/duyuru-bot/bot.log
  ```

- **Sıfırdan kurulumda merkezi `/opt/log/duyuru-bot` klasörünü bağlamak için:**

  ```bash
  sudo mkdir -p /opt/log/duyuru-bot/pm2
  sudo chown -R $USER:$USER /opt/log/duyuru-bot
  rm -rf /opt/duyuru-bot/logs
  ln -s /opt/log/duyuru-bot /opt/duyuru-bot/logs
  ```

### PM2 kullanılıyorsa

| Açıklama | Komut |
| :--- | :--- |
| **Durumu Gör** | `pm2 list` |
| **Canlı Kaynak İzleme** | `pm2 monit` |
| **PM2 Hata Loglarını İzle** | `pm2 logs duyuru-bot --lines 100` |
| **Botu Durdur** | `pm2 stop duyuru-bot` |
| **Botu Yeniden Başlat** | `pm2 restart duyuru-bot` |
| **Uygulamayı Sil** | `pm2 delete duyuru-bot` |

### Systemd kullanılıyorsa

```bash
sudo systemctl status duyuru-bot
sudo journalctl -u duyuru-bot -f
```

---

## ⏸️ Botu Durdurma ve Yeniden Başlatma

Bot, `SIGINT` / `SIGTERM` sinyallerini yakalayarak açık veritabanı bağlantısını, HTTP oturumlarını ve Telegram döngüsünü güvenli şekilde kapatır.

- **PM2 ile:**

  ```bash
  pm2 stop duyuru-bot       # Durdur
  pm2 restart duyuru-bot    # Yeniden başlat
  pm2 start duyuru-bot      # Tekrar başlat
  ```

- **Systemd ile:**

  ```bash
  sudo systemctl stop duyuru-bot      # Durdur
  sudo systemctl restart duyuru-bot   # Yeniden başlat
  sudo systemctl start duyuru-bot     # Tekrar başlat
  ```

- **Doğrudan terminalde çalışıyorsa (Linux / Windows):**
  Terminal penceresinde `CTRL+C` tuşlarına basın.

---

## 🔄 Güncelleme (Yeni Sürüme Geçiş)

Proje klasörüne gidip botu durdurun, yeni kodu çekin, bağımlılıkları güncelleyin ve botu yeniden başlatın:

```bash
cd /opt/duyuru-bot

# 1. Botu durdurun (kullandığınız yönteme göre birini seçin)
pm2 stop duyuru-bot
# veya: sudo systemctl stop duyuru-bot

# 2. Güncel kodu alın ve bağımlılıkları kurun
git pull
./.venv/bin/pip install -r requirements.txt

# 3. (Opsiyonel) Testleri çalıştırın
./.venv/bin/python -m unittest discover -s tests -v

# 4. Botu tekrar başlatın
pm2 start duyuru-bot
# veya: sudo systemctl start duyuru-bot
```

> **Veritabanı şema güncellemesi notu:** Yeni bir sürüm veritabanı şema sürümünü (`PRAGMA user_version`) değiştirirse, bot uyumsuz şemaya karşı hata vererek durur; bu durumda aşağıdaki "Veri ve Log Temizliği" bölümündeki komutla `data/duyurular.db*` dosyalarını temizleyip botu yeniden başlatın.

---

## 🧪 Testleri Çalıştırma

Projedeki birim testleri standart Python `unittest` altyapısını kullanır ve ağ bağlantısı gerektirmez:

- **Linux/macOS:**

  ```bash
  .venv/bin/python -m unittest discover -s tests -v
  ```

- **Windows:**

  ```dos
  .venv\Scripts\python.exe -m unittest discover -s tests -v
  ```

---

## 🧹 Veri ve Log Temizliği (Botu Silmeden Sıfırlama)

Botu kaldırmadan yalnızca veritabanını veya biriken logları temizlemek için önce botu durdurun (`pm2 stop` veya `systemctl stop`), ardından ilgili dosyaları silin:

```bash
cd /opt/duyuru-bot

# Veritabanını ve WAL dosyalarını sıfırlamak için
# (Bir sonraki açılışta bot "İlk Çalıştırma" olarak sıfırdan başlar)
rm -f data/duyurular.db data/duyurular.db-wal data/duyurular.db-shm

# Eski uygulama ve PM2 loglarını temizlemek için
rm -f logs/bot.log* logs/pm2/*.log
```

> **PM2 Log Rotation (Opsiyonel):** PM2'nin kendi hata loglarının (`logs/pm2/`) büyümesini önlemek için `pm2-logrotate` eklentisini kurabilirsiniz:
>
> ```bash
> pm2 install pm2-logrotate
> pm2 set pm2-logrotate:max_size 10M
> pm2 set pm2-logrotate:rotateInterval '0 0 * * 0'
> pm2 set pm2-logrotate:retain 4
> pm2 set pm2-logrotate:compress true
> ```

Temizlik sonrası botu tekrar başlatın (`pm2 start duyuru-bot` veya `sudo systemctl start duyuru-bot`).

---

## 🗑️ VDS Üzerinden Tamamen Kaldırma (Uninstall)

Botu arka plan servisi ve tüm dosyalarıyla birlikte sunucudan tamamen silmek için aşağıdaki adımları sırasıyla uygulayın.

### 1. Arka Plan Servisini Kaldırma

Kurulumda hangi yöntemi kullandıysanız yalnızca ona ait adımları çalıştırın:

#### Yöntem A: PM2 servisi kullanılıyorsa

```bash
# Uygulamayı durdur ve PM2 listesinden sil
pm2 stop duyuru-bot
pm2 delete duyuru-bot

# Güncel (boş) listeyi kaydet ki sunucu yeniden başladığında tekrar açılmasın
pm2 save --force
```

Sunucuda PM2 ile yönetilen **başka hiçbir uygulama yoksa**, PM2 başlangıç servisini de kaldırabilirsiniz:

```bash
pm2 unstartup systemd
```

#### Yöntem B: Systemd servisi kullanılıyorsa

Projeyle birlikte gelen kaldırma betiğini çalıştırın:

```bash
cd /opt/duyuru-bot
chmod +x scripts/linux_service_uninstall.sh
sudo ./scripts/linux_service_uninstall.sh
```

Betiği kullanmadan manuel kaldırmak isterseniz:

```bash
sudo systemctl stop duyuru-bot.service
sudo systemctl disable duyuru-bot.service
sudo rm -f /etc/systemd/system/duyuru-bot.service
sudo systemctl daemon-reload
```

### 2. Proje Dizinini ve Tüm Verileri Silme

Servis kaldırıldıktan sonra proje klasörünü (`.venv`, `.env`, veritabanı dahil) ve merkezi log dizinini tamamen silin (`/opt/duyuru-bot/logs` symlink ise `rm` hedef klasörü silmez, bu yüzden `/opt/log/duyuru-bot` ayrıca belirtilir):

```bash
cd ~
sudo rm -rf /opt/duyuru-bot /opt/log/duyuru-bot
```
