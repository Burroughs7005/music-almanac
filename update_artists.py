"""Add explicit library mappings while preserving local settings and overrides."""
import json
from pathlib import Path
import shutil

COLLABORATIONS = {
    'Al Di Meola/John McLaughlin/Paco de Lucia': ['Al Di Meola', 'John McLaughlin', 'Paco de Lucía'],
    'Al Jarreau/NDR Bigband': ['Al Jarreau', 'NDR Bigband'],
    'Andy Partridge & Harold Budd': ['Andy Partridge', 'Harold Budd'],
    'Andy Summers & Robert Fripp': ['Andy Summers', 'Robert Fripp'],
    'Beatie Wolfe & Brian Eno': ['Beatie Wolfe', 'Brian Eno'],
    'Brian Eno & Beatie Wolfe': ['Brian Eno', 'Beatie Wolfe'],
    'Ben Watt with Robert Wyatt': ['Ben Watt', 'Robert Wyatt'],
    'Berliner Philharmoniker, Claudio Abbado': ['Berliner Philharmoniker', 'Claudio Abbado'],
    'Brian Eno / David Byrne': ['Brian Eno', 'David Byrne'],
    'Bruce Springsteen & the E Street Band': ['Bruce Springsteen', 'E Street Band'],
    'Bruce Springsteen with the Sessions Band': ['Bruce Springsteen'],
    'Dalla/Morandi': ['Lucio Dalla', 'Gianni Morandi'],
    'David Sylvian & Robert Fripp': ['David Sylvian', 'Robert Fripp'],
    'David Sylvian/Holger Czukay': ['David Sylvian', 'Holger Czukay'],
    'Elvis Costello / The Brodsky Quartet': ['Elvis Costello', 'Brodsky Quartet'],
    'Elvis Costello & Burt Bacharach': ['Elvis Costello', 'Burt Bacharach'],
    'Elvis Costello/Marian McPartland': ['Elvis Costello', 'Marian McPartland'],
    'Eno/Cale': ['Brian Eno', 'John Cale'],
    'Francesco DeGregori/Lucio Dalla': ['Francesco De Gregori', 'Lucio Dalla'],
    'Ivano Fossati/Oscar Prudente': ['Ivano Fossati', 'Oscar Prudente'],
    'Joe Jackson, Todd Rundgren & Ethel': ['Joe Jackson', 'Todd Rundgren', 'ETHEL'],
    'John Cale / Bob Neuwirth': ['John Cale', 'Bob Neuwirth'],
    'John Lennon / Yoko Ono': ['John Lennon', 'Yoko Ono'],
    'John Lennon / Yoko Ono / Plastic Ono Band': ['John Lennon', 'Yoko Ono', 'Plastic Ono Band'],
    'John Lennon/Plastic Ono Band': ['John Lennon', 'Plastic Ono Band'],
    'John Lennon/Yoko Ono': ['John Lennon', 'Yoko Ono'],
    'Joni Mitchell and the L.A. Express': ['Joni Mitchell'],
    'Lee Ritenour/Dave Grusin': ['Lee Ritenour', 'Dave Grusin'],
    'Lou Reed & John Cale': ['Lou Reed', 'John Cale'],
    'Lucio Dalla/Francesco De Gregori': ['Lucio Dalla', 'Francesco De Gregori'],
    'Maria Bethânia e Caetano Veloso': ['Maria Bethânia', 'Caetano Veloso'],
    'Marian McPartland/Steely Dan': ['Marian McPartland', 'Steely Dan'],
    'Milton Nascimento/Esperanza Spalding': ['Milton Nascimento', 'Esperanza Spalding'],
    'Mina/Ivano Fossati': ['Mina', 'Ivano Fossati'],
    'Nicola Alesini & Pier Luigi Andreoni': ['Nicola Alesini', 'Pier Luigi Andreoni'],
    'Pat Metheny &  Lyle Mays': ['Pat Metheny', 'Lyle Mays'],
    'Pat Metheny with Dave Holland and Roy Haynes': ['Pat Metheny', 'Dave Holland', 'Roy Haynes'],
    'Pete Christlieb/Warne Marsh': ['Pete Christlieb', 'Warne Marsh'],
    'Prince & the New Power Generation': ['Prince', 'The New Power Generation'],
    'Prince and the Revolution': ['Prince', 'The Revolution'],
    'Robbie Robertson & the Red Road Ensemble': ['Robbie Robertson'],
    'Sarah Vaughan with M. Nascimento': ['Sarah Vaughan', 'Milton Nascimento'],
    'Stephan Mathieu & David Sylvian': ['Stephan Mathieu', 'David Sylvian'],
    'Sylvian/Fripp': ['David Sylvian', 'Robert Fripp'],
    'The Manhattan Transfer with the WDR Funkhausorchester': ['The Manhattan Transfer', 'WDR Funkhausorchester'],
}
ALIASES = {'TR-i': 'Todd Rundgren'}


def update(cfg):
    for field, additions in [('collaborations', COLLABORATIONS), ('aliases', ALIASES)]:
        target = cfg.setdefault(field, {})
        for key, value in additions.items():
            target.setdefault(key, value)
    return cfg


if __name__ == '__main__':
    path = Path(__file__).resolve().parent / 'config.json'
    cfg = update(json.loads(path.read_text(encoding='utf-8')))
    backup = path.with_name('config.before-artists.json')
    if not backup.exists():
        shutil.copyfile(path, backup)
    temp = path.with_name('config.json.tmp')
    temp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)
    print('Mappature aggiornate; impostazioni esistenti conservate.')
