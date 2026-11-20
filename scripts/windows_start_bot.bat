@echo off
color a

:: Scriptin calistigi klasorun bir ustune (proje kok dizinine) git
pushd %~dp0..

:: Sanal ortam aktive ediliyor (.env degiskenleri bot_config.py tarafindan yuklenir)
call .\.venv\Scripts\activate.bat

python bot_main.py

echo Bot durduruldu.
pause
