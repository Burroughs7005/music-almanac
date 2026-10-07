# Le tue uscite musicali del venerdì

Python 3.9 o superiore (config.json; TOML richiede 3.11), Linux/NAS o macOS; nessuna dipendenza esterna. Su glasgy usa run.sh, che legge config.json. Il CSV originale è incluso. Il programma cerca album ed EP ufficiali, comprende le edizioni di catalogo e genera un'email italiana in HTML con alternativa testo.

Per Gmail e il Raspberry Pi **glasgy**, segui `GLASGY.md`: server Gmail già impostato, credenziali locali con `run.sh` e attività del venerdì.

## Avvio

Apri un terminale nella cartella del progetto. Modifica `config.toml`: inserisci il tuo contatto reale, dati SMTP e indirizzi. Puoi scegliere `Europe/Rome` per un NAS impostato sull'orario italiano; il valore iniziale è `Europe/London`.

```sh
python3 -m unittest discover -s tests -v
python3 weekly.py --fixture demo.json --dry-run --date 2026-10-02
```

Apri `state/preview.html` oppure `state/preview.eml`. I titoli della demo sono **fittizi**. La demo non usa la rete e non può inviare email.

Per una prova reale su tre artisti:

```sh
python3 weekly.py --dry-run --limit-artists 3
```

Poi esegui la ricerca completa, senza invio:

```sh
python3 weekly.py --dry-run
```

Per affinità automatiche, imposta `LASTFM_API_KEY` nell'ambiente. Richiedi la chiave su https://www.last.fm/api/account/create. È sufficiente la chiave: non servono password Last.fm né API secret. Senza chiave funziona solo la ricerca sugli artisti posseduti, con avviso nell'email.

Per l'invio, imposta `ROON_SMTP_PASSWORD` nell'ambiente (preferibilmente password applicativa del provider), quindi:

```sh
python3 weekly.py --send
```

Il default è sempre anteprima. Non inserire i segreti nel CSV o in `config.toml`. Il processo pianificato deve ricevere le stesse variabili d'ambiente: normalmente non eredita quelle del tuo terminale. Usa il gestore segreti del NAS o un file privato leggibile solo dall'utente del servizio. SMTP accetta solo SSL o STARTTLS con verifica del certificato.

## Pianificazione ogni venerdì

Nel pianificatore del NAS crea un'attività settimanale: venerdì alle 09:00, eseguita dall'utente proprietario della cartella. Il comando è il percorso assoluto di Python 3.11 seguito dal percorso assoluto di `weekly.py`, `--config` con il percorso assoluto di `config.toml` e `--send`. Le variabili segrete devono essere disponibili al servizio.

In alternativa, esempio cron Linux (sostituisci i percorsi):

```cron
0 9 * * 5 /usr/bin/python3 /volume1/scripts/roon-releases/weekly.py --config /volume1/scripts/roon-releases/config.toml --send >> /volume1/scripts/roon-releases/weekly.log 2>&1
```

Cron usa il fuso del sistema: impostalo coerentemente con `timezone` nel file. Non è stato installato alcun job su questo computer o NAS; il programma è pronto per il pianificatore. L'opzione `--date YYYY-MM-DD` permette di riprodurre una finestra temporale. L'email viene inviata anche senza risultati e riporta gli eventuali problemi di copertura. Un file di lock impedisce esecuzioni concorrenti sulla stessa cartella di stato.

## Fonti e selezione

MusicBrainz: https://musicbrainz.org/doc/MusicBrainz_API e https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting. API JSON pubblica, identificazione obbligatoria mediante User-Agent, massimo una richiesta al secondo (qui almeno 1,1 secondi). Si risolve il nome nell'identificativo artista, si cercano le **release** nella finestra di date e si leggono i dettagli e la **release-group**. La prima pubblicazione dell'opera e la data dell'edizione sono distinte. Cache SQLite di 24 ore, affinità Last.fm 30 giorni; timeout e retry per errori temporanei.

