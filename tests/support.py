"""Tüm birim testleri için ortak kurulum, sahte nesneler ve yardımcılar."""

import logging
import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).parent / 'fixtures'

# bot_config ve core.logger import edilmeden önce test ortamını hazırla
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'test-token')
os.environ.setdefault('CHANNEL1', '-100')

import bot_config  # noqa: E402

_TEST_LOG_DIR = tempfile.mkdtemp(prefix='duyurubot-test-logs-')
bot_config.LOG_FILE = os.path.join(_TEST_LOG_DIR, 'bot.log')

from core import logger as logger_module  # noqa: E402

# Test çıktısını bozmamak için konsol handler'ını kaldır
for _handler in list(logger_module.logger.handlers):
    if type(_handler) is logging.StreamHandler:
        logger_module.logger.removeHandler(_handler)

from core import scheduler as scheduler_module  # noqa: E402


class FakeScraper:
    """
    Ağ kullanmayan sahte scraper.

    `page` duyuru listesini (veya çağrıldığında fırlatılacak Exception'ı),
    `contents` ise URL -> içerik eşlemesini tutar.
    """

    def __init__(self, url: str, name: str):
        self.url = url
        self.name = name
        self.page: object = []
        self.contents: Dict[str, object] = {}

    def scrape(self) -> List[Dict]:
        if isinstance(self.page, Exception):
            raise self.page
        return [dict(item) for item in self.page]  # type: ignore[union-attr]

    def fetch_announcement_content(self, url: str) -> Optional[str]:
        content = self.contents.get(url, f"İçerik {url}")
        if isinstance(content, Exception):
            raise content
        return content

    def close(self) -> None:
        pass


class FakeTelegram:
    """`send_to_telegram` yerine geçer ve gönderilen mesajları kaydeder."""

    def __init__(self):
        self.sent: List[Tuple[str, str, str]] = []
        self.down = False
        self.failing_ids = set()

    def __call__(self, channel_id, site_name, announcement, message_type) -> bool:
        if self.down or announcement['id'] in self.failing_ids:
            return False
        self.sent.append((message_type, announcement['id'], announcement['title']))
        return True

    def messages(self) -> List[Tuple[str, str]]:
        """Gönderilen mesajların (tip, duyuru id) listesi."""
        return [(message_type, ann_id) for message_type, ann_id, _ in self.sent]


class FakeAdminAlert:
    """`send_admin_alert` yerine geçer ve gönderilen uyarı metinlerini toplar."""

    def __init__(self):
        self.alerts: List[str] = []

    def __call__(self, text: str) -> bool:
        self.alerts.append(text)
        return True


class Harness:
    """Tek bir site için scheduler turunu çalıştırıp sonucu okumayı kolaylaştırır."""

    def __init__(self, scheduler, telegram: FakeTelegram, admin_alert: FakeAdminAlert, key: str = 'site_a'):
        self.scheduler = scheduler
        self.telegram = telegram
        self.admin_alert = admin_alert
        self.key = key

    @property
    def db(self):
        return self.scheduler.db

    @property
    def scraper(self) -> FakeScraper:
        return self.scheduler.scrapers[self.key]['instance']

    def run(self, page: Optional[object] = None) -> List[Tuple[str, str]]:
        """Bir kontrol turu çalıştırır ve bu turda gönderilen mesajları döndürür."""
        if page is not None:
            self.scraper.page = page
        self.telegram.sent.clear()
        data = self.scheduler.scrapers[self.key]
        self.scheduler._run_check(self.key, data['instance'], data['config'])
        return self.telegram.messages()

    def record(self, ann_id: str) -> Optional[Dict]:
        return self.db.get_announcement_by_id(self.key, ann_id)

    def pending_ids(self) -> List[str]:
        return [row['announcement_id'] for row in self.db.get_pending_notifications(self.key)]


def make_site(key: str = 'site_a', name: str = 'Site A', enabled: bool = True) -> Dict:
    """Testler için `FakeScraper` kullanan bir site yapılandırması üretir."""
    return {
        'key': key,
        'url': f'https://example.test/{key}',
        'name': name,
        'scraper_path': 'tests.support.FakeScraper',
        'telegram_channel_id': '-100',
        'schedule_minutes': ['05', '35'],
        'enabled': enabled,
    }


def content_url(ann_id: str) -> str:
    return f'https://example.test/{ann_id}'


def make_announcement(ann_id: str, title: Optional[str] = None, date: str = '2026-01-20') -> Dict:
    """Scraper çıktısı biçiminde bir duyuru sözlüğü üretir."""
    return {
        'id': ann_id,
        'title': title or f'Başlık {ann_id}',
        'url': content_url(ann_id),
        'date': date,
    }


class SchedulerTestCase(unittest.TestCase):
    """Geçici veritabanı, deterministik limitler ve sahte Telegram ile test tabanı."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, 'duyurular.db')
        self.telegram = FakeTelegram()
        self.admin_alert = FakeAdminAlert()
        self._schedulers = []

        self._patches = [
            patch.object(bot_config, 'DATABASE_PATH', self.db_path),
            patch.object(bot_config, 'FIRST_RUN_FETCH_LIMIT', 4),
            patch.object(bot_config, 'FIRST_RUN_SEND_LIMIT', 2),
            patch.object(bot_config, 'NORMAL_RUN_UPDATE_CHECK_LIMIT', 5),
            patch.object(bot_config, 'NORMAL_RUN_TOTAL_CHECK_LIMIT', 10),
            patch.object(bot_config, 'MAX_NOTIFY_ATTEMPTS', 3),
            patch.object(bot_config, 'ADMIN_ALERT_THRESHOLD', 3),
            patch.object(scheduler_module, 'send_to_telegram', self.telegram),
            patch.object(scheduler_module, 'send_admin_alert', self.admin_alert),
            patch.object(scheduler_module, 'start_telegram_loop', lambda: None),
            patch.object(scheduler_module, 'stop_telegram_loop', lambda: None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for s in self._schedulers:
            s.db.close()
        for p in reversed(self._patches):
            p.stop()
        self._tmpdir.cleanup()

    def make_scheduler(self, *sites):
        site_list = list(sites) or [make_site()]
        with patch.object(bot_config, 'SITES', site_list):
            scheduler = scheduler_module.DuyuruScheduler()
        self._schedulers.append(scheduler)
        return scheduler

    def make_harness(self, *sites, key: str = 'site_a') -> Harness:
        scheduler = self.make_scheduler(*sites)
        return Harness(scheduler, self.telegram, self.admin_alert, key=key)
