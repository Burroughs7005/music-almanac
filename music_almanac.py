import csv
import datetime
import urllib.parse
import subprocess
import os
from feedgen.feed import FeedGenerator

# Configurazione per glasgy
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
    for entry in history:
        if "|" in entry:
            try:
                date_str, sent_title = entry.split("|", 1)
                if sent_title.lower() == title.strip().lower():
                    sent_date = datetime.date.fromisoformat(date_str)
                    if (today - sent_date).days < days:
                        return True
            except: continue
    return False

def get_roon_matches():
    today = datetime.date.today()
    target_date = today.strftime("%m%d") 
    matches = []
    history = load_sent_albums()

    print(f"[{datetime.datetime.now()}] Scansione RoonBuddy per il {today.strftime('%d/%m')}...")

    if not os.path.exists(CSV_FILE):
        print(f"Errore: {CSV_FILE} non trovato!")
        return []

    with open(CSV_FILE, mode='r', encoding='utf-8') as f:
        # Usiamo il punto e virgola come delimitatore
        reader = csv.reader(f, delimiter=';')
        next(reader) # Salta la riga dell'intestazione
        
        for row in reader:
            # Salta righe vuote o malformate
            if len(row) < 3: continue
            
            artist = row[0].strip()   # Colonna 1: Artista
            title = row[1].strip()    # Colonna 2: Titolo Album
            released = row[2].strip() # Colonna 3: Data (YYYYMMDD)
            
            # Controllo match (es. se finisce con '0327')
            if released and str(released).endswith(target_date):
                year = str(released)[:4]

                if is_recent_duplicate(title, history):
                    continue

                matches.append({'artist': artist, 'title': title, 'year': year})
                save_sent_album(title)
                print(f"  🎵 MATCH TROVATO: {title} - {artist} ({year})")

    return sorted(matches, key=lambda x: x['year'], reverse=True)

def generate_rss(albums):
    fg = FeedGenerator()
    fg.id("https://github.com/Burroughs7005/music-almanac")
    fg.title('Almanacco Musicale (Roon Master)')
    fg.description('Anniversari reali dalla tua libreria personale.')
    fg.link(href="https://github.com/Burroughs7005/music-almanac", rel='alternate')
    
    fe = fg.add_entry()
    today = datetime.date.today()
    fe.id(f"{today}_v_master_final")
    fe.title(f"Accadde oggi nella tua libreria: {today.strftime('%d/%m')}")
    
    content = "<h3>Anniversari della tua libreria:</h3><ul>"
    if not albums:
        content += "<li>Nessun anniversario trovato per oggi nei tuoi dati Roon.</li>"
    else:
        for alb in albums:
            q = urllib.parse.quote(f"{alb['artist']} {alb['title']}")
            s_link = f"http://googleusercontent.com/spotify.com/{q}"
            y_link = f"https://www.youtube.com/results?search_query={q}"
            content += f"<li><strong>{alb['title']}</strong> - {alb['artist']} ({alb['year']})<br><small><a href='{s_link}'>Spotify</a> | <a href='{y_link}'>YouTube</a></small></li>"
    content += "</ul>"
    fe.content(content, type='html')
    fg.rss_file('music_history.xml')

if __name__ == "__main__":
    data = get_roon_matches()
    generate_rss(data)
    try:
        # Automatizzazione Git
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"Roon Almanac Update {datetime.date.today()}"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
    except Exception as e:
        print(f"Nota: Git push non eseguito o nessun cambiamento ({e})")
