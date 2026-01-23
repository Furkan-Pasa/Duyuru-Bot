@echo off
echo.
echo ===================================================
echo   DUYURU-BOT KURULUM SCRIPTINE HOS GELDINIZ
echo ===================================================
echo.

echo [1/4] Python sanal ortami (.venv) olusturuluyor...

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
echo [2/4] Sanal ortam aktive ediliyor...
call .\.venv\Scripts\activate.bat

echo.
echo [3/4] Gereksinimler yukleniyor...
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

:: Basarili Bitis
echo.
echo ===================================================
powershell -Command "Write-Host '  KURULUM BASARIYLA TAMAMLANDI!' -ForegroundColor Green"
echo ===================================================
echo.
echo Artik 'scripts\windows_start_bot.bat' ile botu baslatabilirsiniz.
echo.
pause