![FlowStudy, studia con il tuo ritmo](docs/img/banner.jpg)

# FlowStudy

[![CI/CD](https://github.com/MattiaFarci28/FlowStudy/actions/workflows/ci.yml/badge.svg)](https://github.com/MattiaFarci28/FlowStudy/actions/workflows/ci.yml)

FlowStudy è un timer per lo studio. Scegli la materia e avvii il pomodoro;
la pausa può funzionare in due modi:

- **Pomodoro** (statica): tempi fissi, per esempio 25 minuti di studio e 5 di
  pausa, e il timer suona alla fine di ognuno;
- **Flowtime** (dinamica): studi finché sei concentrato e la pausa cresce con
  lo studio, un quinto del tempo studiato fino a un massimo di 30 minuti.

Ogni sessione viene salvata per materia. Il calendario mostra i giorni di
studio, le statistiche dicono quanto hai studiato per giorno, settimana e
materia, e con un obiettivo giornaliero si costruisce la **serie** di giorni
di fila. Più sei costante, più cresce il tuo **bonsai**: da seme a bonsai fiorito.

L'app ha tre schermate: **Home** (pomodoro e calendario), **Progressi**
(bonsai e statistiche) e **Impostazioni** (profilo, pause, materie e
download dei dati in CSV).

Progetto per il corso di **Ingegneria del Software Avanzata**, Università di
Ferrara.

## Requisiti

- Python **3.12** (l'ambiente di sviluppo, il container e la pipeline usano
  tutti la stessa versione; `requirements.txt` è stato generato con la 3.12.3)


## Installazione

```bash
git clone https://github.com/MattiaFarci28/FlowStudy.git
cd FlowStudy
python3 -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate
pip install -r requirements.txt       # solo l'esecuzione
pip install -r requirements-dev.txt   # anche test e strumenti di verifica
```

L'attivazione del virtual environment vale solo per la sessione di terminale
corrente e va ripetuta a ogni nuovo terminale.


## Avvio

```bash
uvicorn --factory src.api:crea_app
```

L'app si apre su http://localhost:8000; la documentazione interattiva
dell'API è su http://localhost:8000/docs. I dati vengono salvati nel file
`flowstudy.db`; per usarne un altro si imposta la variabile d'ambiente
`FLOWSTUDY_DB` (per esempio `sqlite:///altro.db`).


## Container

Con Docker Compose basta un comando (la configurazione è in `compose.yaml`):

```bash
docker compose up -d       # costruisce l'immagine e avvia il servizio
docker compose down        # lo ferma; i dati restano
```

Oppure, con i soli comandi di Docker:

```bash
docker build -t flowstudy .
docker run -d -p 8000:8000 -v flowstudy-dati:/dati --name flowstudy flowstudy
```

Il servizio risponde su http://localhost:8000. I dati stanno nel volume
`flowstudy-dati` e restano anche se il container viene eliminato e ricreato.
L'immagine contiene solo le dipendenze di esecuzione e il codice in `src/`,
e il servizio gira con un utente senza privilegi di amministratore.

Per provare il container in esecuzione:

```bash
FLOWSTUDY_URL=http://localhost:8000 pytest -m container
```


## Verifica

```bash
pytest                         # tutti i test
pytest -m "not integrazione"   # solo test di unità e property-based
pytest -m integrazione         # solo test di integrazione (database e API)
pytest --cov                   # test con misura della copertura (soglia 95%)
ruff check                     # analisi statica del codice
mypy                           # controllo dei tipi
```

La configurazione di pytest, della copertura, di ruff e di mypy è in
`pyproject.toml`.


## Integrazione e consegna continua

A ogni push e pull request GitHub Actions esegue la pipeline
[`.github/workflows/ci.yml`](.github/workflows/ci.yml):

1. **Analisi statica e test**: ruff, mypy, test di unità e property-based, test
   di integrazione e copertura (il rapporto si scarica dalla pagina dell'esecuzione);
2. **Container**: costruisce l'immagine, la avvia e la prova via rete;
3. **Pubblicazione**: solo su `main` e sui tag di versione, e solo se tutto è
   passato, l'immagine viene pubblicata su GitHub Container Registry;
4. **Release**: sui tag di versione viene creata anche la release su GitHub,
   con le note generate dai commit.

```bash
docker run -d -p 8000:8000 -v flowstudy-dati:/dati ghcr.io/mattiafarci28/flowstudy:latest
```

### Nuova versione

Il lavoro si fa su un branch e arriva su `main` con una pull request, dopo
che la pipeline è passata. Per pubblicare una versione si aggiorna il numero
in `pyproject.toml` e in `src/api.py` (un test controlla che coincidano), poi
si mette il tag su `main`:

```bash
git tag -a v1.0.0 -m "FlowStudy 1.0.0"
git push origin v1.0.0
```

La pipeline controlla che il tag corrisponda alla versione del progetto,
pubblica l'immagine `ghcr.io/mattiafarci28/flowstudy:1.0.0` e crea la release.


## Licenza

MIT, vedi [LICENSE](LICENSE).
