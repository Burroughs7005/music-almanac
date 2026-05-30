#!/usr/bin/env python3
import os
import sys
import datetime
import re
import pandas as pd
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BASE_DIR = "/home/pi/music-almanac"
INPUT_CSV = os.path.join(BASE_DIR, "RoonBuddy.csv")
CACHE_CSV = os.path.join(BASE_DIR, "artists_bio_cache.csv")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
EMAIL_USER = "andrea.lutri@gmail.com"
EMAIL_PASS = os.environ.get("ROON_ALMANAC_PASS", "kxzrstdkuqcgfccg")

def clean_and_split_artists(artist_string):
    if not isinstance(artist_string, str):
        return []
    # Splitta in modo pulito su congiunzioni e slash
    raw_names = re.split(r'\s+&\s+|\s+/\s+|\s+and\s+|\s+with\s+|\s+feat\.\s+|/', artist_string, flags=re.IGNORECASE)
    cleaned = []
    for name in raw_names:
        name_clean = name.strip()
        if name_clean and len(name_clean) > 1:
            cleaned.append(name_clean)
    return cleaned

def fetch_wikidata_api(artist_name):
    """Cerca l'artista usando l'API nativa di Wikidata con filtro anti-omonimia per musicisti"""
    search_url = "https://www.wikidata.org/w/api.php"
    headers = {'User-Agent': 'RoonAlmanacBuddy/3.0 (andrea.lutri@gmail.com)'}
    events = []
    try:
        search_params = {
            'action': 'wbsearchentities',
            'search': artist_name,
            'language': 'en',
            'format': 'json',
            'limit': 5  # Più candidati per scovare il musicista se nascosto sotto un omonimo
        }
        r_search = requests.get(search_url, params=search_params, headers=headers, timeout=10)
        if r_search.status_code != 200:
            return events
            
        results = r_search.json().get('search', [])
        if not results:
            search_params['language'] = 'it'
            r_search = requests.get(search_url, params=search_params, headers=headers, timeout=10)
            results = r_search.json().get('search', [])
            
        if not results:
            return events

        # LOGICA ANTI-OMONIMIA: Cerchiamo il candidato che appartenga al mondo della musica
        entity_id = None
        parole_chiave_musica = ['music', 'musician', 'composer', 'singer', 'band', 'jazz', 'pianist', 'guitarist', 'producer', 'rock', 'pop']
        parole_chiave_escludi = ['actor', 'actress', 'footballer', 'politician', 'player', 'film', 'movie']

        # 1. Tentativo: Cerca qualcuno che abbia una descrizione esplicitamente musicale
        for cand in results:
            desc = cand.get('description', '').lower()
            label = cand.get('label', '').lower()
            
            if label == artist_name.lower() or cand.get('match', {}).get('text', '').lower() == artist_name.lower():
                if any(kw in desc for kw in parole_chiave_musica):
                    entity_id = cand['id']
                    break

        # 2. Tentativo: Se mancano parole chiave musicali, prendiamo il primo che NON sia un attore/sportivo esplicito
        if not entity_id:
            for cand in results:
                desc = cand.get('description', '').lower()
                label = cand.get('label', '').lower()
                if label == artist_name.lower() or cand.get('match', {}).get('text', '').lower() == artist_name.lower():
                    if not any(kw in desc for kw in parole_chiave_escludi):
                        entity_id = cand['id']
                        break

        # 3. Fallback: Se tutti i filtri falliscono, prendiamo il primo risultato
        if not entity_id:
            entity_id = results[0]['id']

        entity_params = {
            'action': 'wbgetentities',
            'ids': entity_id,
            'format': 'json',
            'props': 'claims'
        }
        r_entity = requests.get(search_url, params=entity_params, headers=headers, timeout=10)
        if r_entity.status_code != 200:
            return events
            
        claims = r_entity.json().get('entities', {}).get(entity_id, {}).get('claims', {})
        birth_claims = claims.get('P569', [])
        death_claims = claims.get('P570', [])
        is_dead = len(death_claims) > 0
        
        if birth_claims:
            b_time = birth_claims[0].get('mainsnak', {}).get('datavalue', {}).get('value', {}).get('time', '')
            if b_time:
                b_date = b_time.lstrip('+').split('T')[0]
                if re.match(r'^\d{4}-\d{2}-\d{2}$', b_date) and not b_date.startswith('0000'):
                    events.append({'artist_key': artist_name, 'subject': artist_name, 'type': 'Nascita', 'date': b_date, 'is_dead': is_dead})
                    
        if death_claims:
            d_time = death_claims[0].get('mainsnak', {}).get('datavalue', {}).get('value', {}).get('time', '')
            if d_time:
                d_date = d_time.lstrip('+').split('T')[0]
                if re.match(r'^\d{4}-\d{2}-\d{2}$', d_date) and not d_date.startswith('0000'):
                    events.append({'artist_key': artist_name, 'subject': artist_name, 'type': 'Morte', 'date': d_date, 'is_dead': is_dead})
    except Exception as e:
        pass
    return events

