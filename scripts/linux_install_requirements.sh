#!/bin/bash
set -e

# Scriptin çaliştiği dizinin bir üstüne (proje köküne) git
cd "$(dirname "$0")/.."

# Renk Kodlari
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo
echo "==================================================="
echo "  DUYURU-BOT KURULUM SCRIPTINE HOS GELDINIZ"
echo "==================================================="
echo

echo "[1/4] Sistem gereksinimleri kontrol ediliyor (python3-venv)..."
if ! command -v python3 &> /dev/null; then
    echo
    echo -e "${RED}[HATA] python3 bulunamadı!${NC}"
    echo "Lütfen Python'u yükleyin."
    echo
    exit 1
fi

# Debian/Ubuntu tabanlı sistemler için venv paketi kontrolü
if [ -f /etc/debian_version ]; then
    sudo apt-get update
    sudo apt-get install python3-venv -y
fi

echo
echo "[2/4] Python sanal ortami (.venv) olusturuluyor..."
if ! python3 -m venv .venv; then
    echo
    echo -e "${RED}[HATA] Sanal ortam oluşturulamadı.${NC}"
    echo
    exit 1
fi

echo
echo "[3/4] Sanal ortam aktive ediliyor..."
source ./.venv/bin/activate

echo
echo "[4/4] Gereksinimler yukleniyor..."
echo "---------------------------------------------------"
if ! pip install -r requirements.txt; then
    echo
    echo "---------------------------------------------------"
    echo -e "${RED}[HATA] Kütüphaneler yüklenirken bir sorun oluştu.${NC}"
    echo "İnternet bağlantınızı kontrol edin."
    echo
    exit 1
fi
echo "---------------------------------------------------"

echo
echo "==================================================="
echo -e "${GREEN}  KURULUM BASARIYLA TAMAMLANDI!${NC}"
echo "==================================================="
echo
echo "Artık './scripts/linux_start_bot.sh' ile botu başlatabilirsiniz."
echo