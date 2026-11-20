"""core/telegram_bot.py testleri: mesaj formatlama, RetryAfter ve yönetici bildirimleri."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from telegram.error import RetryAfter, TelegramError

import bot_config
import tests.support  # noqa: F401
from core.telegram_bot import TelegramNotifier, send_admin_alert


class TestTelegramBot(unittest.TestCase):
    def setUp(self):
        with patch('core.telegram_bot.Bot'):
            self.notifier = TelegramNotifier()
        self.notifier.bot.send_message = AsyncMock()

    # ------------------------------------------------------- Mesaj formatlama

    def test_format_message_converts_iso_date_and_escapes_html(self):
        msg = self.notifier._format_message(
            site_name='BŞEÜ & <Test>',
            announcement={
                'id': '1',
                'title': 'Sınav <1> & "2"',
                'url': "https://example.test/a'b",
                'date': '2026-01-20',
            },
            message_type='new',
        )

        self.assertIn('🔔 <b>Yeni Duyuru - BŞEÜ &amp; &lt;Test&gt;</b>', msg)
        self.assertIn('<b>Sınav &lt;1&gt; &amp; &quot;2&quot;</b>', msg)
        self.assertIn('📅 <i>20.01.2026</i>', msg)
        self.assertIn("href='https://example.test/a%27b'", msg)

    def test_format_message_uses_update_header_and_keeps_non_iso_date(self):
        msg = self.notifier._format_message(
            site_name='Site',
            announcement={'id': '1', 'title': 'Başlık', 'url': '', 'date': 'yakında'},
            message_type='update',
        )

        self.assertIn('🔄 <b>Duyuru Güncellendi - Site</b>', msg)
        self.assertIn('📅 <i>yakında</i>', msg)

    # ------------------------------------------------------------ RetryAfter

    def test_retry_after_short_wait_sleeps_and_retries(self):
        self.notifier.bot.send_message.side_effect = [RetryAfter(3), None]

        with patch('core.telegram_bot.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            ok = asyncio.run(
                self.notifier.send_announcement('-100', 'Site', {'id': '1', 'title': 'T', 'url': '', 'date': ''})
            )

        self.assertTrue(ok)
        mock_sleep.assert_awaited_once_with(4.0)
        self.assertEqual(self.notifier.bot.send_message.await_count, 2)

    def test_retry_after_long_wait_returns_false_without_sleeping(self):
        self.notifier.bot.send_message.side_effect = RetryAfter(45)

        with patch('core.telegram_bot.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            ok = asyncio.run(
                self.notifier.send_announcement('-100', 'Site', {'id': '1', 'title': 'T', 'url': '', 'date': ''})
            )

        self.assertFalse(ok)
        mock_sleep.assert_not_called()
        self.assertEqual(self.notifier.bot.send_message.await_count, 1)

    def test_retry_after_returns_false_when_second_attempt_fails(self):
        self.notifier.bot.send_message.side_effect = [RetryAfter(1), TelegramError('hata')]

        with patch('core.telegram_bot.asyncio.sleep', new_callable=AsyncMock):
            ok = asyncio.run(
                self.notifier.send_announcement('-100', 'Site', {'id': '1', 'title': 'T', 'url': '', 'date': ''})
            )

        self.assertFalse(ok)
        self.assertEqual(self.notifier.bot.send_message.await_count, 2)

    # ------------------------------------------------------- Yönetici bildirimi

    def test_send_admin_message_skips_when_not_configured(self):
        with patch.object(bot_config, 'ADMIN_CHAT_ID', None):
            self.assertFalse(asyncio.run(self.notifier.send_admin_message('uyarı')))
            self.assertFalse(send_admin_alert('uyarı'))
        self.notifier.bot.send_message.assert_not_called()

    def test_send_admin_message_sends_escaped_alert(self):
        with patch.object(bot_config, 'ADMIN_CHAT_ID', '99999'):
            ok = asyncio.run(self.notifier.send_admin_message('Site <A> çöktü'))

        self.assertTrue(ok)
        kwargs = self.notifier.bot.send_message.await_args.kwargs
        self.assertEqual(kwargs['chat_id'], '99999')
        self.assertIn('Site &lt;A&gt; çöktü', kwargs['text'])


if __name__ == '__main__':
    unittest.main()
