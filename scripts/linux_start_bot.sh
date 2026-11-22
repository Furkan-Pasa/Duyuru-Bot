#!/bin/bash
set -e

# Script'in bulunduğu dizinin bir üstüne git (proje kök dizini)
cd "$(dirname "$0")/.."

# Sanal ortam aktive ediliyor
source ./.venv/bin/activate

# Bot başlatılıyor (.env değişkenleri bot_config.py tarafından yüklenir)
python3 bot_main.py
