#!/bin/bash
echo "Python sanal ortami (.venv) olusturuluyor..."
python3 -m venv .venv

echo "Sanal ortam aktive ediliyor..."
source ./.venv/bin/activate

echo "Gereksinimler yukleniyor (requirements.txt)..."
pip install -r requirements.txt

echo "Kurulum tamamlandi."