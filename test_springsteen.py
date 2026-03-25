import csv
import os

# Configurazione basata sulla tua struttura reale
CSV_FILE = "RoonBuddy.csv"
# Simuliamo il 27 Marzo (MMDD) per Bruce
target_date = "0327" 

print(f"--- TEST DIAGNOSTICO: SIMULAZIONE 27 MARZO ---")

if not os.path.exists(CSV_FILE):
    print(f"❌ ERRORE: Il file {CSV_FILE} non è nella cartella attuale.")
    print(f"Directory corrente: {os.getcwd()}")
else:
    try:
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            # Usiamo il punto e virgola come delimitatore
            reader = csv.DictReader(f, delimiter=';')
            
            found = False
            for row in reader:
                # Il tuo CSV ha la colonna 'Date'
                released = row.get('Date', '')
                
                # Verifichiamo se la data finisce con 0327
                if released and str(released).endswith(target_date):
                    # Usiamo i nomi colonne: 'Album Artist' e 'Title'
                    artist = row.get('Album Artist', 'Sconosciuto')
                    title = row.get('Title', 'Sconosciuto')
                    year = str(released)[:4] # Estraiamo l'anno (YYYY)
                    
                    print(f"✅ MATCH TROVATO!")
                    print(f"   Artista: {artist}")
                    print(f"   Album:   {title}")
                    print(f"   Anno:    {year}")
                    print(f"   Stringa data nel CSV: {released}")
                    found = True
            
            if not found:
                print(f"❌ Nessun match trovato per il {target_date}.")
                print("Suggerimento: Verifica che nel CSV non ci siano spazi dopo il punto e virgola.")
                
    except Exception as e:
        print(f"❌ Errore durante la lettura del file: {e}")

print(f"----------------------------------------------")
