@echo off
echo.
echo ===================================================
echo   DUYURU-BOT KURULUM SCRIPTINE HOS GELDINIZ
echo ===================================================
echo.

echo [1/5] Python sanal ortami (.venv) olusturuluyor...

:: Scriptin calistigi klasorun bir ustune (proje kok dizinine) git
pushd %~dp0..

:: Python kontrolu
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    powershell -Command "Write-Host '[HATA] Python bulunamadi!' -ForegroundColor Red"
    echo Lutfen Python'u yukleyin ve kurulum sirasinda "Add Python to PATH" secenegini isaretleyin.
    echo.
    pause
    exit /b 1
)

python -m venv .venv
if %errorlevel% neq 0 (
    echo.
    powershell -Command "Write-Host '[HATA] Sanal ortam .venv olusturulamadi.' -ForegroundColor Red"
    echo.
    pause
    exit /b 1
)

echo.
echo [2/5] Sanal ortam aktive ediliyor...
call .\.venv\Scripts\activate.bat

echo.
echo [3/5] Gereksinimler yukleniyor...
echo ---------------------------------------------------
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ---------------------------------------------------
    powershell -Command "Write-Host '[HATA] Kutuphaneler yuklenirken bir sorun olustu.' -ForegroundColor Red"
    echo Internet baglantinizi kontrol edin veya loglari inceleyin.
    echo.
    pause
    exit /b 1
)
echo ---------------------------------------------------

echo.
echo [4/5] Gerekli dizinler olusturuluyor...
if not exist "logs" mkdir logs
if not exist "data" mkdir data

:: Basarili Bitis
echo.
echo [5/5] Tamamlandi!
echo.
echo ===================================================
powershell -Command "Write-Host '  KURULUM BASARIYLA TAMAMLANDI!' -ForegroundColor Green"
echo ===================================================
echo.
echo Artik 'scripts\windows_start_bot.bat' ile botu baslatabilirsiniz.
echo.
pause