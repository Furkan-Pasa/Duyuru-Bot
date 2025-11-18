#!/bin/bash

echo "Sistem gereksinimleri kontrol ediliyor (python3-venv)..."
sudo apt-get update
sudo apt-get install python3-venv -y

echo "Python sanal ortami (.venv) olusturuluyor..."
python3 -m venv .venv

echo "Sanal ortam aktive ediliyor..."
source ./.venv/bin/activate

echo "Gereksinimler yukleniyor (requirements.txt)..."
pip install -r requirements.txt

echo "Kurulum tamamlandi!"