# Furkan "Paşa" Çelik
# 26.10.2025
# bot_main.py
"""
Ana Başlatıcı (Entry Point).

Bu script, bot'u başlatan ana dosyadır.
Sorumlulukları:
1. Güvenli kapatma (Graceful Shutdown) için signal handler'ları (SIGINT, SIGTERM) kurmak.
2. Ana `DuyuruScheduler` sınıfını başlatmak (`scheduler.start()`).
3. Ana thread'i canlı tutmak (BackgroundScheduler arkaplanda çalışırken).
"""

import sys
import signal
import time
from typing import Optional
from core.scheduler import DuyuruScheduler
from core.logger import log_debug, log_info, log_error, log_critical, log_warning

# Global scheduler instance (signal_handler'ın erişebilmesi için)
scheduler_instance: Optional[DuyuruScheduler] = None

def signal_handler(signum, frame):
    """
    CTRL+C (SIGINT) veya 'kill' (SIGTERM) sinyalini yakalar.

    `scheduler_instance.shutdown()`'ı çağırarak APScheduler'ın, 
    scraper session'larının ve DB bağlantılarının güvenli kapatılmasını sağlar.
    """
    global scheduler_instance
    
    log_warning("🛑 Kapatma sinyali alındı (CTRL+C / TERM)")
    log_debug("🛑 Scheduler durduruluyor...")
    
    if scheduler_instance:
        try:
            # Scheduler'a güvenli kapatma komutu gönder
            scheduler_instance.shutdown()
        except Exception as e:
            log_error(f"🛑 Scheduler kapatılırken hata: {e}")
    
    log_info("👋 Program kapatıldı. Güle güle!")
    sys.exit(0)

def main():
    """
    Bot'u başlatır, signal handler'ları kurar ve ana thread'i beklemeye alır.
    """
    global scheduler_instance
    
    # Güvenli kapatma (CTRL+C veya 'kill' komutu) için sinyalleri ayarla
    signal.signal(signal.SIGINT, signal_handler)   # CTRL+C
    signal.signal(signal.SIGTERM, signal_handler)  # örn: 'kill' komutu
    
    log_info("⏳ Duyuru Bot başlatılıyor...")
    
    try:
        # 1. Scheduler'ı başlat (Scraper'ları yükler, Telegram loop'u başlatır)
        scheduler_instance = DuyuruScheduler()
        
        # 2. Görevleri (cron, date) ayarlar ve APScheduler'ı (yeni thread'de) başlatır
        scheduler_instance.start()
        
        log_info("🤖 BOT ÇALIŞIYOR. Kapatmak için CTRL+C basın.")
        
        # 3. Ana thread'i canlı tut
        # APScheduler arkaplanda (kendi thread'inde) çalışırken bu ana thread'in sonlanmasını engeller.
        while True:
            # Sinyaller (CTRL+C) bu uykuyu böler ve signal_handler'ı tetikler.
            # 3600 saniye (1 saat) uyur, bu sadece ana thread'i meşgul etmemek içindir.
            time.sleep(3600)
        
    except KeyboardInterrupt:
        # Bu 'except' bloğu normalde signal_handler tarafından yakalanmalı,
        # ama bir 'failsafe' (güvenlik) olarak burada da duruyor.
        log_warning("🛑 Program (beklenmedik) KeyboardInterrupt ile durduruldu")
        if scheduler_instance:
            scheduler_instance.shutdown()
        sys.exit(0)
        
    except Exception as e:
        # En dıştaki 'catch-all'. Burası tetiklenirse ciddi bir sorun vardır.
        log_critical(f"🚨 KRİTİK HATA! Program ana döngüde çöktü: {e}", exc_info=True)
        if scheduler_instance:
            scheduler_instance.shutdown() # Acil durum kapatması
        sys.exit(1)

if __name__ == "__main__":
    # Programı başlat
    main()