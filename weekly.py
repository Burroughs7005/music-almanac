#!/usr/bin/env python3
"""Roon release digest. Python 3.9+, standard library only."""
import argparse
import collections
import csv
import datetime as dt
import email.policy
from email.message import EmailMessage
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shlex
import smtplib
import sqlite3
import ssl
import time
try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo


def load_environment(cfg, base):
    """Read plain dotenv assignments without executing shell code."""
    filename = cfg.get('environment_file', '')
    if filename:
        path = Path(filename).expanduser()
        if not path.is_absolute():
            path = base / path
        for number, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('export '):
                line = line[7:].strip()
            key, sep, value = line.partition('=')
            key = key.strip()
            if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
                raise ValueError(f'.env: assegnazione non valida alla riga {number}')
            try:
                parts = shlex.split(value, comments=True, posix=True)
            except ValueError:
                raise ValueError(f'.env: virgolette non valide alla riga {number}') from None
            if len(parts) > 1:
                raise ValueError(f'.env: racchiudi il valore tra virgolette alla riga {number}')
            os.environ.setdefault(key, parts[0] if parts else '')
    for field, variable in cfg.get('smtp_env', {}).items():
        if field not in {'host', 'port', 'mode', 'username', 'sender', 'recipient'}:
            raise ValueError('smtp_env: campo non supportato')
        value = os.environ[variable]
        cfg['smtp'][field] = int(value) if field == 'port' else value
    if cfg.get('contact_env'):
        cfg['contact'] = os.environ[cfg['contact_env']]


def norm(s):
    return ' '.join(unicodedata.normalize('NFKD', s.replace('’', "'")).encode('ascii', 'ignore').decode().casefold().split())


def quote(s):
    return '"' + re.sub(r'([+\-!(){}\[\]^"~*?:\\/])', r'\\\1', s) + '"'


def library(path, aliases, collaborations=None):
    counts, owned = collections.Counter(), set()
    amap = {norm(k): v for k, v in aliases.items()}
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        if not {'Album Artist', 'Title', 'Date', 'File Format'} <= set(reader.fieldnames or []):
            raise ValueError('CSV: intestazioni Roon non riconosciute')
        for row in reader:
            artist = row['Album Artist'].strip()
            if not artist or norm(artist) in {'various artists', 'ondarock'}:
                continue
            artist = amap.get(norm(artist), artist)
            targets = (collaborations or {}).get(artist, [artist])
            for target in targets:
                target = amap.get(norm(target), target)
                counts[target] += 1
                owned.add((norm(target), norm(row['Title'])))
    return counts, owned


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript('CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY,t REAL,v TEXT); CREATE TABLE IF NOT EXISTS sent(k TEXT PRIMARY KEY,t TEXT);')

    def seen(self, key):
        return self.db.execute('SELECT 1 FROM sent WHERE k=?', (key,)).fetchone() is not None

    def mark(self, keys):
        with self.db:
            self.db.executemany('INSERT OR IGNORE INTO sent VALUES (?,?)', [(k, dt.datetime.now(dt.timezone.utc).isoformat()) for k in keys])


class API:
    def __init__(self, store, agent):
        self.store, self.agent, self.last = store, agent, 0

    def get(self, base, params, ttl=86400):
        url = base + '?' + urllib.parse.urlencode(params)
        key = hashlib.sha256(url.encode()).hexdigest()
        row = self.store.db.execute('SELECT t,v FROM cache WHERE k=?', (key,)).fetchone()
        if row and time.time() - row[0] < ttl:
            return json.loads(row[1])
        for attempt in range(4):
            time.sleep(max(0, 1.1 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={'User-Agent': self.agent, 'Accept': 'application/json'})
                with urllib.request.urlopen(req, timeout=40) as response:
                    data = json.load(response)
                if 'error' in data:
                    raise ValueError('Last.fm errore ' + str(data['error']))
                with self.store.db:
                    self.store.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (key, time.time(), json.dumps(data)))
                return data
            except urllib.error.HTTPError as e:
                if e.code not in {429, 500, 502, 503, 504} or attempt == 3:
                    raise RuntimeError('API HTTP ' + str(e.code)) from None
                delay = e.headers.get('Retry-After', '')
                time.sleep(float(delay) if delay.isdigit() else 2 ** (attempt + 1))
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise RuntimeError('API non raggiungibile') from None
                time.sleep(2 ** (attempt + 1))

    def mb(self, entity, **params):
        return self.get('https://musicbrainz.org/ws/2/' + entity, {'fmt': 'json', **params})


