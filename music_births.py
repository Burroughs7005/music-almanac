#!/usr/bin/env python3
import os
import sys
import datetime
import time
import re
import pandas as pd
import musicbrainzngs
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

musicbrainzngs.set_useragent("RoonAlmanacBuddy", "1.5", EMAIL_USER)

def clean_and_split_artists(artist_string):
    if not isinstance(artist_string, str):
        return []
    # Splitta in modo pulito eliminando i separatori di collaborazione
    raw_names = re.split(r'\s+&\s+|\s+/\s+|\s+and\s+|\s+with\s+|\s+feat\.\s+', artist_string, flags=re.IGNORECASE)
    cleaned = []
    for name in raw_names:
        name_clean = name.strip()
        if name_clean and not any(x in name_clean.lower() for x in [' & ', ' / ', ' and ', ' with ']):
            cleaned.append(name_clean)
    return cleaned

def fetch_artist_dates(artist_name):
    events = []
    # Salta stringhe sporche o vuote
    if not artist_name or any(x in artist_name.lower() for x in [' & ', ' / ', ' and ', ' with ', ' feat ']):
        return events
        
    try:
        # Query di ricerca rigorosa per nome esatto (campo artist racchiuso tra virgolette)
        query_str = f'artist:"{artist_name}"'
        result = musicbrainzngs.search_artists(query=query_str, limit=10)
        if not result['artist-list']:
            return events
            
        best_match = None
        for candidate in result['artist-list']:
            # Controllo di uguaglianza totale e rigorosa sul nome per evitare omonimie o album collaborativi
            if candidate['name'].strip().lower() == artist_name.lower():
                best_match = candidate
                break
                
        if not best_match:
            return events
            
        artist_id = best_match['id']
        details = musicbrainzngs.get_artist_by_id(artist_id, includes=["artist-rels"])
        artist_info = details['artist']
        entity_type = artist_info.get('type')
        
        if entity_type == 'Person':
            birth = artist_info.get('life-span', {}).get('begin')
            death = artist_info.get('life-span', {}).get('end')
            is_dead = artist_info.get('life-span', {}).get('ended') == 'true' or death is not None
            
            if birth and re.match(r'^\d{4}-\d{2}-\d{2}$', birth): 
                events.append({'artist_key': artist_name, 'subject': artist_name, 'type': 'Nascita', 'date': birth, 'is_dead': is_dead})
            if death and re.match(r'^\d{4}-\d{2}-\d{2}$', death): 
                events.append({'artist_key': artist_name, 'subject': artist_name, 'type': 'Morte', 'date': death, 'is_dead': is_dead})
            
        elif entity_type == 'Group':
            for rel in artist_info.get('artist-relation-list', []):
                if rel['type'] == 'member of' and rel.get('direction') == 'backward':
                    member = rel['artist']
                    m_name = member['name']
                    birth = member.get('life-span', {}).get('begin')
                    death = member.get('life-span', {}).get('end')
                    m_is_dead = member.get('life-span', {}).get('ended') == 'true' or death is not None
                    
                    if birth and re.match(r'^\d{4}-\d{2}-\d{2}$', birth): 
                        events.append({'artist_key': artist_name, 'subject': f"{m_name} ({artist_name})", 'type': 'Nascita', 'date': birth, 'is_dead': m_is_dead})
                    if death and re.match(r'^\d{4}-\d{2}-\d{2}$', death): 
                        events.append({'artist_key': artist_name, 'subject': f"{m_name} ({artist_name})", 'type': 'Morte', 'date': death, 'is_dead': m_is_dead})
    except Exception as e:
        print(f"Errore con l'artista '{artist_name}': {e}", file=sys.stderr)
    return events

