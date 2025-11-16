#!/bin/bash

# ==========================================
# Duyuru-Bot systemd Servis Kaldırma Betiği
# ==========================================

# root yetkisi kontrolü
if [ "$EUID" -ne 0 ]; then
  echo "Lütfen bu betiği 'sudo ./uninstall_service.sh' olarak çalıştırın."
  exit 1
fi

SERVICE_NAME="duyuru-bot"
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME.service"

echo "Servis durduruluyor: $SERVICE_NAME"
systemctl stop $SERVICE_NAME.service

echo "Servisin otomatik açılması devre dışı bırakılıyor..."
systemctl disable $SERVICE_NAME.service

echo "Servis dosyası siliniyor: $SERVICE_FILE_PATH"
rm $SERVICE_FILE_PATH

echo "systemd yeniden yükleniyor..."
systemctl daemon-reload

echo "✅ Servis ($SERVICE_NAME) başarıyla kaldırıldı."