> Su glasgy  usa **config.json**, compatibile con Python 3.9. Il file TOML è un’alternativa per Python 3.11+, ma modificarlo non cambia la configurazione usata da run.sh. Nelle istruzioni sotto, per glasgy leggi config.json al posto di config.toml.

# Gmail su glasgy

Il server Gmail è già configurato: smtp.gmail.com, SSL, porta 465.
Fonte: https://developers.google.com/workspace/gmail/imap/imap-smtp

## Configurazione concordata per glasgy

Cartella: `/home/pi/music-almanac`. File delle variabili: `/home/pi/music-almanac/.env` (già configurato in `config.toml`). Il file esistente contiene una variabile non relativa alla posta: conservala e aggiungi in fondo:

```dotenv
ROON_GMAIL_ADDRESS='tuoindirizzo@gmail.com'
ROON_EMAIL_TO='tuoindirizzo@gmail.com'
ROON_SMTP_PASSWORD='PASSWORD_PER_APP_GOOGLE_SENZA_SPAZI'
# Facoltativo per gli artisti affini:
# LASTFM_API_KEY='LA_TUA_API_KEY'
```

Non sovrascrivere il `.env` con il file di esempio. `ROON_GMAIL_ADDRESS` alimenta contatto, utente SMTP e mittente; `ROON_EMAIL_TO` è il destinatario. Modifica i valori direttamente sul Raspberry e proteggi il file:

```sh
cd /home/pi/music-almanac
chmod 600 .env
python3 --version
sh run.sh --dry-run --limit-artists 3
```

Python deve essere 3.9 o superiore. Quando la prima prova funziona, esegui `sh run.sh --dry-run` per la ricerca completa, poi `sh run.sh --send` per inviare realmente il risultato. Per questa installazione, la riga da aggiungere a `crontab -e` dell'utente `pi` è:

```cron
0 9 * * 5 /bin/sh /home/pi/music-almanac/run.sh --send >> /home/pi/music-almanac/weekly.log 2>&1
```

Le sezioni seguenti spiegano Gmail e l'installazione generale: usa i percorsi concordati sopra al posto di `~/roon-releases`. I dati email provengono ora dalle variabili, quindi non occorre sostituire gli indirizzi segnaposto di `config.toml`.

## 1. Prepara Gmail

Attiva la verifica in due passaggi del tuo account Google e crea una password per le app chiamata `Roon Buddy glasgy` su https://myaccount.google.com/apppasswords.
Non usare la normale password di Gmail. Non inviare la password nella chat.
La funzione può non essere disponibile per alcuni account con Advanced Protection o restrizioni dell'organizzazione; in quel caso serve un'integrazione OAuth, non ancora implementata.
Guida Google: https://support.google.com/accounts/answer/185833?hl=it

## 2. Copia il progetto sul Raspberry

Estrai lo ZIP sul Mac. Dal terminale, nella cartella che contiene `roon-releases`, esegui il seguente comando sostituendo `UTENTE` con il nome del tuo utente SSH:

```sh
scp -r roon-releases UTENTE@glasgy:~/roon-releases
ssh UTENTE@glasgy
```

Se `glasgy` non si risolve, usa l'indirizzo IP o `glasgy.local` se disponibile nella rete.
Non copiare una cartella `state` di prova da un altro dispositivo: lo ZIP la esclude già.

Sul Raspberry:

```sh
python3 --version
cd ~/roon-releases
nano config.toml
```

Occorre Python **3.9 o superiore**. Se la versione è precedente, fermati prima di avviare lo script e aggiorna l'ambiente del Raspberry con una versione supportata.
Nel file sostituisci `your-address@example.com` con il tuo indirizzo Gmail nei campi `contact`, `username`, `sender` e `recipient`.
Puoi scegliere un destinatario diverso. Il fuso iniziale è `Europe/London`.

## 3. Salva le credenziali sul Raspberry

**Se hai già un `.env`, riutilizzalo senza copiarlo o modificarlo.** In `config.toml` imposta `environment_file` al suo percorso assoluto e `smtp.password_env` al nome della variabile password esistente. Nella sezione `smtp_env` associa `username`, `sender`, `recipient` ed eventualmente `host` e `port` ai nomi delle variabili esistenti. Puoi usare `contact_env` per prendere il contatto dalla variabile email. I campi senza mappatura mantengono i valori di `config.toml`. Comunica solo percorso e nomi per completare queste mappature.

Il lettore supporta assegnazioni `NOME=valore`, apici singoli/doppi, commenti ed `export`. Non esegue comandi né espande `$VAR` o `${VAR}`; i valori con spazi devono essere tra virgolette. Le variabili già impostate nell'ambiente prevalgono sul file. Il file deve essere leggibile dall'utente che esegue il job.

La procedura seguente serve solo se non hai un file esistente:

```sh
umask 077
cp secrets.env.example secrets.env
chmod 600 secrets.env
nano secrets.env
```

Sostituisci il valore di `ROON_SMTP_PASSWORD` con la password per le app Google, senza spazi, lasciando gli apici. Se vuoi artisti affini, aggiungi la chiave `LASTFM_API_KEY` ottenuta da https://www.last.fm/api/account/create.
Imposta `environment_file = "secrets.env"` in `config.toml`. Lo script legge il file sia nelle prove sia durante la pianificazione, senza eseguire codice shell.

## 4. Prova senza invio

```sh
python3 -m unittest discover -s tests -v
sh run.sh --fixture demo.json --dry-run --date 2026-10-02
sh run.sh --dry-run --limit-artists 3
sh run.sh --dry-run
```

La prima anteprima è fittizia; le ultime due interrogano MusicBrainz. Controlla il numero di avvisi mostrato e leggi `state/report.json` per le identità da correggere.
La ricerca completa può durare diversi minuti.

Per vedere la vera anteprima sul Mac, esegui in un secondo terminale del Mac, sostituendo `UTENTE`:

```sh
scp UTENTE@glasgy:~/roon-releases/state/preview.html ./anteprima-glasgy.html
```

Apri il file con un doppio clic. Quando la selezione ti soddisfa, sul Raspberry esegui:

```sh
sh run.sh --send
```

Questo comando invia realmente l'email all'indirizzo `recipient` configurato. Una risposta SMTP positiva conferma l'accettazione; verifica anche posta in arrivo e spam. Un errore di autenticazione va risolto controllando password per le app e indirizzo `username`.

## 5. Attiva il venerdì alle 09:00

Sul Raspberry verifica l'orario locale con `date`. Il pianificatore usa il fuso del dispositivo: deve essere coerente con `timezone` in `config.toml`.
Apri `crontab -e` e aggiungi una sola volta:

```cron
0 9 * * 5 /bin/sh "$HOME/roon-releases/run.sh" --send >> "$HOME/roon-releases/weekly.log" 2>&1
```

Qui HOME è la variabile standard del tuo utente, non va sostituita o ridefinita. Se hai scelto una cartella diversa, aggiorna i percorsi. Conferma l'attività con `crontab -l`.
Il Raspberry deve restare acceso e connesso a Internet all'orario previsto: cron non recupera un'esecuzione saltata. In quel caso puoi lanciare `sh run.sh --send` manualmente; la deduplicazione evita gli elementi già registrati.
Conserva `state/history.sqlite` tra gli aggiornamenti. Controlla `weekly.log` se l'email non arriva.

Questi sono file e istruzioni pronti per glasgy; l'installazione remota, l'accesso Gmail e il job non sono stati eseguiti da questo progetto.
