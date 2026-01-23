@echo off
color a

:: Scriptin calistigi klasorun bir ustune (proje kok dizinine) git
pushd %~dp0..

:: .env dosyasindaki ortam degiskenleri okunuyor...
for /F "usebackq delims== tokens=1,*" %%a in (`findstr /v /c:"#" .env`) do (
    set "%%a=%%~b"
)

:: Sanal ortam aktive ediliyor...
call .\.venv\Scripts\activate.bat

python bot_main.py

echo Bot durduruldu.
pause