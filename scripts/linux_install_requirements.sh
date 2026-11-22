#!/bin/bash
set -e

# Scriptin çalıştığı dizinin bir üstüne (proje köküne) git
cd "$(dirname "$0")/.."

# Renk Kodları
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# sudo ile çalıştırılırsa .venv, data ve logs dizinleri root sahipliğinde oluşur;
# bu durum servisin normal kullanıcıyla çalışmasını engeller.
if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
    echo -e "${RED}[HATA] Bu betiği 'sudo' ile çalıştırmayın!${NC}"
    echo "Lütfen normal kullanıcınızla çalıştırın: ./scripts/linux_install_requirements.sh"
    echo "(Gerekli olduğunda apt-get için sudo şifresi otomatik sorulacaktır.)"
    exit 1
fi

echo
echo "==================================================="
echo "  DUYURU-BOT KURULUM SCRIPTINE HOS GELDINIZ"
echo "==================================================="
echo

echo "[1/5] Sistem gereksinimleri kontrol ediliyor (python3-venv)..."
if ! command -v python3 &> /dev/null; then
    echo
    echo -e "${RED}[HATA] python3 bulunamadı!${NC}"
    echo "Lütfen Python'u yükleyin."
    echo
    exit 1
fi

# Debian/Ubuntu tabanlı sistemlerde python3-venv kurulu değilse yükle
if [ -f /etc/debian_version ] && ! python3 -m venv --help > /dev/null 2>&1; then
    if [ "$EUID" -eq 0 ]; then
        apt-get update
        apt-get install python3-venv -y
    else
        sudo apt-get update
        sudo apt-get install python3-venv -y
    fi
fi

echo
echo "[2/5] Python sanal ortamı (.venv) oluşturuluyor..."
if ! python3 -m venv .venv; then
    echo
    echo -e "${RED}[HATA] Sanal ortam oluşturulamadı.${NC}"
    echo
    exit 1
fi

echo
echo "[3/5] Sanal ortam aktive ediliyor..."
source ./.venv/bin/activate

echo
echo "[4/5] Gereksinimler yükleniyor..."
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
echo "[5/5] Gerekli dizinler oluşturuluyor..."
# logs, logs/pm2 ve data dizinlerini oluştur
mkdir -p logs/pm2
mkdir -p data

echo
echo "==================================================="
echo -e "${GREEN}  KURULUM BASARIYLA TAMAMLANDI!${NC}"
echo "==================================================="
echo
