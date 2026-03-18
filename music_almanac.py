import requests
import datetime
import urllib.parse
import subprocess
import os
import re
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

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
    """Controllo avanzato: blocca se il titolo è simile o contenuto in uno recente."""
    today = datetime.date.today()
    clean_title = re.sub(r'\(.*?\)', '', title).strip().lower() # Rimuove parentesi es. (Part 1)
    
    for entry in history:
        if "|" in entry:
            try:
                date_str, sent_title = entry.split("|", 1)
                sent_date = datetime.date.fromisoformat(date_str)
                if (today - sent_date).days < days:
                    # Confronto fuzzy semplice: se uno è contenuto nell'altro
                    clean_sent = re.sub(r'\(.*?\)', '', sent_title).strip().lower()
                    if clean_title in clean_sent or clean_sent in clean_title:
                        return True
            except: continue
    return False

def load_my_artists(filepath):
    if not os.path.exists(filepath): return set()
    artists = set()
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            clean_name = line.split("]")[-1].strip().lower() if "]" in line else line.strip().lower()
            if clean_name and "nome_artista" not in clean_name:
                artists.add(clean_name)
    return artists

def get_wiki_matches(my_artists):
    today = datetime.date.today()
    day, month = str(today.day), today.strftime("%B")
    matches = []
    history = load_sent_albums()
    headers = {'User-Agent': 'Mozilla/5.0'}

    # Scansione doppia: Liste Album + "Year in Music"
    for year in range(1960, 2025):
        urls = [
            f"https://en.wikipedia.org/wiki/List_of_{year}_albums",
            f"https://en.wikipedia.org/wiki/{year}_in_music"
        ]
        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code != 200: continue
                soup = BeautifulSoup(r.text, 'html.parser')
                for element in soup.find_all(['tr', 'li']):
                    text = element.get_text(separator=" ").strip()
                    if month in text and f" {day} " in f" {text} ":
                        links = element.find_all('a')
                        if len(links) >= 2:
                            artist_raw = links[0].get_text(strip=True)
                            title = links[1].get_text(strip=True).replace('"', '')
                            
                            if artist_raw.lower() in my_artists:
                                if is_recent_duplicate(title, history): continue
                                if not any(m['title'] == title for m in matches):
                                    matches.append({'artist': artist_raw, 'title': title, 'year': str(year)})
                                    save_sent_album(title)
                                    print(f"  🎵 MATCH: {title} ({year})")
            except: continue
    return sorted(matches, key=lambda x: x['year'], reverse=True)

def generate_rss(albums):
    fg = FeedGenerator()
    fg.id("https://github.com/Burroughs7005/music-almanac")
    fg.title('Almanacco Musicale (Roon Library Edition)')
    fg.description('Anniversari musicali filtrati sulla tua libreria.')
    fg.link(href="https://github.com/Burroughs7005/music-almanac", rel='alternate')
    
    fe = fg.add_entry()
    today = datetime.date.today()
    fe.id(f"{today}_v16_deep_scan")
    fe.title(f"Accadde oggi nella tua libreria: {today.strftime('%d/%m')}")
    
    content = "<h3>Anniversari della tua libreria:</h3><ul>"
    if not albums:
        content += "<li>Nessun nuovo match trovato oggi.</li>"
    else:
        for alb in albums:
            q = urllib.parse.quote(f"{alb['artist']} {alb['title']}")
            s_link = f"http://googleusercontent.com/spotify.com/{q}"
            y_link = f"https://www.youtube.com/results?search_query={q}+album"
            content += f"<li><strong>{alb['title']}</strong> - {alb['artist']} ({alb['year']})<br><small><a href='{s_link}'>Spotify</a> | <a href='{y_link}'>YouTube</a></small></li>"
    content += "</ul>"
    fe.content(content, type='html')
    fg.rss_file('music_history.xml')

if __name__ == "__main__":
    my_artists = load_my_artists('artists.txt')
    print(f"Caricati {len(my_artists)} artisti. Avvio deep scan...")
    data = get_wiki_matches(my_artists)
    generate_rss(data)
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"Deep Scan {datetime.date.today()}"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
    except: pass