def build_cache():
    if not os.path.exists(INPUT_CSV):
        print(f"Errore: Il file {INPUT_CSV} non esiste.", file=sys.stderr)
        return
    print("Inizio scansione atomica della libreria RoonBuddy con Wikidata API...")
    try:
        df_roon = pd.read_csv(INPUT_CSV, sep=None, engine='python')
        artist_col = [col for col in df_roon.columns if 'artist' in col.lower()][0]
        raw_artists = df_roon[artist_col].dropna().unique()
        
        individual_artists = set()
        for ra in raw_artists:
            for clean_name in clean_and_split_artists(ra):
                individual_artists.add(clean_name)
        artists = sorted(list(individual_artists))
    except Exception as e:
        print(f"Errore nella lettura di RoonBuddy.csv: {e}", file=sys.stderr)
        return

    all_events = []
    total = len(artists)
    for idx, artist in enumerate(artists, 1):
        print(f"[{idx}/{total}] Controllo API Wikidata: {artist}")
        all_events.extend(fetch_wikidata_api(artist))
        
    if all_events:
        pd.DataFrame(all_events).to_csv(CACHE_CSV, index=False)
        print(f"\nCache rigenerata via Wikidata API ({len(all_events)} eventi salvati).")
    else:
        print("\nNessun dato biografico trovato.")

