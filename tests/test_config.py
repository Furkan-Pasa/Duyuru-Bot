"""bot_config.py testleri: yapılandırma kuralları ve doğrulama."""

import unittest
from unittest.mock import patch

import bot_config
import tests.support  # noqa: F401
from tests.support import make_site


class TestConfig(unittest.TestCase):
    def test_current_config_is_valid(self):
        bot_config.validate_config()
        for site in bot_config.SITES:
            if site['enabled']:
                self.assertTrue(site['url'].startswith('https://www.'))

    def test_invalid_or_duplicate_site_key_raises(self):
        for bad_sites in (
            [{**make_site(), 'key': ''}],
            [{**make_site(), 'key': 'Site-A'}],
            [make_site('dup', 'A'), make_site('dup', 'B')],
        ):
            with patch.object(bot_config, 'SITES', bad_sites):
                with self.assertRaises(ValueError):
                    bot_config.validate_config()

    def test_missing_required_fields_on_enabled_site_raises(self):
        for field in ('url', 'name', 'scraper_path', 'telegram_channel_id'):
            bad = [{**make_site(), field: ''}]
            with patch.object(bot_config, 'SITES', bad):
                with self.assertRaises(ValueError):
                    bot_config.validate_config()

    def test_invalid_schedule_minutes_raises(self):
        for bad_minutes in ([], ['abc'], ['60'], ['-1']):
            bad = [{**make_site(), 'schedule_minutes': bad_minutes}]
            with patch.object(bot_config, 'SITES', bad):
                with self.assertRaises(ValueError):
                    bot_config.validate_config()

    def test_disabled_site_skips_channel_and_schedule_checks(self):
        disabled = {**make_site(enabled=False), 'telegram_channel_id': None, 'schedule_minutes': []}
        with patch.object(bot_config, 'SITES', [disabled]):
            bot_config.validate_config()

    def test_limit_ordering_violations_raise(self):
        cases = [
            {'FIRST_RUN_SEND_LIMIT': 11, 'FIRST_RUN_FETCH_LIMIT': 10},
            {'FIRST_RUN_SEND_LIMIT': -1},
            {'NORMAL_RUN_UPDATE_CHECK_LIMIT': 0},
            {'NORMAL_RUN_UPDATE_CHECK_LIMIT': 11, 'NORMAL_RUN_TOTAL_CHECK_LIMIT': 10},
            {'NORMAL_RUN_TOTAL_CHECK_LIMIT': 11, 'FIRST_RUN_FETCH_LIMIT': 10},
            {'MAX_NOTIFY_ATTEMPTS': 0},
            {'ADMIN_ALERT_THRESHOLD': 0},
        ]
        for overrides in cases:
            with patch.multiple(bot_config, **overrides):
                with self.assertRaises(ValueError):
                    bot_config.validate_config()


if __name__ == '__main__':
    unittest.main()
