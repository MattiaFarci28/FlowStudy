# FlowStudy

Timer di studio che calcola la pausa in base a quanto hai studiato: niente
blocchi fissi da 25 minuti, studi finché sei concentrato e la pausa che ti
spetta cresce con il tempo di studio. Le sessioni sono organizzate per materia,
con statistiche per giorno, settimana e materia, un obiettivo giornaliero e la
serie di giorni consecutivi in cui l'hai raggiunto.

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

Il servizio risponde su http://localhost:8000; la documentazione interattiva
dell'API è su http://localhost:8000/docs. I dati vengono salvati nel file
`flowstudy.db`; per usarne un altro si imposta la variabile d'ambiente
`FLOWSTUDY_DB` (per esempio `sqlite:///altro.db`).


## Container

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
```

La configurazione di pytest, della copertura e di ruff è in `pyproject.toml`.


## Licenza

MIT, vedi [LICENSE](LICENSE).
