#!/bin/bash

# Script'in bulunduğu dizine git
cd "$(dirname "$0")"

# ".env dosyasindaki ortam degiskenleri okunuyor..."
set -a
source .env
set +a

# "Sanal ortam aktive ediliyor..."
source ./.venv/bin/activate

# "Bot baslatiliyor..."
python3 bot_main.py