def run_daily_almanac():
    if not os.path.exists(CACHE_CSV):
        build_cache()
        if not os.path.exists(CACHE_CSV):
            return

    df = pd.read_csv(CACHE_CSV)
    oggi = datetime.datetime.now().strftime("%m-%d")
    anno_corrente = datetime.datetime.now().year
    ricorrenze_oggi = []
    
    for _, row in df.iterrows():
        date_str = str(row['date'])
        if len(date_str) == 10 and date_str.endswith(f"-{oggi}"):
            anno_evento = int(date_str.split('-')[0])
            ricorrenze_oggi.append({
                'subject': row['subject'],
                'type': row['type'],
                'anno': anno_evento,
                'delta': anno_corrente - anno_evento,
                'is_dead': str(row.get('is_dead', 'False')).lower() == 'true'
            })

    if not ricorrenze_oggi:
        print("Nessun anniversario musicale valido trovato per oggi.")
        return

    # Divisione rigorosa in tre categorie distinte
    compleanni = [r for r in ricorrenze_oggi if r['type'] == 'Nascita' and not r['is_dead']]
    nascite_ricorrenze = [r for r in ricorrenze_oggi if r['type'] == 'Nascita' and r['is_dead']]
    scomparse = [r for r in ricorrenze_oggi if r['type'] == 'Morte']

    css_style = """
    body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f6f8; color: #333; margin: 0; padding: 20px; }
    .container { max-width: 600px; background-color: #ffffff; margin: 0 auto; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    .header { background: linear-gradient(135deg, #1f2937, #111827); color: #ffffff; padding: 25px 20px; text-align: center; }
    .header h1 { margin: 0; font-size: 20px; font-weight: 600; letter-spacing: 1.5px; color: #f3f4f6; }
    .header p { margin: 5px 0 0 0; font-size: 13px; color: #9ca3af; }
    .content { padding: 25px 20px; }
    .section-title { font-size: 13px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: bold; margin-top: 25px; margin-bottom: 12px; padding-bottom: 4px; }
    .title-birthday { color: #0d9488; border-bottom: 2px solid #ccfbf1; }
    .title-memory { color: #b45309; border-bottom: 2px solid #fef3c7; }
    .title-death { color: #64748b; border-bottom: 2px solid #e2e8f0; }
    .event-card { padding: 12px 15px; margin-bottom: 10px; border-radius: 0 6px 6px 0; }
    .card-birthday { border-left: 4px solid #0d9488; background-color: #f0fdfa; }
    .card-memory { border-left: 4px solid #d97706; background-color: #fffbec; }
    .card-death { border-left: 4px solid #64748b; background-color: #f8fafc; }
    .artist-name { font-size: 15px; font-weight: 600; color: #1f2937; }
    .event-details { font-size: 13px; color: #4b5563; margin-top: 2px; }
    .badge-centenario { background-color: #d97706; color: #ffffff; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: bold; display: inline-block; margin-left: 6px; vertical-align: middle; }
    .footer { background-color: #f3f4f6; padding: 15px; text-align: center; font-size: 11px; color: #9ca3af; border-top: 1px solid #e5e7eb; }
    """

    html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{css_style}</style></head>"
    html_content += "<body><div class='container'><div class='header'>"
    html_content += "<h1>ROON BUDDY ALMANAC</h1>"
    html_content += "<p>Ricorrenze del giorno • " + datetime.datetime.now().strftime('%d %B %Y') + "</p>"
    html_content += "</div><div class='content'>"
    html_content += "<p style='margin-top:0; font-size: 14px; color:#4b5563;'>Buongiorno Andrea, ecco gli anniversari di oggi:</p>"

    # SEZIONE 1: COMPLEANNI (VIVI)
    if compleanni:
        html_content += "<div class='section-title title-birthday'>🎂 Festeggiano Oggi</div>"
        for n in compleanni:
            badge = "<span class='badge-centenario'>✨ CENTENARIO</span>" if n['delta'] == 100 else ""
            html_content += f"<div class='event-card card-birthday'><div class='artist-name'>{n['subject']}{badge}</div><div class='event-details'>Compie <strong>{n['delta']} anni</strong> (nato nel {n['anno']})</div></div>"

    # SEZIONE 2: RICORRENZE NASCITA (ARTISTI SCOMPARSI)
    if nascite_ricorrenze:
        html_content += "<div class='section-title title-memory'>🕯️ Ricorrenze della Nascita</div>"
        for n in nascite_ricorrenze:
            badge = "<span class='badge-centenario'>✨ CENTENARIO</span>" if n['delta'] == 100 else ""
            html_content += f"<div class='event-card card-memory'><div class='artist-name'>{n['subject']}{badge}</div><div class='event-details'>Avrebbe compiuto <strong>{n['delta']} anni</strong> (nato nel {n['anno']})</div></div>"

    # SEZIONE 3: ANNIVERSARI SCOMPARSA
    if scomparse:
        html_content += "<div class='section-title title-death'>🖤 Anniversari della Scomparsa</div>"
        for m in scomparse:
            html_content += f"<div class='event-card card-death'><div class='artist-name'>{m['subject']}</div><div class='event-details'>Scomparso nel <strong>{m['anno']}</strong> — {m['delta']} anni fa</div></div>"

    html_content += "</div><div class='footer'>Generato da glasgy.pi • RoonBuddy Almanac Project</div></div></body></html>"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Music Almanac: Ricorrenze del " + datetime.datetime.now().strftime('%d/%m')
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_USER
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print("Email dell'almanacco inviata con successo.")
    except Exception as e:
        print(f"Errore nell'invio dell'email: {e}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        build_cache()
    else:
        run_daily_almanac()
