"""core/scheduler.py testleri: akışlar, sahte güncelleme koruması, kuyruk ve yönetici uyarıları."""

import unittest

from core.database import Database
from tests.support import (
    Harness, SchedulerTestCase, content_url,
    make_announcement as ann, make_site,
)


class TestScheduler(SchedulerTestCase):
    def _seeded(self, harness: Harness, content='Metin A') -> Harness:
        """'X' (içerikli) ve 'N' (içeriği bilinmeyen) kayıtları olan hazır durum."""
        harness.db.save_announcement('site_a', {**ann('X'), 'content': content}, pending=None)
        harness.db.save_announcement('site_a', {**ann('N'), 'content': None}, pending=None)
        harness.scraper.page = [ann('X'), ann('N')]
        harness.scraper.contents = {content_url('X'): content, content_url('N'): None}
        return harness

    # ------------------------------------------------------- İlk çalıştırma

    def test_first_run_queues_newest_announcements_oldest_first(self):
        harness = self.make_harness()
        page = [ann('4'), ann('3'), ann('2'), ann('1')]

        self.assertEqual(harness.run(page), [('new', '3'), ('new', '4')])
        self.assertEqual(harness.pending_ids(), [])
        self.assertEqual(harness.db.get_total_announcements('site_a'), 4)

    def test_first_run_marks_only_sent_announcements_as_notified(self):
        harness = self.make_harness()
        harness.run([ann('4'), ann('3'), ann('2'), ann('1')])

        self.assertIsNotNone(harness.record('4')['notified_at'])
        self.assertIsNotNone(harness.record('3')['notified_at'])
        self.assertIsNone(harness.record('2')['notified_at'])
        self.assertIsNone(harness.record('1')['notified_at'])

    def test_first_run_saves_only_fetch_limit(self):
        harness = self.make_harness()
        harness.run([ann(str(i)) for i in range(10, 0, -1)])

        self.assertEqual(harness.db.get_total_announcements('site_a'), 4)

    def test_second_run_does_not_resend(self):
        harness = self.make_harness()
        page = [ann('3'), ann('2'), ann('1')]
        harness.run(page)

        self.assertEqual(harness.run(page), [])

    def test_renaming_site_keeps_records(self):
        first = self.make_harness(make_site('site_a', 'Eski Ad'))
        first.run([ann('2'), ann('1')])
        first.db.close()

        renamed = self.make_harness(make_site('site_a', 'Yeni Ad'))
        self.assertEqual(renamed.run([ann('2'), ann('1')]), [])
        self.assertEqual(renamed.db.get_total_announcements('site_a'), 2)

    # ------------------------------------------------------------ Yeni duyuru

    def test_new_announcement_is_sent_once(self):
        harness = self.make_harness()
        harness.run([ann('1')])

        self.assertEqual(harness.run([ann('2'), ann('1')]), [('new', '2')])
        self.assertEqual(harness.run([ann('2'), ann('1')]), [])

    def test_new_announcement_without_content_is_still_sent(self):
        harness = self.make_harness()
        harness.run([ann('1')])
        harness.scraper.contents[content_url('2')] = ConnectionResetError('10054')

        self.assertEqual(harness.run([ann('2'), ann('1')]), [('new', '2')])
        self.assertIsNone(harness.record('2')['content_hash'])

    def test_announcement_without_id_is_skipped(self):
        harness = self.make_harness()
        harness.run([ann('1')])

        self.assertEqual(harness.run([{**ann('2'), 'id': ''}, ann('1')]), [])

    # ---------------------------------------------------- Güncelleme kuralları

    def test_network_error_does_not_trigger_update(self):
        harness = self._seeded(self.make_harness())
        harness.scraper.contents = {
            content_url('X'): ConnectionResetError('10054'),
            content_url('N'): ConnectionResetError('10054'),
        }

        self.assertEqual(harness.run(), [])
        self.assertEqual(harness.record('X')['content_text'], 'Metin A')

    def test_missing_content_block_keeps_previous_content(self):
        harness = self._seeded(self.make_harness())
        harness.scraper.contents = {content_url('X'): None, content_url('N'): None}

        self.assertEqual(harness.run(), [])
        self.assertEqual(harness.record('X')['content_text'], 'Metin A')

    def test_unchanged_content_does_not_trigger_update(self):
        harness = self._seeded(self.make_harness())
        self.assertEqual(harness.run(), [])

    def test_first_time_content_is_stored_silently(self):
        harness = self._seeded(self.make_harness())
        harness.scraper.contents[content_url('N')] = 'Metin N1'

        self.assertEqual(harness.run(), [])
        record = harness.record('N')
        self.assertEqual(record['content_text'], 'Metin N1')
        self.assertEqual(record['content_hash'], Database.generate_hash('Metin N1'))
        self.assertIsNone(record['updated_at'])
        self.assertEqual(harness.pending_ids(), [])

    def test_changed_content_sends_update(self):
        harness = self._seeded(self.make_harness())
        harness.scraper.contents[content_url('X')] = 'Metin B'

        self.assertEqual(harness.run(), [('update', 'X')])
        record = harness.record('X')
        self.assertEqual(record['content_text'], 'Metin B')
        self.assertIsNotNone(record['updated_at'])
        self.assertIsNotNone(record['notified_at'])
        self.assertEqual(harness.run(), [])

    def test_title_change_sends_update_and_keeps_hash_when_content_unavailable(self):
        harness = self._seeded(self.make_harness())
        old_hash = harness.record('X')['content_hash']
        harness.scraper.contents[content_url('X')] = ConnectionResetError('10054')

        self.assertEqual(harness.run([ann('X', 'Yeni Başlık'), ann('N')]), [('update', 'X')])
        self.assertEqual(harness.record('X')['title'], 'Yeni Başlık')
        self.assertEqual(harness.record('X')['content_hash'], old_hash)

        harness.scraper.contents[content_url('X')] = 'Metin A'
        self.assertEqual(harness.run([ann('X', 'Yeni Başlık'), ann('N')]), [])

    def test_alternating_errors_and_successes_never_trigger_update(self):
        harness = self._seeded(self.make_harness())
        for outcome in [ConnectionResetError('10054'), 'Metin A'] * 3:
            harness.scraper.contents[content_url('X')] = outcome
            self.assertEqual(harness.run(), [])

    def test_title_change_of_older_announcement_is_detected(self):
        harness = self.make_harness()
        older = [ann(f'O{i}') for i in range(6)]
        for item in older:
            harness.db.save_announcement('site_a', {**item, 'content': 'x'}, pending=None)
        page = list(older)
        harness.scraper.contents = {item['url']: 'x' for item in older}

        page[-1] = ann('O5', 'O5 değişti')
        self.assertEqual(harness.run(page), [('update', 'O5')])

    # ------------------------------------------------------- Bildirim kuyruğu

    def test_failed_send_keeps_announcement_queued_in_order(self):
        harness = self.make_harness()
        harness.run([ann('1')])
        self.telegram.down = True

        self.assertEqual(harness.run([ann('3'), ann('2'), ann('1')]), [])
        self.assertEqual(harness.pending_ids(), ['2', '3'])
        self.assertEqual(harness.record('2')['notify_attempts'], 1)
        self.assertEqual(harness.record('3')['notify_attempts'], 0)

    def test_queue_is_sent_even_when_site_returns_nothing(self):
        harness = self.make_harness()
        harness.run([ann('1')])
        self.telegram.down = True
        harness.run([ann('2'), ann('1')])
        self.telegram.down = False

        self.assertEqual(harness.run([]), [('new', '2')])
        self.assertEqual(harness.record('2')['notify_attempts'], 0)
        self.assertEqual(harness.pending_ids(), [])

    def test_pending_new_announcement_is_sent_with_latest_title(self):
        harness = self.make_harness()
        harness.run([ann('1')])
        self.telegram.down = True
        harness.run([ann('2'), ann('1')])
        self.telegram.down = False

        harness.run([ann('2', 'Düzeltilmiş başlık'), ann('1')])
        self.assertEqual(self.telegram.sent, [('new', '2', 'Düzeltilmiş başlık')])

    def test_content_change_of_sent_announcement_is_queued_as_update(self):
        harness = self.make_harness()
        harness.run([ann('1')])
        self.telegram.down = True
        harness.scraper.contents[content_url('1')] = 'yeni'

        self.assertEqual(harness.run([ann('1')]), [])
        self.assertEqual(harness.record('1')['pending_notification'], 'update')

        self.telegram.down = False
        self.assertEqual(harness.run([ann('1')]), [('update', '1')])

    def test_notification_is_abandoned_after_max_attempts_and_alerts_admin(self):
        harness = self.make_harness()
        harness.run([ann('1')])
        self.telegram.failing_ids = {'2'}
        page = [ann('3'), ann('2'), ann('1')]

        self.assertEqual(harness.run(page), [])
        self.assertEqual(harness.pending_ids(), ['2', '3'])
        self.assertEqual(harness.run(page), [])
        self.assertEqual(harness.record('2')['notify_attempts'], 2)

        self.assertEqual(harness.run(page), [('new', '3')])
        abandoned = harness.record('2')
        self.assertIsNone(abandoned['pending_notification'])
        self.assertEqual(abandoned['notify_attempts'], 3)
        self.assertIsNone(abandoned['notified_at'])
        self.assertEqual(len(self.admin_alert.alerts), 1)
        self.assertIn('vazgeçildi', self.admin_alert.alerts[0])
        self.assertEqual(harness.run(page), [])

    def test_repeated_changes_do_not_reset_attempt_counter(self):
        harness = self.make_harness()
        harness.run([ann('1')])
        self.telegram.down = True
        harness.scraper.contents[content_url('1')] = 'v2'
        harness.run([ann('1')])
        harness.scraper.contents[content_url('1')] = 'v3'
        harness.run([ann('1')])

        self.assertEqual(harness.record('1')['notify_attempts'], 2)
        self.assertEqual(harness.record('1')['pending_notification'], 'update')

        self.telegram.down = False
        self.assertEqual(harness.run([ann('1')]), [('update', '1')])

    # ------------------------------------------------------- Yönetici uyarıları

    def test_consecutive_scrape_failures_alert_admin_once_and_recover(self):
        harness = self.make_harness()

        # Eşik = 3: ilk 2 başarısızlıkta uyarı gitmez
        harness.run([])
        harness.run([])
        self.assertEqual(self.admin_alert.alerts, [])

        # 3. ve 4. başarısızlık: yalnızca 3.'de tek uyarı gider
        harness.run([])
        harness.run(RuntimeError('bağlantı kesildi'))
        self.assertEqual(len(self.admin_alert.alerts), 1)
        self.assertIn('art arda 3 kontrolde', self.admin_alert.alerts[0])

        # Site normale döndüğünde düzelme bildirimi gider ve sayaç sıfırlanır
        harness.run([ann('1')])
        self.assertEqual(len(self.admin_alert.alerts), 2)
        self.assertIn('normale döndü', self.admin_alert.alerts[1])
        self.assertEqual(harness.scheduler.failure_counts['site_a'], 0)


if __name__ == '__main__':
    unittest.main()
