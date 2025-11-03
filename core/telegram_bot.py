# core/telegram_bot.py
"""
Telegram bot entegrasyonu ve async loop yönetimi.

Bu modül, `APScheduler` (sync) gibi thread'lerden `python-telegram-bot`'un (async)
'await' fonksiyonlarını çağırabilmek için 'sync-to-async' bir köprü (bridge) sağlar.

Arkaplanda ayrı bir thread'de `asyncio` event loop'u çalıştırır
(`start_telegram_loop`). `send_to_telegram` gibi sync 'wrapper' fonksiyonlar,
`asyncio.run_coroutine_threadsafe` kullanarak görevleri bu loop'a gönderir.
"""

import html
import asyncio
import threading
from typing import Dict, Optional
from concurrent.futures import Future
from telegram import Bot
from telegram.error import TelegramError

import bot_config
from core.logger import log_debug, log_info, log_error, log_critical, log_telegram_sent, log_telegram_error

# --- Async Loop Thread Globals ---
_loop: Optional[asyncio.AbstractEventLoop] = None # Arkaplanda çalışacak event loop
_thread: Optional[threading.Thread] = None        # Event loop'u çalıştıran thread
_notifier: Optional['TelegramNotifier'] = None    # Async thread'de yaşayan bot instance'ı
_loop_ready = threading.Event()                   # Loop'un başlatıldığını bildiren 'event' (sinyal)
# ---------------------------------

class TelegramNotifier:
    """
    Asıl async bot işlemlerini (mesaj gönderme, formatlama) yapan sınıf.

    Bu sınıfın instance'ı, arkaplandaki async thread'de (`_start_async_loop`)
    oluşturulur ve yaşar.
    """
    def __init__(self):
        """Telegram bot'u 'python-telegram-bot' kütüphanesi ile başlatır."""
        token = bot_config.TELEGRAM_BOT_TOKEN
        if not token:
            log_error("🚨 TelegramNotifier: TELEGRAM_BOT_TOKEN eksik veya None!")
            raise ValueError("TELEGRAM_BOT_TOKEN eksik.")
        self.bot = Bot(token=token)

    async def send_announcement(self, channel_id: str, site_name: str, announcement: Dict, message_type: str = 'new') -> bool:
        """
        (Async) Kanala formatlanmış bir duyuru mesajı gönderir.
        """
        try:
            # 1. Mesajı formatla
            message = self._format_message(site_name, announcement, message_type) 

            # 2. Gönder (await ile)
            await self.bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=False
            ) # type: ignore

            log_telegram_sent(site_name, announcement.get('title', 'Başlıksız'))
            return True

        except TelegramError as e:
            # API'den dönen (beklenen) hatalar
            log_telegram_error(site_name, str(e))
            return False
        except Exception as e:
            # Beklenmeyen diğer hatalar
            log_critical(f"🚨 [{site_name}] Telegram göndermede beklenmeyen hata: {e}", exc_info=True)
            return False

    def _format_message(self, site_name: str, announcement: Dict, message_type: str = 'new') -> str:
        """
        Gönderilecek mesajı standart HTML formatına getirir.

        Args:
            site_name: Site adı (örn: 'BŞEÜ Bilgisayar Müh.')
            announcement: Duyuru sözlüğü (id, title, url, date içerir)
            message_type: 'new' (Yeni) veya 'update' (Güncelleme)

        Returns:
            Formatlanmış HTML string'i.
        """
        title = announcement.get('title', 'Başlık yok')
        url = announcement.get('url', '')
        date = announcement.get('date', 'Tarih belirtilmemiş')

        # Mesaj başlığını ayarla
        if message_type == 'update':
            header_text = "Duyuru Güncellendi"
            emoji = "🔄"
        else:
            header_text = "Yeni Duyuru"
            emoji = "🔔"

        message = f"{emoji} <b>{header_text} - {site_name}</b>\n"
        message += "━━━━━━━━━━━━━━━━━━━━\n\n"
        message += f"<b>{self._escape_html(title)}</b>\n\n"
        if date:
            message += f"📅 <i>{self._escape_html(date)}</i>\n\n"
        if url:
            message += f"🔗 <a href='{url}'>Duyuruyu Aç</a>\n"
        message += "\n━━━━━━━━━━━━━━━━━━━━"
        return message

    def _escape_html(self, text: str) -> str:
        """
        Metni 'parse_mode=HTML' için güvenli hale getirir (örn: <, >, & karakterlerini çevirir).

        Args:
            text: Düz metin.

        Returns:
            HTML-safe metin.
        """
        if not text:
            return ""
        # `html.escape` &, <, >, ", ' gibi tüm özel karakterleri çevirir.
        return html.escape(str(text))

def _start_async_loop():
    """
    Async event loop'u başlatan ve 'run_forever' ile kilitleyen thread hedefi.

    Bu fonksiyon `start_telegram_loop` tarafından bir thread içinde çalıştırılır.
    """
    global _loop, _notifier
    try:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        # Notifier'ı (ve içindeki Bot'u) bu loop'un içinde (aynı thread'de) oluşturmak önemli.
        _notifier = TelegramNotifier()
        # Hazır olduğumuzu (start_telegram_loop'a) bildir
        _loop_ready.set()
        # Bu thread burada kilitlenir
        _loop.run_forever()
    except Exception as e:
        log_critical(f"🚨 CRITICAL: Async Telegram loop thread çöktü: {e}", exc_info=True)

def start_telegram_loop():
    """
    Scheduler tarafından çağrılacak: Async thread'i başlatır.
    """
    global _thread
    if _thread is None:
        _thread = threading.Thread(target=_start_async_loop, daemon=True, name="TelegramLoop")
        _thread.start()
        _loop_ready.wait(timeout=10) # Loop'un hazır olmasını bekle
        if _loop_ready.is_set():
            log_info("✅ Telegram | Async event loop başlatıldı.")
        else:
            log_error("❌ Telegram | Async event loop başlatılamadı (Timeout).")

def stop_telegram_loop():
    """
    Scheduler tarafından çağrılacak: Async thread'i durdurur.
    """
    if _loop:
        log_debug("⏳ Telegram | Async event loop durduruluyor...")
        _loop.call_soon_threadsafe(_loop.stop)
    if _thread:
        _thread.join(timeout=5)
        log_debug("🔒 Telegram | Async loop thread durduruldu.")

def send_to_telegram(channel_id: str, site_name: str, announcement: Dict, message_type: str = 'new') -> bool:
    """
    Sync wrapper (Scheduler bunu çağırır)
    asyncio.run() KULLANMAZ, görevi çalışan loop'a gönderir.
    """
    if not _loop_ready.is_set() or not _notifier or not _loop:
        log_critical(f"🚨 [{site_name}] Telegram loop hazır değil. Mesaj gönderilemedi.")
        return False

    try:
        # 1. Coroutine'i oluştur
        coro = _notifier.send_announcement(channel_id, site_name, announcement, message_type)

        # 2. Görevi arkaplandaki loop'a thread-safe olarak gönder
        future: Future = asyncio.run_coroutine_threadsafe(coro, _loop)

        # 3. Bu sync thread'de, o async görevin bitmesini bekle
        # (Bu, eski asyncio.run() maliyetinden ÇOK daha hızlıdır)
        result = future.result(timeout=45)
        return result

    except Exception as e:
        log_critical(f"🚨 [{site_name}] send_to_telegram (threadsafe) hatası: {e}")
        return False
