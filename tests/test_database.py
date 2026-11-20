"""core/database.py testleri: şema, WAL, indeks ve bildirim kuyruğu."""

import os
import tempfile
import unittest
from unittest.mock import patch

import bot_config
import tests.support  # noqa: F401
from core.database import SCHEMA_VERSION, Database
from tests.support import make_announcement

SITE = 'site_a'


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, 'duyurular.db')
        self._patch = patch.object(bot_config, 'DATABASE_PATH', self.db_path)
        self._patch.start()
        self.db = Database()

    def tearDown(self):
        self.db.close()
        self._patch.stop()
        self._tmpdir.cleanup()

    def _update(self, queue_update, title='Yeni başlık', content='yeni içerik'):
        return self.db.update_announcement(
            site_key=SITE,
            announcement_id='1',
            title=title,
            url='https://example.test/yeni',
            content_hash=Database.generate_hash(content),
            content_text=content,
            queue_update=queue_update,
        )

    # ----------------------------------------------------------------- Şema

    def test_new_database_has_current_schema_index_and_wal_mode(self):
        columns = {row[1] for row in self.db.conn.execute('PRAGMA table_info(announcements)')}
        indexes = {row[0] for row in self.db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        journal_mode = self.db.conn.execute('PRAGMA journal_mode').fetchone()[0]
        self.assertEqual(self.db.conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(journal_mode.lower(), 'wal')
        self.assertIn('idx_announcements_pending', indexes)
        self.assertEqual(columns, {
            'id', 'site_key', 'announcement_id', 'title', 'url', 'published_date',
            'content_text', 'content_hash', 'pending_notification', 'notify_attempts',
            'first_seen_at', 'updated_at', 'notified_at',
        })

    def test_close_and_reopen_connection(self):
        self.db.save_announcement(SITE, make_announcement('1'), pending=None)
        self.db.close()
        self.assertIsNone(self.db._conn)
        self.assertEqual(self.db.get_total_announcements(SITE), 1)
        self.assertIsNotNone(self.db._conn)

    def test_reopening_current_database_keeps_data(self):
        self.db.save_announcement(SITE, make_announcement('1'), pending=None)
        self.db.close()

        second = Database()
        try:
            self.assertEqual(second.get_total_announcements(SITE), 1)
        finally:
            second.close()

    # ----------------------------------------------------------------- Hash

    def test_generate_hash_is_sha256_and_none_without_content(self):
        self.assertIsNone(Database.generate_hash(None))
        self.assertIsNone(Database.generate_hash(''))
        self.assertEqual(len(Database.generate_hash('içerik')), 64)
        self.assertEqual(Database.generate_hash('içerik'), Database.generate_hash('içerik'))
        self.assertNotEqual(Database.generate_hash('içerik'), Database.generate_hash('içerik 2'))

    # ---------------------------------------------------------------- Kayıt

    def test_save_announcement_stores_all_fields(self):
        announcement = {**make_announcement('1'), 'content': 'metin'}
        self.assertTrue(self.db.save_announcement(SITE, announcement, pending='new'))

        record = self.db.get_announcement_by_id(SITE, '1')
        self.assertEqual(record['title'], announcement['title'])
        self.assertEqual(record['url'], announcement['url'])
        self.assertEqual(record['published_date'], announcement['date'])
        self.assertEqual(record['content_text'], 'metin')
        self.assertEqual(record['content_hash'], Database.generate_hash('metin'))
        self.assertEqual(record['pending_notification'], 'new')
        self.assertEqual(record['notify_attempts'], 0)
        self.assertIsNotNone(record['first_seen_at'])
        self.assertIsNone(record['updated_at'])
        self.assertIsNone(record['notified_at'])

    def test_save_announcement_without_content_has_no_hash(self):
        self.db.save_announcement(SITE, {**make_announcement('1'), 'content': None}, pending=None)

        record = self.db.get_announcement_by_id(SITE, '1')
        self.assertIsNone(record['content_hash'])
        self.assertIsNone(record['content_text'])
        self.assertIsNone(record['pending_notification'])

    def test_duplicate_announcement_is_ignored(self):
        self.assertTrue(self.db.save_announcement(SITE, make_announcement('1'), pending=None))
        self.assertFalse(self.db.save_announcement(SITE, make_announcement('1', 'Başka başlık'), pending='new'))
        self.assertEqual(self.db.get_announcement_by_id(SITE, '1')['title'], 'Başlık 1')

    def test_same_announcement_id_is_independent_per_site(self):
        self.db.save_announcement('site_a', make_announcement('1'), pending=None)
        self.db.save_announcement('site_b', make_announcement('1'), pending=None)

        self.assertEqual(self.db.get_total_announcements('site_a'), 1)
        self.assertEqual(self.db.get_total_announcements('site_b'), 1)
        self.assertEqual(self.db.get_total_announcements(), 2)

    def test_missing_announcement_returns_none(self):
        self.assertIsNone(self.db.get_announcement_by_id(SITE, 'yok'))

    # ----------------------------------------------------------- Güncelleme

    def test_update_without_queue_only_completes_data(self):
        self.db.save_announcement(SITE, {**make_announcement('1'), 'content': None}, pending=None)

        self.assertTrue(self._update(queue_update=False))

        record = self.db.get_announcement_by_id(SITE, '1')
        self.assertEqual(record['content_text'], 'yeni içerik')
        self.assertEqual(record['url'], 'https://example.test/yeni')
        self.assertIsNone(record['updated_at'])
        self.assertIsNone(record['pending_notification'])

    def test_update_with_queue_marks_update_pending(self):
        self.db.save_announcement(SITE, make_announcement('1'), pending=None)

        self._update(queue_update=True)

        record = self.db.get_announcement_by_id(SITE, '1')
        self.assertEqual(record['title'], 'Yeni başlık')
        self.assertIsNotNone(record['updated_at'])
        self.assertEqual(record['pending_notification'], 'update')
        self.assertEqual(record['notify_attempts'], 0)

    def test_update_keeps_pending_new_notification(self):
        self.db.save_announcement(SITE, make_announcement('1'), pending='new')

        self._update(queue_update=True)

        self.assertEqual(self.db.get_announcement_by_id(SITE, '1')['pending_notification'], 'new')

    def test_update_does_not_reset_attempts_of_pending_notification(self):
        self.db.save_announcement(SITE, make_announcement('1'), pending='new')
        record_id = self.db.get_announcement_by_id(SITE, '1')['id']
        self.db.record_notification_failure(record_id)

        self._update(queue_update=True)

        self.assertEqual(self.db.get_announcement_by_id(SITE, '1')['notify_attempts'], 1)

    def test_update_of_missing_announcement_returns_false(self):
        self.assertFalse(self._update(queue_update=True))

    # ------------------------------------------------------ Bildirim kuyruğu

    def test_pending_notifications_are_returned_in_insert_order(self):
        for ann_id in ['1', '2', '3']:
            self.db.save_announcement(SITE, make_announcement(ann_id), pending='new' if ann_id != '2' else None)
        self.db.save_announcement('site_b', make_announcement('9'), pending='new')

        self.assertEqual([r['announcement_id'] for r in self.db.get_pending_notifications(SITE)], ['1', '3'])

    def test_mark_notification_sent_clears_queue_entry(self):
        self.db.save_announcement(SITE, make_announcement('1'), pending='new')
        record = self.db.get_announcement_by_id(SITE, '1')
        self.db.record_notification_failure(record['id'])

        self.db.mark_notification_sent(record['id'])

        record = self.db.get_announcement_by_id(SITE, '1')
        self.assertIsNone(record['pending_notification'])
        self.assertEqual(record['notify_attempts'], 0)
        self.assertIsNotNone(record['notified_at'])

    def test_record_notification_failure_counts_attempts(self):
        self.db.save_announcement(SITE, make_announcement('1'), pending='new')
        record_id = self.db.get_announcement_by_id(SITE, '1')['id']

        self.assertEqual(self.db.record_notification_failure(record_id), 1)
        self.assertEqual(self.db.record_notification_failure(record_id), 2)

    def test_abandon_notification_removes_from_queue_but_keeps_attempts(self):
        self.db.save_announcement(SITE, make_announcement('1'), pending='new')
        record_id = self.db.get_announcement_by_id(SITE, '1')['id']
        self.db.record_notification_failure(record_id)

        self.db.abandon_notification(record_id)

        record = self.db.get_announcement_by_id(SITE, '1')
        self.assertIsNone(record['pending_notification'])
        self.assertEqual(record['notify_attempts'], 1)
        self.assertIsNone(record['notified_at'])
        self.assertEqual(self.db.get_pending_notifications(SITE), [])


if __name__ == '__main__':
    unittest.main()
