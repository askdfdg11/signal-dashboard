import copy
import importlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import common
import collect_headlines as collector
import generate_analysis as analysis


class PipelineTests(unittest.TestCase):
    def test_schedule_and_delayed_trigger(self):
        for hour, minute, expected in [(7, 59, 'evening'), (8, 0, 'morning'), (12, 30, 'noon'), (20, 0, 'evening')]:
            with patch.dict(os.environ, {'SIGNAL_CRON': '', 'SIGNAL_SLOT': 'auto'}):
                value = common.slot_context(datetime(2026, 10, 20, hour, minute, tzinfo=common.KST))
            self.assertEqual(value['slot'], expected)
        with patch.dict(os.environ, {'SIGNAL_CRON': '0 20 * * *'}):
            value = common.slot_context(datetime(2026, 10, 21, 0, 5, tzinfo=common.KST))
        self.assertEqual(value['date'], '2026-10-20')
        self.assertEqual(value['slot'], 'evening')

    def test_feed_rejects_stale_future_missing_time_and_unsafe_url(self):
        items = ''.join(f'<item><title>{title}</title><link>{url}</link><pubDate>{date}</pubDate></item>'
            for title, url, date in [
                ('Valid', 'https://example.org/1', 'Mon, 19 Oct 2026 10:00:00 GMT'),
                ('Old', 'https://example.org/2', 'Mon, 12 Oct 2026 10:00:00 GMT'),
                ('Future', 'https://example.org/3', 'Mon, 26 Oct 2026 10:00:00 GMT'),
                ('Unsafe', 'javascript:alert(1)', 'Mon, 19 Oct 2026 10:00:00 GMT'),
                ('Missing', 'https://example.org/4', '')])
        result = collector.parse_feed(('<rss><channel>' + items + '</channel></rss>').encode(),
                    'stocks', datetime(2026, 10, 19, 20, tzinfo=common.KST))
        self.assertEqual([a['title'] for a in result], ['Valid'])

    def test_collection_failure_preserves_last_good_and_does_not_create_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common.write(root / 'data/live-headlines.json', {'sentinel': 'last-good'})
            with patch.object(common, 'ROOT', root), patch.object(collector, 'ROOT', root), \
                    patch.object(collector, 'fetch_feed', side_effect=TimeoutError):
                self.assertEqual(collector.main(), 1)
            self.assertEqual(common.read(root / 'data/live-headlines.json'), {'sentinel': 'last-good'})
            self.assertFalse((root / 'data/headline-index.json').exists())

    def test_collection_is_immutable_and_idempotent(self):
        ctx = common.slot_context()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / f"data/headline-archive/{ctx['date']}/{ctx['slot']}.json"
            def fake(category, query, now):
                return [{'title': category, 'url': 'https://example.org/' + category,
                         'category_id': category}]
            with patch.object(common, 'ROOT', root), patch.object(collector, 'ROOT', root), \
                    patch.object(collector, 'fetch_feed', side_effect=fake) as fetch:
                self.assertEqual(collector.main(), 0)
                before = file.read_bytes()
                collector.main()
                self.assertEqual(fetch.call_count, 4)
                self.assertEqual(file.read_bytes(), before)
                self.assertEqual(len(common.read(root / 'data/headline-index.json')['snapshots']), 1)

    def test_disabled_analysis_does_not_touch_briefings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common.write(root / 'data/briefings.json', {'snapshots': [{'id': 'saved'}]})
            before = (root / 'data/briefings.json').read_bytes()
            with patch.object(common, 'ROOT', root), patch.object(analysis, 'ROOT', root), \
                    patch.dict(os.environ, {'ENABLE_ANALYSIS': 'false'}):
                self.assertEqual(analysis.main(), 0)
            self.assertEqual((root / 'data/briefings.json').read_bytes(), before)

    def test_analysis_rejects_invented_sources_or_shortened_report(self):
        articles = [{'id': f'a{i}', 'category': list(sorted(analysis.CATEGORIES))[i % 4],
            'title': 'Valid title', 'deck': 'Valid deck', **{k: 'Detailed evidence. ' * 12
                for k in ['facts', 'why', 'parties', 'impact', 'watch']},
            'sources': [{'label': 'one', 'url': 'https://example.org/1'},
                        {'label': 'two', 'url': 'https://example.net/2'}]} for i in range(12)]
        doc = {'title': 'Report', 'dek': 'Description', 'summary': ['a', 'b', 'c'], 'articles': articles}
        consulted = {'https://example.org/1', 'https://example.net/2'}
        self.assertEqual(len(analysis.validate_analysis(copy.deepcopy(doc), consulted)['articles']), 12)
        with self.assertRaises(ValueError):
            analysis.validate_analysis(copy.deepcopy(doc), {'https://example.org/1'})
        doc['articles'] = articles[:11]
        with self.assertRaises(ValueError):
            analysis.validate_analysis(doc, consulted)

    def test_original_archive_is_preserved(self):
        root = Path(__file__).resolve().parents[1]
        original = common.read(root / 'data/original-archive.json')
        current = common.read(root / 'data/briefings.json')
        current = {s['id']: s for s in current['snapshots']}
        self.assertEqual(len(original['snapshots']), 15)
        for snapshot in original['snapshots']:
            self.assertEqual(snapshot, current[snapshot['id']])


if __name__ == '__main__':
    unittest.main()
