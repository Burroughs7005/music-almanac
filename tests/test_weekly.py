import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import weekly


class DigestTests(unittest.TestCase):
    def test_json_config_without_tomllib(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            cfg = json.loads((root / 'config.json').read_text())
            cfg['environment_file'] = ''
            cfg.pop('contact_env', None)
            cfg['smtp_env'] = {}
            config = Path(d) / 'config.json'
            config.write_text(json.dumps(cfg))
            with patch('weekly.tomllib', None), patch('sys.argv', ['weekly', '--config', str(config), '--fixture', str(root / 'demo.json'), '--dry-run', '--date', '2026-10-02']):
                weekly.main()
            self.assertTrue((Path(d) / 'state/preview.html').exists())

    def test_existing_dotenv_mapping_without_execution(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / '.env'
            path.write_text('export MAIL_USER="demo@gmail.com"\nMAIL_PORT=465 # SSL\nMAIL_PASS=\'$(touch forbidden)\'\n')
            cfg = {'environment_file': '.env', 'smtp': {}, 'smtp_env': {'username': 'MAIL_USER', 'port': 'MAIL_PORT'}, 'contact_env': 'MAIL_USER'}
            with patch.dict('os.environ', {'MAIL_USER': 'existing@gmail.com'}, clear=True):
                weekly.load_environment(cfg, Path(d))
                self.assertEqual(cfg['smtp']['username'], 'existing@gmail.com')
                self.assertEqual(cfg['smtp']['port'], 465)
                self.assertEqual(cfg['contact'], 'existing@gmail.com')
                self.assertEqual(__import__('os').environ['MAIL_PASS'], '$(touch forbidden)')
                self.assertFalse((Path(d) / 'forbidden').exists())

    def test_real_library(self):
        root = Path(__file__).resolve().parents[1]
        counts, owned = weekly.library(root / 'RoonBuddy.csv', {'Hall & Oates': 'Daryl Hall & John Oates'})
        self.assertEqual(counts['Pino Daniele'], 28)
        self.assertNotIn('Various Artists', counts)
        self.assertIn(('a girl called eddy', 'been around'), owned)

    def test_history_and_preview(self):
        with tempfile.TemporaryDirectory() as d:
            store = weekly.Store(Path(d) / 'db')
            self.assertFalse(store.seen('a'))
            store.mark(['a', 'a'])
            self.assertTrue(store.seen('a'))
            store.db.close()

    def test_reissue_and_unknown(self):
        r = {'title': 'Album', 'date': '2026-10-02', 'release-group': {'first-release-date': '1982'}}
        self.assertIn('Ristampa', weekly.classify(r, set(), 'Artist'))
        r['release-group'] = {}
        self.assertIn('verificare', weekly.classify(r, set(), 'Artist'))

    def test_resolver_rejects_homonyms(self):
        api = MagicMock()
        api.mb.return_value = {'artists': [{'name': 'X', 'score': 100, 'id': '1'}, {'name': 'X', 'score': 100, 'id': '2'}]}
        with self.assertRaises(ValueError):
            weekly.resolve(api, 'X', {})
        self.assertEqual(weekly.resolve(api, 'X', {'X': '3'}), '3')

    def test_html_escaping_and_multipart(self):
        item = {'artist': '<script>', 'title': 'A&B', 'date': '2026-10-02', 'formats': ['CD'], 'kind': 'Uscita', 'reason': 'Collezione', 'known': True, 'url': 'https://musicbrainz.org/release/x'}
        m = weekly.message([item], ['Errore <x>'], dt.date(2026, 9, 12), dt.date(2026, 10, 2), 'a@example.com', 'b@example.com')
        h = m.get_body(preferencelist=('html',)).get_content()
        self.assertNotIn('<script>', h)
        self.assertIn('&lt;script&gt;', h)
        self.assertEqual(m.get_content_type(), 'multipart/alternative')

    def test_collect_pagination_dedup_and_partial_dates(self):
        api = MagicMock()
        def mb(entity, **kwargs):
            if entity == 'release':
                if kwargs['offset'] == 0:
                    return {'count': 3, 'releases': [{'id': 'r1', 'date': '2026-10-02'}, {'id': 'r2', 'date': '2026-10-02'}]}
                return {'count': 3, 'releases': [{'id': 'r3', 'date': '2026'}]}
            return {'id': entity.split('/')[1], 'date': '2026-10-02', 'title': 'Old album', 'status': 'Official', 'artist-credit': [{'artist': {'id': 'a'}}], 'media': [{'format': 'CD'}], 'release-group': {'id': 'g', 'primary-type': 'Album', 'first-release-date': '1980'}}
        api.mb.side_effect = mb
        warnings = []
        cfg = {'artist_ids': {'Artist': 'a'}, 'types': ['Album'], 'exclude_secondary_types': [], 'formats': []}
        result = weekly.collect(api, {'Artist': {'known': True, 'reason': 'NAS'}}, set(), cfg, dt.date(2026, 9, 12), dt.date(2026, 10, 2), warnings)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(warnings), 1)

    def test_smtp_failure_does_not_mark(self):
        # main owns mark after successful send; raising here must leave history empty.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            config = (root / 'config.toml').read_text().replace('state_dir = "state"', 'state_dir = "state-test"')
            config = config.replace('environment_file = "/home/pi/music-almanac/.env"', 'environment_file = ""')
            config = config.replace('contact_env = "ROON_GMAIL_ADDRESS"', '# contact_env disabled for test')
            for field, variable in [('username', 'ROON_GMAIL_ADDRESS'), ('sender', 'ROON_GMAIL_ADDRESS'), ('recipient', 'ROON_EMAIL_TO')]:
                config = config.replace(f'{field} = "{variable}"', f'# {field} mapping disabled for test')
            path = Path(d) / 'config.toml'
            path.write_text(config)
            fixture = [{'key': 'one', 'artist': 'Artist', 'title': 'Album', 'date': '2026-10-02', 'formats': ['CD'], 'kind': 'Uscita', 'reason': 'NAS', 'known': True, 'url': 'https://musicbrainz.org/release/x'}]
            with patch('sys.argv', ['weekly', '--config', str(path), '--send']), patch('weekly.library', return_value=({'Artist': 1}, set())), patch('weekly.candidates', return_value={}), patch('weekly.collect', return_value=fixture), patch('weekly.send', side_effect=RuntimeError('SMTP failure')):
                path.write_text(config.replace('your-address@example.com', 'real@domain.test'))
                with self.assertRaises(RuntimeError):
                    weekly.main()
            store = weekly.Store(Path(d) / 'state-test/history.sqlite')
            self.assertFalse(store.seen('one'))
            store.db.close()

    def test_similar_requires_multiple_seeds(self):
        api = MagicMock()
        api.get.return_value = {'similarartists': {'artist': [{'name': 'New', 'match': '0.9'}]}}
        cfg = {'similar_seeds': 2, 'similar_threshold': .65, 'similar_min_seeds': 2, 'similar_max': 25, 'exclude_artists': []}
        with patch.dict('os.environ', {'LASTFM_API_KEY': 'test'}):
            r = weekly.candidates(api, __import__('collections').Counter({'A': 10, 'B': 5}), cfg, [])
            self.assertIn('New', r)
            r = weekly.candidates(api, __import__('collections').Counter({'A': 10}), cfg, [])
            self.assertNotIn('New', r)


if __name__ == '__main__':
    unittest.main()
