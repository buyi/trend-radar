from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import radar


def snapshot(day='14', hour='09', rank=100, error=None, country='us'):
    timestamp = f'2026-10-{day}T{hour}:00:00+08:00'
    src = {'key': f'apple-{country}-social', 'url': 'https://example.com',
           'fetched_at': timestamp, 'items': [] if error else [
               {'id': 'app1', 'name': 'App', 'rank': rank, 'url': 'https://example.com/app'}]}
    if error:
        src['error'] = error
    return {'fetched_at': timestamp, 'country': country, 'sources': [src]}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)
        self.db = radar.open_database(self.output / 'radar.sqlite3')

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_daily_latest_success_and_idempotency(self):
        early, late = snapshot(), snapshot(hour='10', rank=80)
        for value in [early, early, late, snapshot(hour='11', error='timeout'), early]:
            radar.save_snapshot(self.db, value)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM collection_runs').fetchone()[0], 3)
        history = radar.load_history(self.db, date(2026, 10, 21), 'us')
        self.assertEqual(history['2026-10-14']['sources'][0]['items'][0]['rank'], 80)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM daily_baselines').fetchone()[0], 1)

    def test_seven_day_report_and_country_isolation(self):
        radar.save_snapshot(self.db, snapshot())
        radar.save_snapshot(self.db, snapshot(country='gb', rank=2))
        current = snapshot(day='21', rank=20)
        history = radar.load_history(self.db, date(2026, 10, 21), 'us')
        _, analysis = radar.build_report(current, history, 20)
        self.assertEqual(analysis['weekly_risers'][0]['rank_gain'], 80)
        self.assertEqual(len(history['2026-10-14']['sources']), 1)

    def test_transaction_rolls_back_invalid_duplicate(self):
        value = snapshot()
        value['sources'][0]['items'] *= 2
        with self.assertRaises(sqlite3.IntegrityError):
            radar.save_snapshot(self.db, value)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM collection_runs').fetchone()[0], 0)

    def test_migration_is_offline_repeatable_and_preserves_old_day(self):
        (self.output / 'radar-old.json').write_text(json.dumps(snapshot()))
        (self.output / 'days').mkdir()
        (self.output / 'days' / '2026-10-14.json').write_text(json.dumps(snapshot()))
        radar.migrate_legacy(self.db, self.output)
        radar.migrate_legacy(self.db, self.output)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM rank_observations').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM legacy_imports').fetchone()[0], 2)

    def test_failed_first_capture_does_not_establish_baseline(self):
        radar.save_snapshot(self.db, snapshot(error='blocked'))
        self.assertEqual(radar.load_history(self.db, date(2026, 10, 21), 'us'), {})

    def test_github_metrics_survive_round_trip(self):
        value = snapshot()
        src = value['sources'][0]
        src['key'] = 'github-weekly'
        src['items'][0].update(stars=10000, stars_this_week=250)
        radar.save_snapshot(self.db, value)
        row = self.db.execute('SELECT stars,stars_this_week FROM rank_observations').fetchone()
        self.assertEqual(row, (10000, 250))
        history = radar.load_history(self.db, date(2026, 10, 21), 'gb')
        self.assertEqual(history['2026-10-14']['sources'][0]['items'][0]['stars_this_week'], 250)


if __name__ == '__main__':
    unittest.main()