def resolve(api, name, overrides):
    if name in overrides:
        return overrides[name]
    hits = api.mb('artist', query='artist:' + quote(name), limit=10).get('artists', [])
    def identity(s):
        return re.sub(r'[^a-z0-9]+', '', norm(s).replace('&', ' and '))
    # Search hits can include tribute acts with the seed as an alias.
    # Prefer canonical names; aliases are only a fallback.
    exact = [a for a in hits if identity(a['name']) == identity(name)]
    if not exact:
        exact = [a for a in hits if int(a.get('score', 0)) >= 95 and any(identity(v.get('name', '')) == identity(name) for v in a.get('aliases', []))]
    if exact:
        best = max(int(a.get('score', 0)) for a in exact)
        exact = [a for a in exact if int(a.get('score', 0)) == best]
    if len(exact) != 1:
        options = exact or hits[:3]
        detail = '; '.join(a['name'] + ' (' + a.get('disambiguation', 'senza descrizione') + ') [' + a['id'] + ']' for a in options)
        raise ValueError('identità ambigua/non trovata; imposta artist_ids. Candidati: ' + (detail or 'nessuno'))
    return exact[0]['id']


def candidates(api, counts, config, warnings):
    result = {a: {'reason': 'Nella tua collezione', 'known': True} for a in counts}
    blocked = {norm(a) for a in config['exclude_artists']}
    return {a: info for a, info in result.items() if norm(a) not in blocked}


def classify(release, owned, artist):
    group = release.get('release-group', {})
    original = group.get('first-release-date', '')
    edition = release.get('date', '')
    if re.fullmatch(r'\d{4}(-\d{2}(-\d{2})?)?', original) and original[:4] < edition[:4]:
        return 'Ristampa / nuova edizione di catalogo'
    if (norm(artist), norm(release['title'])) in owned:
        return 'Nuova edizione di un titolo già nel NAS'
    if original and original[:4] == edition[:4]:
        return 'Prima edizione nel catalogo quest’anno; registrazione da verificare'
    return 'Edizione recente; natura da verificare'


def collect(api, artists, owned, cfg, start, end, warnings):
    result = []
    for name, info in artists.items():
        try:
            aid = resolve(api, name, cfg.get('artist_ids', {}))
            offset = 0
            while True:
                data = api.mb('release', query=f'arid:{aid} AND date:[{start} TO {end}] AND status:official', limit=100, offset=offset)
                hits = data.get('releases', [])
                for hit in hits:
                    date = hit.get('date', '')
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
                        warnings.append(f'{name}: data incompleta, edizione {hit["id"]} esclusa')
                        continue
                    if not str(start) <= date <= str(end):
                        continue
                    release = api.mb('release/' + hit['id'], inc='release-groups+media+artist-credits+labels')
                    if release.get('status') != 'Official':
                        continue
                    if aid not in [a['artist']['id'] for a in release.get('artist-credit', []) if isinstance(a, dict) and 'artist' in a]:
                        continue
                    group = release.get('release-group', {})
                    if group.get('primary-type') not in cfg['types']:
                        continue
                    if set(group.get('secondary-types', [])) & set(cfg['exclude_secondary_types']):
                        continue
                    formats = sorted({m.get('format', 'Non specificato') for m in release.get('media', [])})
                    if cfg['formats'] and not set(formats) & set(cfg['formats']):
                        continue
                    # Same work/date/format across territories: one item; different editions retained.
                    identity = [aid, group.get('id', release['id']), date, formats, release.get('disambiguation', '')]
                    itemkey = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                    result.append({'key': itemkey, 'artist': name, 'title': release['title'], 'date': date, 'formats': formats, 'kind': classify(release, owned, name), 'reason': info['reason'], 'known': info['known'], 'url': 'https://musicbrainz.org/release/' + release['id']})
                offset += len(hits)
                if offset >= data.get('count', 0) or not hits:
                    break
        except Exception as e:
            warnings.append(f'{name}: {type(e).__name__}: {e}')
    return list({r['key']: r for r in result}.values())


