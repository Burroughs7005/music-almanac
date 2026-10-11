"""Offline tests: run with python3 -m unittest discover -s . -p 'test_music_almanac.py'."""
import contextlib
import datetime
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import music_almanac as app


def album(key='1', artist='Donald Fagen', title='The Nightfly', year=1982):
    return SimpleNamespace(ratingKey=key, parentTitle=artist, title=title, year=year,
                           getWebURL=lambda: 'https://app.plex.tv/desktop/#!/server/test/details?key=%2Flibrary%2Fmetadata%2F' + key)


class PlexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)
        self.env = patch.dict(os.environ, {'PLEX_URL': 'http://plex.test:32400',
                              'PLEX_TOKEN': 'secret-test-token', 'PLEX_MUSIC_SECTION_ID': '1'}, clear=True)
        self.env.start()
        self.section = SimpleNamespace(type='artist', albums=Mock(return_value=[album()]))
        self.server = Mock()
        self.server.library.sectionByID.return_value = self.section
        self.factory = patch('plexapi.server.PlexServer', return_value=self.server)
        self.factory.start()

    def tearDown(self):
        self.factory.stop()
        self.env.stop()
        os.chdir(self.cwd)
        self.temp.cleanup()

    def test_exact_unicode_case_whitespace_and_reissue_year(self):
        links = app.PlexAlbumLinks()
        self.assertIn('metadata%2F1', links.url_for(' DONALD  FAGEN ', 'the nightfly', '1990'))
        self.assertIsNone(links.url_for('Other Artist', 'The Nightfly', '1982'))
        self.assertIsNone(links.url_for('Donald Fagen', 'The Nightfly Deluxe', '1982'))
        self.assertEqual(app.normalize_plex_text('Cafe\u0301'), app.normalize_plex_text('Café'))
        self.section.albums.assert_called_once()

    def test_duplicates_disambiguate_only_if_unique_year(self):
        self.section.albums.return_value = [album(), album('2', year=1990)]
        links = app.PlexAlbumLinks()
        self.assertIn('metadata%2F2', links.url_for('Donald Fagen', 'The Nightfly', '1990'))
        self.assertIsNone(links.url_for('Donald Fagen', 'The Nightfly', '2000'))
        self.section.albums.return_value = [album(), album('2')]
        self.assertIsNone(app.PlexAlbumLinks().url_for('Donald Fagen', 'The Nightfly', '1982'))

    def test_api_failure_no_credential_in_log(self):
        self.server.library.sectionByID.side_effect = RuntimeError('secret-test-token')
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            links = app.PlexAlbumLinks()
        self.assertIsNone(links.url_for('Donald Fagen', 'The Nightfly', '1982'))
        self.assertNotIn('secret-test-token', captured.getvalue())

    def test_missing_invalid_config_and_wrong_section(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(app.PlexAlbumLinks().ready)
        for changes in [{'PLEX_TOKEN': ''}, {'PLEX_TIMEOUT': 'nan'}, {'PLEX_URL': 'ftp://plex.test'}]:
            with patch.dict(os.environ, changes):
                self.assertFalse(app.PlexAlbumLinks().ready)
        self.section.type = 'movie'
        self.assertFalse(app.PlexAlbumLinks().ready)

    def test_rss_real_feedgen_and_html_escape(self):
        self.section.albums.return_value = [album(title='A & <B>')]
        app.generate_rss([{'artist': 'Donald Fagen', 'title': 'A & <B>', 'year': '1982'}])
        from xml.etree import ElementTree as ET
        root = ET.parse('music_history.xml').getroot()
        text = root.findtext('./channel/item/description')
        self.assertIn('>Plex</a>', text)
        self.assertIn('>Spotify</a>', text)
        self.assertIn('>YouTube</a>', text)
        self.assertIn('A &amp; &lt;B&gt;', text)
        self.assertNotIn('secret-test-token', Path('music_history.xml').read_text())
        self.server.library.sectionByID.side_effect = RuntimeError()
        app.generate_rss([{'artist': 'Donald Fagen', 'title': 'The Nightfly', 'year': '1982'}])
        text = ET.parse('music_history.xml').getroot().findtext('./channel/item/description')
        self.assertNotIn('>Plex</a>', text)
        self.assertIn('>YouTube</a>', text)
        app.generate_rss([])
        self.assertIn('Nessun anniversario', Path('music_history.xml').read_text())

    def test_csv_history_sorting_preserved(self):
        today = datetime.date.today().strftime('%m%d')
        Path('RoonBuddy.csv').write_text(f'artist;title;release\nA;Old;1980{today}\nB;New;2000{today}\n')
        matches = app.get_roon_matches()
        self.assertEqual([x['title'] for x in matches], ['New', 'Old'])
        self.assertEqual(app.get_roon_matches(), [])


if __name__ == '__main__':
    unittest.main()