Last.fm: https://www.last.fm/api/show/artist.getSimilar. Di default i 40 artisti con più album nel NAS sono i riferimenti: almeno due di essi devono suggerire il candidato con match >= 0,65. Si selezionano al massimo 25 affini. Questo criterio riduce suggerimenti generici e mostra nell'email perché sono stati scelti; è un'euristica, non un'analisi degli ascolti. Le collaborazioni rimangono intere: separare indiscriminatamente '&' corromperebbe nomi come Earth, Wind & Fire. Se una collaborazione non si risolve, aggiungi una mappatura esplicita oppure il suo MusicBrainz ID verificato.

Artisti omonimi/ambigui vengono esclusi e indicati negli avvisi. Aggiungi il loro identificativo verificato nella sezione `artist_ids`. Alcune varianti evidenti sono già normalizzate tramite `aliases`; puoi estenderla. `exclude_artists`, `types`, `exclude_secondary_types` e `formats` personalizzano il filtro. Le compilation sono escluse inizialmente, i live sono inclusi. Ristampe di titoli già posseduti restano ammesse.

## Deduplicazione e affidabilità

Una chiave comprende artista, release-group, data esatta, formati e disambiguazione dell'edizione. Edizioni territoriali equivalenti sono raggruppate; formati/date differenti restano distinti. Il titolo non è usato da solo come identificativo. Questa granularità può unire edizioni con packaging/label diversi nella stessa data: consulta il link per i dettagli.

La finestra iniziale di 21 giorni sovrappone tre settimane per recuperare inserimenti tardivi; `sent` in SQLite esclude le segnalazioni già inviate. Lo stato viene aggiornato **solo dopo l'accettazione SMTP**. Il dry-run non marca elementi come inviati, ma aggiorna cache e anteprime. Conserva `state/history.sqlite` quando aggiorni lo script. Eliminare lo stato può far ripartire vecchie segnalazioni.

L'accettazione SMTP non garantisce la consegna nella posta in arrivo. Un arresto dopo l'accettazione e prima del salvataggio può produrre un duplicato alla successiva esecuzione; SMTP e SQLite non consentono una transazione unica. Gli errori di ricerca compaiono nell'email; un errore SMTP termina il processo senza marcare gli elementi. Il log può contenere nomi della collezione: custodiscilo insieme al CSV.

## Limiti della copertura

MusicBrainz è un catalogo collaborativo, non un feed esaustivo di annunci. Date incomplete (solo anno/mese) sono escluse con avviso per evitare falsi positivi. Non si deduce una data precisa dal giorno di inserimento nel catalogo. Inserimenti con oltre 21 giorni di ritardo richiedono una finestra più ampia. Si cercano uscite già pubblicate, non annunci futuri. Con centinaia di artisti la prima esecuzione può richiedere diversi minuti.

Un album originale di un anno precedente indica una nuova edizione di catalogo, ma non dimostra remaster, bonus track o miglioramento audio. Le edizioni dello stesso anno possono richiedere verifica manuale. Il formato audio nel CSV descrive il file posseduto, non una preferenza esclusiva per quel formato. Non sono implementati scraping di negozi o un'integrazione Discogs: Discogs può essere una futura fonte complementare per edizioni fisiche, con token e verifica delle date, ma non viene presentato come fonte attiva.

## Contenuto e verifiche

`weekly.py`: programma; `config.toml`: configurazione; `RoonBuddy.csv`: sorgente; `demo.json`: esempi; `tests/`: test offline; `analisi_collezione.json`: conteggi derivati dal CSV. Le anteprime reali e il report strutturato vengono scritti in `state/`.

I test coprono parsing del CSV originale, omonimie, classificazione, paginazione, deduplicazione, date parziali, HTML sicuro, affinità e mancato salvataggio dopo errore SMTP. Le API live e l'invio SMTP richiedono la prova sul tuo ambiente con credenziali configurate.
