import csv
import datetime
import urllib.parse
import subprocess
import os
import re
from feedgen.feed import FeedGenerator

# Configurazione
CSV_FILE = "RoonBuddy.csv"
LOG_FILE = "sent_albums.log"

def load_sent_albums():
    if not os.path.exists(LOG_FILE): return []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines()]

def save_sent_album(title):
    today = datetime.date.today().isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{today}|{title}\n")

def is_recent_duplicate(title, history, days=7):
    today = datetime.date.today()
    clean_title = title.strip().lower()
    for entry in history:
        if "|" in entry:
            try:
                date_str, sent_title = entry.split("|", 1)
                if sent_title.lower() == clean_title:
                    sent_date = datetime.date.fromisoformat(date_str)
                    if (today - sent_date).days < days:
                        return True
            except: continue
    return False

def get_roon_matches():
    today = datetime.date.today()
    today_str = today.strftime("%d/%m") # Formato DD/MM per match
    matches = []
    history = load_sent_albums()

    print(f"[{datetime.datetime.now()}] Ricerca anniversari nel database Roon per il {today_str}...")

    if not os.path.exists(CSV_FILE):
        print(f"Errore: {CSV_FILE} non trovato!")
        return []

    with open(CSV_FILE, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            released = row.get('Released', '')
            # Gestione formati data comuni (DD/MM/YYYY o YYYY-MM-DD)
            if released and today_str in released:
                artist = row.get('Artist', 'Unknown Artist')
                title = row.get('Album', 'Unknown Album')
                year = released.split('/')[-1] if '/' in released else released.split('-')[0]

                if is_recent_duplicate(title, history):
                    continue

                matches.append({'artist': artist, 'title': title, 'year': year})
                save_sent_album(title)
                print(f"  🎵 MATCH LIBRERIA: {title} - {artist} ({year})")

    return sorted(matches, key=lambda x: x['year'], reverse=True)

def generate_rss(albums):
    fg = FeedGenerator()
    fg.id("https://github.com/Burroughs7005/music-almanac")
    fg.title('Almanacco Musicale (Roon Personal Edition)')
    fg.description('Anniversari basati sulla TUA libreria Roon personalizzata.')
    fg.link(href="https://github.com/Burroughs7005/music-almanac", rel='alternate')
    
    fe = fg.add_entry()
    today = datetime.date.today()
    fe.id(f"{today}_v_roon_master")
    fe.title(f"Accadde oggi nella tua libreria: {today.strftime('%d/%m')}")
    
    content = "<h3>Anniversari della tua libreria Roon:</h3><ul>"
    if not albums:
        content += "<li>Nessun anniversario trovato per oggi nei tuoi dati.</li>"
    else:
        for alb in albums:
            q = urllib.parse.quote(f"{alb['artist']} {alb['title']}")
            s_link = f"https://open.spotify.com/search/{q}"
            y_link = f"https://www.youtube.com/results?search_query={q}"
            content += f"<li><strong>{alb['title']}</strong> - {alb['artist']} ({alb['year']})<br><small><a href='{s_link}'>Spotify</a> | <a href='{y_link}'>YouTube</a></small></li>"
    content += "</ul>"
    fe.content(content, type='html')
    fg.rss_file('music_history.xml')

if __name__ == "__main__":
    data = get_roon_matches()
    generate_rss(data)
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"Roon Database Update {datetime.date.today()}"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("Operazione completata con successo.")
    except:
        pass
