# core/telegram_bot.py
"""
Telegram bot entegrasyonu ve async loop yönetimi.

Bu modül, `APScheduler` (sync) gibi thread'lerden `python-telegram-bot`'un (async)
'await' fonksiyonlarını çağırabilmek için 'sync-to-async' bir köprü (bridge) sağlar.

Arkaplanda ayrı bir thread'de `asyncio` event loop'u çalıştırır
(`start_telegram_loop`). `send_to_telegram` ve `send_admin_alert` gibi sync
fonksiyonlar, `asyncio.run_coroutine_threadsafe` kullanarak görevleri bu loop'a gönderir.
"""

import html
import asyncio
import threading
from datetime import datetime
from typing import Coroutine, Dict, Optional
from concurrent.futures import Future
from telegram import Bot
from telegram.error import RetryAfter, TelegramError
import bot_config
from core.logger import (
    log_debug, log_info, log_warning, log_error, log_critical,
    log_telegram_sent, log_telegram_error
)

# Tek seferde bekleme yapılacak azami flood limiti süresi (saniye)
MAX_RETRY_AFTER_SECONDS = 30

# --- Async Loop Thread Globals ---
_loop: Optional[asyncio.AbstractEventLoop] = None  # Arkaplanda çalışacak event loop
_thread: Optional[threading.Thread] = None         # Event loop'u çalıştıran thread
_notifier: Optional['TelegramNotifier'] = None     # Async thread'de yaşayan bot instance'ı
_loop_ready = threading.Event()                    # Loop'un başlatıldığını bildiren sinyal
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

    async def _post_message(self, chat_id: str, text: str, disable_preview: bool = False) -> None:
        """Telegram API üzerinden HTML formatlı mesaj gönderir."""
        await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='HTML',
            disable_web_page_preview=disable_preview
        )  # type: ignore

    async def send_announcement(self, channel_id: str, site_name: str, announcement: Dict, message_type: str = 'new') -> bool:
        """
        (Async) Kanala formatlanmış bir duyuru mesajı gönderir.

        Telegram flood limiti (`RetryAfter`) durumunda bekleme süresi
        `MAX_RETRY_AFTER_SECONDS` sınırını aşmıyorsa bekleyip bir kez daha dener;
        daha uzunsa `False` döndürerek mesajı kuyrukta bir sonraki tura bırakır.
        """
        message = self._format_message(site_name, announcement, message_type)
        title = announcement.get('title', 'Başlıksız')

        try:
            await self._post_message(channel_id, message, disable_preview=False)
            log_telegram_sent(site_name, title, message_type)
            return True

        except RetryAfter as e:
            wait_seconds = float(e.retry_after) + 1.0
            if wait_seconds > MAX_RETRY_AFTER_SECONDS:
                log_telegram_error(
                    site_name,
                    f"Telegram flood limiti çok uzun ({wait_seconds:.0f}s), gönderim sonraki tura bırakıldı."
                )
                return False

            log_warning(f"⏳ [{site_name}] Telegram flood limiti: {wait_seconds:.0f}s beklenip tekrar denenecek.")
            await asyncio.sleep(wait_seconds)
            try:
                await self._post_message(channel_id, message, disable_preview=False)
                log_telegram_sent(site_name, title, message_type)
                return True
            except TelegramError as retry_err:
                log_telegram_error(site_name, str(retry_err))
                return False
            except Exception as retry_err:
                log_critical(f"🚨 [{site_name}] Telegram tekrar gönderimde beklenmeyen hata: {retry_err}", exc_info=True)
                return False

        except TelegramError as e:
            log_telegram_error(site_name, str(e))
            return False
        except Exception as e:
            log_critical(f"🚨 [{site_name}] Telegram göndermede beklenmeyen hata: {e}", exc_info=True)
            return False

    async def send_admin_message(self, text: str) -> bool:
        """(Async) `ADMIN_CHAT_ID` tanımlıysa yöneticiye uyarı mesajı gönderir."""
        admin_chat_id = bot_config.ADMIN_CHAT_ID
        if not admin_chat_id:
            return False

        message = f"⚠️ <b>Duyuru-Bot Yönetici Bildirimi</b>\n\n{self._escape_html(text)}"
        try:
            await self._post_message(admin_chat_id, message, disable_preview=True)
            return True
        except TelegramError as e:
            log_telegram_error("ADMIN", str(e))
            return False
        except Exception as e:
            log_critical(f"🚨 [ADMIN] Yönetici bildirimi gönderilemedi: {e}", exc_info=True)
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
        date = self._format_date(announcement.get('date', ''))

        if message_type == 'update':
            header_text = "Duyuru Güncellendi"
            emoji = "🔄"
        else:
            header_text = "Yeni Duyuru"
            emoji = "🔔"

        message = f"{emoji} <b>{header_text} - {self._escape_html(site_name)}</b>\n"
        message += "━━━━━━━━━━━━━━━━━\n\n"
        message += f"<b>{self._escape_html(title)}</b>\n\n"
        if date:
            message += f"📅 <i>{self._escape_html(date)}</i>\n\n"
        if url:
            safe_url = url.replace("'", "%27")
            message += f"🔗 <a href='{safe_url}'>Duyuruyu Aç</a>\n"
        message += "\n━━━━━━━━━━━━━━━━━"
        return message

    @staticmethod
    def _format_date(date_str: str) -> str:
        """ISO tarih değerini (YYYY-MM-DD) kullanıcı dostu 'GG.AA.YYYY' biçimine çevirir."""
        if not date_str:
            return ""
        try:
            return datetime.fromisoformat(date_str).strftime('%d.%m.%Y')
        except ValueError:
            return date_str

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
        _loop_ready.set()
        _loop.run_forever()
    except Exception as e:
        log_critical(f"🚨 CRITICAL: Async Telegram loop thread çöktü: {e}", exc_info=True)


