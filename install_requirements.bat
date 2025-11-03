@echo off
echo Python sanal ortami (.venv) olusturuluyor...
python -m venv .venv

echo Sanal ortam aktive ediliyor...
call .\.venv\Scripts\activate.bat

echo Gereksinimler yukleniyor (requirements.txt)...
pip install -r requirements.txt

echo Kurulum tamamlandi.
pause