def reader_notes(warnings):
    notes = []
    incomplete = [w for w in warnings if ': data incompleta, edizione ' in w]
    unresolved = [w.split(':', 1)[0] for w in warnings if ': ValueError: identità ambigua/non trovata' in w]
    if incomplete:
        notes.append(f'{len(incomplete)} edizioni non incluse perché il catalogo non indica una data di pubblicazione completa.')
    if unresolved:
        notes.append('Ricerca da completare per: ' + ', '.join(dict.fromkeys(unresolved)) + '.')
    known = set(incomplete) | {w for w in warnings if ': ValueError: identità ambigua/non trovata' in w or w.startswith('LASTFM_API_KEY assente:')}
    other = [w for w in warnings if w not in known]
    demo = [w for w in other if w.startswith('Anteprima offline:')]
    notes.extend(demo)
    count = len(other) - len(demo)
    if count:
        notes.append(f'{count} ulteriori problemi hanno limitato la ricerca. I dettagli sono disponibili nel report sul Raspberry.')
    return notes


def message(items, warnings, start, end, sender, recipient):
    subject = f'Le tue uscite musicali · {end:%d/%m/%Y}'
    lines = [subject, f'Edizioni pubblicate dal {start} al {end}.', '']
    blocks = []
    for title, group in [('I tuoi artisti', [r for r in items if r['known']])]:
        lines.append(title)
        blocks.append('<h2 style="font-family:Georgia,serif;font-size:27px;font-weight:normal;margin:30px 0 6px;color:#203d39">' + title + '</h2><p style="font-size:13px;color:#79766d;margin:0 0 18px">' + ('Le voci che fanno già parte del tuo mondo musicale.' if title == 'I tuoi artisti' else 'Nuovi percorsi, a partire dai tuoi ascolti preferiti.') + '</p>')
        if not group:
            lines.append('Nessuna nuova segnalazione da aggiungere questa settimana.')
            blocks.append('<p>Nessuna nuova segnalazione da aggiungere questa settimana.</p>')
        for r in sorted(group, key=lambda x: (x['artist'], x['date'])):
            text = f"{r['artist']} — {r['title']} | {r['date']} | {', '.join(r['formats'])} | {r['kind']}\n{r['reason']}\n{r['url']}"
            lines.extend([text, ''])
            catalog = 'Ristampa' in r['kind'] or 'già nel NAS' in r['kind']
            accent, tint, label = ('#95622b', '#f7eedf', 'CATALOGO') if catalog else ('#316b5c', '#eaf2ec', 'NOVITÀ')
            if not r['known']:
                accent, tint, label = '#69618c', '#f0edf7', 'DA SCOPRIRE'
            date = dt.date.fromisoformat(r['date']).strftime('%d.%m.%Y')
            blocks.append(f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;border:1px solid #e6e1d7;border-radius:12px;background:#ffffff"><tr><td style="padding:23px;border-left:4px solid {accent};border-radius:12px">
<span style="display:inline-block;background:{tint};color:{accent};padding:5px 9px;border-radius:4px;font-size:10px;font-weight:bold;letter-spacing:1.3px">{label}</span>
<p style="font-size:13px;letter-spacing:.5px;color:#686b63;margin:18px 0 5px">{html.escape(r['artist'])}</p>
<h3 style="font-family:Georgia,serif;font-size:24px;font-weight:normal;line-height:1.3;margin:0 0 14px;color:#233b35">{html.escape(r['title'])}</h3>
<p style="font-size:12px;line-height:1.6;color:#716d63;margin:0 0 10px">{date} &nbsp;·&nbsp; {html.escape(', '.join(r['formats']))}</p>
<p style="font-size:13px;line-height:1.6;color:{accent};margin:0 0 8px">{html.escape(r['kind'])}</p>
<p style="font-size:12px;line-height:1.6;color:#817c72;margin:0 0 20px">{html.escape(r['reason'])}</p>
<table role="presentation" cellpadding="0" cellspacing="0"><tr><td bgcolor="{accent}" style="border-radius:6px"><a href="{html.escape(r['url'], quote=True)}" style="display:inline-block;padding:11px 17px;color:#ffffff;font-size:12px;font-weight:bold;text-decoration:none">Esplora l’edizione &nbsp;→</a></td></tr></table>
</td></tr></table>''')
    if warnings:
        notes = reader_notes(warnings)
        lines += ['Note sulla selezione', *notes]
        blocks.append('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;background:#f2eee5;border-radius:8px"><tr><td style="padding:18px;font-size:12px;line-height:1.7;color:#756b57"><strong>Note sulla selezione</strong><ul style="padding-left:18px;margin-bottom:0">' + ''.join('<li>' + html.escape(w) + '</li>' for w in notes) + '</ul></td></tr></table>')
    msg = EmailMessage(policy=email.policy.SMTP)
    msg['Subject'], msg['From'], msg['To'] = subject, sender, recipient
    msg.set_content('\n'.join(lines))
    period = f'{start:%d.%m.%Y} — {end:%d.%m.%Y}'
    count = f'{len(items)} edizioni selezionate' if len(items) != 1 else '1 edizione selezionata'
    msg.add_alternative('''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Il venerdì in musica</title></head>
<body style="margin:0;padding:0;background:#eeece5;font-family:Arial,Helvetica,sans-serif;color:#243c35">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all">Le novità dei tuoi artisti e le nuove edizioni di catalogo per il weekend.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#eeece5"><tr><td align="center" style="padding:24px 12px">
<!--[if mso]><table role="presentation" width="640"><tr><td><![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background:#fbfaf6;border:1px solid #e1ddd2">
<tr><td bgcolor="#203d39" style="padding:34px 26px 38px;color:#f9f5e9">
<p style="font-size:10px;font-weight:bold;letter-spacing:3px;color:#c3d0b8;margin:0 0 25px">ROON BUDDY &nbsp;/&nbsp; LA TUA SELEZIONE SETTIMANALE</p>
<h1 style="font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.2;font-weight:normal;white-space:nowrap;margin:0 0 18px">Il venerdì in musica</h1>
<p style="font-size:14px;line-height:1.8;color:#d1dccf;margin:0">Artisti di casa. Dischi da ritrovare.<br>Qualcosa di nuovo da portare nel weekend.</p>
</td></tr><tr><td style="padding:16px 26px;background:#e7ecdf;font-size:11px;line-height:1.8;letter-spacing:.6px;color:#365447">''' + period + ' &nbsp;·&nbsp; ' + count + '''</td></tr>
<tr><td style="padding:0 26px 30px">''' + ''.join(blocks) + '''</td></tr>
<tr><td style="border-top:1px solid #e3dfd4;padding:23px 26px;font-size:11px;line-height:1.8;color:#888174"><strong style="color:#536858;letter-spacing:1px">BUON ASCOLTO.</strong><br>Selezione dalla tua collezione · Dati MusicBrainz.<br>Le date si riferiscono alle edizioni. La copertura dei cataloghi può essere incompleta.</td></tr>
</table><!--[if mso]></td></tr></table><![endif]-->
</td></tr></table></body></html>''', subtype='html')
    return msg


def send(msg, cfg):
    smtp = cfg['smtp']
    password = os.environ[smtp['password_env']]
    context = ssl.create_default_context()
    cls = smtplib.SMTP_SSL if smtp['mode'] == 'ssl' else smtplib.SMTP
    kwargs = {'context': context} if smtp['mode'] == 'ssl' else {}
    with cls(smtp['host'], smtp['port'], timeout=40, **kwargs) as server:
        if smtp['mode'] == 'starttls':
            server.starttls(context=context)
        elif smtp['mode'] != 'ssl':
            raise ValueError('SMTP: usa ssl o starttls')
        server.login(smtp['username'], password)
        refused = server.send_message(msg)
        if refused:
            raise RuntimeError('SMTP: destinatari rifiutati')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='config.toml' if tomllib is not None else 'config.json')
    p.add_argument('--send', action='store_true', help='Invia via SMTP; altrimenti anteprima')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--fixture', help='JSON offline con items e warnings')
    p.add_argument('--date', type=dt.date.fromisoformat)
    p.add_argument('--limit-artists', type=int, help='Test live su un sottoinsieme; vietato con --send')
    args = p.parse_args()
    if args.send and (args.dry_run or args.fixture or args.limit_artists is not None):
        p.error('--send incompatibile con dry-run, fixture e sottoinsieme')
    base = Path(args.config).resolve().parent
    source = Path(args.config).read_text(encoding='utf-8')
    if Path(args.config).suffix == '.json':
        cfg = json.loads(source)
    elif tomllib is not None:
        cfg = tomllib.loads(source)
    else:
        raise SystemExit('Con Python 3.9/3.10 usa --config config.json')
    load_environment(cfg, base)
    end = args.date or dt.datetime.now(ZoneInfo(cfg['timezone'])).date()
    start = end - dt.timedelta(days=cfg['lookback_days'] - 1)
    state = base / cfg['state_dir']
    state.mkdir(parents=True, exist_ok=True)
    with open(state / 'run.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Un’altra esecuzione è già attiva')
        store = Store(state / 'history.sqlite')
        warnings = []
        if args.fixture:
            fixture = json.loads(Path(args.fixture).read_text())
            items, warnings = fixture['items'], fixture.get('warnings', [])
        else:
            contact = cfg['contact']
            if not contact or 'example' in contact:
                raise SystemExit('Configura contact con un indirizzo reale')
            counts, owned = library(base / cfg['csv'], cfg.get('aliases', {}), cfg.get('collaborations', {}))
            api = API(store, 'RoonWeekly/1.0 (' + contact + ')')
            artists = candidates(api, counts, cfg, warnings)
            if args.limit_artists is not None:
                artists = dict(list(artists.items())[:args.limit_artists])
            items = collect(api, artists, owned, cfg, start, end, warnings)
        items = [r for r in items if not store.seen(r['key'])]
        msg = message(items, warnings, start, end, cfg['smtp']['sender'], cfg['smtp']['recipient'])
        (state / 'preview.eml').write_bytes(msg.as_bytes())
        (state / 'preview.html').write_text(msg.get_body(preferencelist=('html',)).get_content(), encoding='utf-8')
        (state / 'report.json').write_text(json.dumps({'start': str(start), 'end': str(end), 'items': items, 'warnings': warnings}, ensure_ascii=False, indent=2))
        print(f'{len(items)} segnalazioni; {len(warnings)} avvisi; anteprima: {state / "preview.html"}')
        if args.send:
            send(msg, cfg)
            store.mark([r['key'] for r in items])
            print('Email inviata e segnalazioni registrate.')
        store.db.close()


if __name__ == '__main__':
    main()