def start_telegram_loop():
    """Scheduler tarafından çağrılır: Async thread'i başlatır."""
    global _thread
    if _thread is None:
        _thread = threading.Thread(target=_start_async_loop, daemon=True, name="TelegramLoop")
        _thread.start()
        _loop_ready.wait(timeout=10)
        if _loop_ready.is_set():
            log_info("✅ Telegram | Async event loop başlatıldı.")
        else:
            raise RuntimeError("Telegram async loop başlatılamadı! Bot durduruluyor.")


def stop_telegram_loop():
    """Scheduler tarafından çağrılır: Async thread'i durdurur."""
    if _loop:
        log_debug("⏳ Telegram | Async event loop durduruluyor...")
        _loop.call_soon_threadsafe(_loop.stop)
    if _thread:
        _thread.join(timeout=5)
        log_debug("🔒 Telegram | Async loop thread durduruldu.")


def _submit_coroutine(coro: Coroutine, label: str, timeout: int = 45) -> bool:
    """Coroutine'i çalışan async loop'a gönderir ve sonucunu senkron olarak bekler."""
    if not _loop_ready.is_set() or not _notifier or not _loop:
        coro.close()
        log_critical(f"🚨 [{label}] Telegram loop hazır değil. Mesaj gönderilemedi.")
        return False

    future: Optional[Future] = None
    try:
        future = asyncio.run_coroutine_threadsafe(coro, _loop)
        return future.result(timeout=timeout)
    except TimeoutError:
        if future:
            future.cancel()
        log_critical(f"🚨 [{label}] Telegram gönderimi zaman aşımına uğradı ({timeout}s)")
        return False
    except Exception as e:
        log_critical(f"🚨 [{label}] Telegram gönderim (threadsafe) hatası: {e}")
        return False


def send_to_telegram(channel_id: str, site_name: str, announcement: Dict, message_type: str = 'new') -> bool:
    """Sync wrapper: kanala duyuru mesajı gönderir."""
    if not _loop_ready.is_set() or not _notifier or not _loop:
        log_critical(f"🚨 [{site_name}] Telegram loop hazır değil. Mesaj gönderilemedi.")
        return False
    return _submit_coroutine(
        _notifier.send_announcement(channel_id, site_name, announcement, message_type),
        label=site_name,
        timeout=45
    )


def send_admin_alert(text: str) -> bool:
    """Sync wrapper: `ADMIN_CHAT_ID` tanımlıysa yöneticiye uyarı mesajı gönderir."""
    if not bot_config.ADMIN_CHAT_ID:
        return False
    if not _loop_ready.is_set() or not _notifier or not _loop:
        log_warning("⚠️ [ADMIN] Telegram loop hazır değil, yönetici bildirimi gönderilemedi.")
        return False
    return _submit_coroutine(
        _notifier.send_admin_message(text),
        label="ADMIN",
        timeout=30
    )
