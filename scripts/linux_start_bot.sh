#!/bin/bash

# Script'in bulunduğu dizinin bir üstüne git (proje kök dizini)
cd "$(dirname "$0")/.."

# ".env dosyasindaki ortam degiskenleri okunuyor..."
set -a
source .env
set +a

# "Sanal ortam aktive ediliyor..."
source ./.venv/bin/activate

# "Bot baslatiliyor..."
python3 bot_main.py