def build_cache():
    if not os.path.exists(INPUT_CSV):
        print(f"Errore: Il file {INPUT_CSV} non esiste.", file=sys.stderr)
        return
    print("Inizio scansione atomica e pulizia della libreria RoonBuddy...")
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
        print(f"[{idx}/{total}] Verifica MusicBrainz Strict: {artist}")
        all_events.extend(fetch_artist_dates(artist))
        time.sleep(1.2)
        
    if all_events:
        pd.DataFrame(all_events).to_csv(CACHE_CSV, index=False)
        print(f"\nCache rigenerata con successo ({len(all_events)} eventi memorizzati).")
    else:
        print("\nNessun dato valido trovato.")

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
        print("Nessun anniversario musicale valido per oggi.")
        return

    nascite = [r for r in ricorrenze_oggi if r['type'] == 'Nascita']
    morti = [r for r in ricorrenze_oggi if r['type'] == 'Morte']

    html_content = "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
    html_content += "body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f6f8; color: #333; margin: 0; padding: 20px; }"
    html_content += ".container { max-width: 600px; background-color: #ffffff; margin: 0 auto; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }"
    html_content += ".header { background: linear-gradient(135deg, #1f2937, #111827); color: #ffffff; padding: 25px 20px; text-align: center; }"
    html_content += ".header h1 { margin: 0; font-size: 20px; font-weight: 600; letter-spacing: 1.5px; color: #f3f4f6; }"
    html_content += ".header p { margin: 5px 0 0 0; font-size: 13px; color: #9ca3af; }"
    html_content += ".content { padding: 25px 20px; }"
    html_content += ".section-title { font-size: 13px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: bold; margin-top: 25px; margin-bottom: 12px; padding-bottom: 4px; }"
    html_content += ".title-birth { color: #0d9488; border-bottom: 2px solid #ccfbf1; }"
    html_content += ".title-death { color: #64748b; border-bottom: 2px solid #e2e8f0; }"
    html_content += ".event-card { padding: 12px 15px; margin-bottom: 10px; border-radius: 0 6px 6px 0; }"
    html_content += ".card-birth { border-left: 4px solid #0d9488; background-color: #f0fdfa; }"
    html_content += ".card-death { border-left: 4px solid #64748b; background-color: #f8fafc; }"
    html_content += ".artist-name { font-size: 15px; font-weight: 600; color: #1f2937; }"
    html_content += ".event-details { font-size: 13px; color: #4b5563; margin-top: 2px; }"
    html_content += ".badge-centenario { background-color: #d97706; color: #ffffff; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: bold; display: inline-block; margin-left: 6px; vertical-align: middle; }"
    html_content += ".footer { background-color: #f3f4f6; padding: 15px; text-align: center; font-size: 11px; color: #9ca3af; border-top: 1px solid #e5e7eb; }"
    html_content += "</style></head><body><div class='container'><div class='header'>"
    html_content += "<h1>ROON BUDDY ALMANAC</h1>"
    html_content += "<p>Ricorrenze del giorno • " + datetime.datetime.now().strftime('%d %B %Y') + "</p>"
    html_content += "</div><div class='content'>"
    html_content += "<p style='margin-top:0; font-size: 14px; color:#4b5563;'>Buongiorno Andrea, ecco gli anniversari di oggi:</p>"

    if nascite:
        html_content += "<div class='section-title title-birth'>🎂 Nascite ed Anniversari</div>"
        for n in nascite:
            badge = "<span class='badge-centenario'>✨ CENTENARIO</span>" if n['delta'] == 100 else ""
            dettaglio = f"Avrebbe compiuto <strong>{n['delta']} anni</strong> (nato nel {n['anno']})" if n['is_dead'] else f"Compie <strong>{n['delta']} anni</strong> (nato nel {n['anno']})"
            html_content += f"<div class='event-card card-birth'><div class='artist-name'>{n['subject']}{badge}</div><div class='event-details'>{dettaglio}</div></div>"

    if morti:
        html_content += "<div class='section-title title-death'>🖤 Anniversari della Scomparsa</div>"
        for m in morti:
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
