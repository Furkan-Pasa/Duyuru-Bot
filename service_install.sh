#!/bin/bash

# =========================================
# Duyuru-Bot systemd Servis Kurulum Betiği
# =========================================

# root yetkisi kontrolü
if [ "$EUID" -ne 0 ]; then
  echo "Lütfen bu betiği 'sudo ./install_service.sh' olarak çalıştırın."
  exit 1
fi

# Değişkenleri otomatik ayarla
SERVICE_NAME="duyuru-bot"
# Betiğin çalıştığı dizini al
PROJECT_PATH=$(pwd)
# Betiği 'sudo' ile çalıştıran kullanıcının adını al
USER_NAME=$SUDO_USER
# Kullanıcının birincil grubunu al
GROUP_NAME=$(id -gn $USER_NAME)

START_SCRIPT_PATH="$PROJECT_PATH/start_bot.sh"
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME.service"

echo "Servis kuruluyor: $SERVICE_NAME"
echo "Kullanıcı: $USER_NAME"
echo "Proje Yolu: $PROJECT_PATH"

# Eğer servis zaten varsa, önce durdur
echo "Mevcut servis (varsa) durduruluyor..."
systemctl stop $SERVICE_NAME.service > /dev/null 2>&1

# systemd servis dosyasını oluşturmak için HEREDOC kullan
# 'EOF' tırnak içinde OLMAMALI ki $USER_NAME gibi değişkenler çalışsın
echo "Servis dosyası oluşturuluyor: $SERVICE_FILE_PATH"
cat > $SERVICE_FILE_PATH << EOF
[Unit]
Description=Duyuru Bot (by Furkan Pasa)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
Group=$GROUP_NAME
WorkingDirectory=$PROJECT_PATH
ExecStart=$START_SCRIPT_PATH

# Bot çökerse yeniden başlat
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

# start_bot.sh'e çalıştırma izni ver
chmod +x $START_SCRIPT_PATH

# systemd'yi güncelle, servisi etkinleştir ve başlat
echo "systemd yeniden yükleniyor (daemon-reload)..."
systemctl daemon-reload

echo "Servis açılışta başlamak üzere etkinleştiriliyor..."
systemctl enable $SERVICE_NAME.service

echo "Servis başlatılıyor..."
systemctl start $SERVICE_NAME.service

echo ""
echo "✅ Kurulum tamamlandı!"
echo "Servis durumunu kontrol etmek için aşağıdaki komutu kullanabilirsiniz:"
echo "sudo systemctl status $SERVICE_NAME"