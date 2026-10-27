"""API REST di FlowStudy (RNF1).

Ogni richiesta segue lo stesso schema:
1. legge l'ora una volta sola (``orologio``): e' l'unico punto dell'app che
   guarda l'orologio (RNF3);
2. applica al timer le scadenze gia' passate (``aggiorna``), salvando
   l'eventuale sessione chiusa;
3. esegue l'operazione richiesta con le funzioni del dominio;
4. conferma tutte le modifiche insieme; se qualcosa va storto non resta nulla.

Avvio:  uvicorn --factory src.api:crea_app
Il database si sceglie con la variabile d'ambiente FLOWSTUDY_DB.
"""

import os
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src import database as dbm
from src.domain import (
    Impostazioni,
    Modalita,
    Timer,
    TransizioneNonValida,
    aggiorna,
    avvia,
    durata,
    esporta_csv,
    giorni_con_obiettivo,
    giorno_di,
    pausa,
    ripartisci_per_giorno,
    riprendi,
    secondi_rimanenti,
    serie,
    stadio_bonsai,
    studio_per_giorno,
    studio_per_materia,
    studio_per_settimana,
    termina,
)

DB_PREDEFINITO = "sqlite:///flowstudy.db"


# --- Dipendenze ------------------------------------------------------------

def orologio() -> datetime:
    """L'ora attuale, al secondo. Nei test viene sostituita da un'ora fissa."""
    return datetime.now(UTC).replace(microsecond=0)


def sessione_db(request: Request) -> Iterator[Session]:
    """Una sessione del database per richiesta, confermata solo se va tutto bene."""
    with Session(request.app.state.motore) as db:
        yield db
        db.commit()


Db = Annotated[Session, Depends(sessione_db)]
Adesso = Annotated[datetime, Depends(orologio)]


# --- Corpi delle richieste -------------------------------------------------

class MateriaIn(BaseModel):
    nome: str


class ImpostazioniIn(BaseModel):
    modalita: Modalita
    studio_min: int
    pausa_min: int
    obiettivo_min: int
    nome: str = ""


class TimerIn(BaseModel):
    materia_id: int


# --- Conversioni in JSON ---------------------------------------------------

def _materia(m: dbm.MateriaDB) -> dict:
    return {"id": m.id, "nome": m.nome}


def _timer(timer: Timer | None, adesso: datetime, suona: bool) -> dict:
    if timer is None:
        return {"attivo": False, "suona": suona}
    return {
        "attivo": True,
        "suona": suona,
        "materia_id": timer.materia_id,
        "stato": timer.stato.value,
        "modalita": timer.impostazioni.modalita.value,
        "secondi_rimanenti": secondi_rimanenti(timer, adesso),
        "inizio_sessione": timer.inizio_sessione,
        "fine_pausa": timer.fine_pausa,
    }


def _per_data(valori: dict[date, int]) -> dict[str, int]:
    return {g.isoformat(): s for g, s in sorted(valori.items())}


# --- Errori ----------------------------------------------------------------

def _errore(codice: int):
    def gestore(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=codice, content={"detail": str(exc)})
    return gestore


class Conflitto(Exception):
    """Operazione in contrasto con lo stato dei dati (HTTP 409)."""


# --- Applicazione ----------------------------------------------------------

def _timer_aggiornato(db: Session, adesso: datetime) -> tuple[Timer | None, bool]:
    """Applica e salva le scadenze del timer attivo (RF12)."""
    timer = dbm.leggi_timer(db)
    if timer is None:
        return None, False
    timer, sessione, suona = aggiorna(timer, adesso)
    if sessione is not None:
        dbm.aggiungi_sessione(db, sessione)
    dbm.salva_timer(db, timer)
    return timer, suona


EVENTI = {"avvia": avvia, "pausa": pausa, "riprendi": riprendi, "termina": termina}


def crea_app(url: str | None = None) -> FastAPI:
    app = FastAPI(title="FlowStudy", version="0.1.0")
    app.state.motore = dbm.crea_motore(url or os.environ.get("FLOWSTUDY_DB", DB_PREDEFINITO))

    app.add_exception_handler(dbm.NonTrovata, _errore(404))
    for conflitto in (dbm.NomeGiaUsato, dbm.MateriaInUso, TransizioneNonValida, Conflitto):
        app.add_exception_handler(conflitto, _errore(409))
    app.add_exception_handler(ValueError, _errore(422))

    # --- Materie (RF1-RF4) ---

    @app.get("/materie")
    def elenca_materie(db: Db):
        return [_materia(m) for m in dbm.elenca_materie(db)]

    @app.post("/materie", status_code=201)
    def crea_materia(corpo: MateriaIn, db: Db):
        return _materia(dbm.crea_materia(db, corpo.nome))

    @app.patch("/materie/{materia_id}")
    def rinomina_materia(materia_id: int, corpo: MateriaIn, db: Db):
        return _materia(dbm.rinomina_materia(db, materia_id, corpo.nome))

    @app.delete("/materie/{materia_id}", status_code=204)
    def elimina_materia(materia_id: int, db: Db, adesso: Adesso, conserva_sessioni: bool = False):
        _timer_aggiornato(db, adesso)
        dbm.elimina_materia(db, materia_id, conserva_sessioni)

    # --- Impostazioni (RF5-RF7) ---

    @app.get("/impostazioni")
    def leggi_impostazioni(db: Db):
        return asdict(dbm.leggi_impostazioni(db))

    @app.put("/impostazioni")
    def salva_impostazioni(corpo: ImpostazioniIn, db: Db):
        impostazioni = Impostazioni(**corpo.model_dump())
        dbm.salva_impostazioni(db, impostazioni)
        return asdict(impostazioni)

    # --- Timer (RF8-RF12) ---

    @app.get("/timer")
    def stato_timer(db: Db, adesso: Adesso):
        timer, suona = _timer_aggiornato(db, adesso)
        return _timer(timer, adesso, suona)

    @app.post("/timer", status_code=201)
    def crea_timer(corpo: TimerIn, db: Db, adesso: Adesso):
        if _timer_aggiornato(db, adesso)[0] is not None:
            raise Conflitto("c'e' gia' un timer attivo")
        materia = db.get(dbm.MateriaDB, corpo.materia_id)
        if materia is None or materia.archiviata:
            raise dbm.NonTrovata(f"materia {corpo.materia_id} inesistente")
        timer = Timer(materia.id, dbm.leggi_impostazioni(db))
        dbm.salva_timer(db, timer)
        return _timer(timer, adesso, False)

    @app.post("/timer/{evento}")
    def evento_timer(evento: Literal["avvia", "pausa", "riprendi", "termina"], db: Db, adesso: Adesso):
        timer, suona = _timer_aggiornato(db, adesso)
        if timer is None:
            raise dbm.NonTrovata("nessun timer attivo")
        esito = EVENTI[evento](timer, adesso)
        timer, sessione = esito if isinstance(esito, tuple) else (esito, None)
        if sessione is not None:
            dbm.aggiungi_sessione(db, sessione)
        dbm.salva_timer(db, timer)
        return _timer(timer, adesso, suona)

    # --- Sessioni (RF13-RF15) ---

    @app.get("/sessioni")
    def elenca_sessioni(db: Db, adesso: Adesso, giorno: date | None = None):
        _timer_aggiornato(db, adesso)
        nomi = dbm.nomi_materie(db)
        righe = dbm.elenca_sessioni(db)
        if giorno is not None:
            righe = [r for r in righe if giorno in ripartisci_per_giorno(r.a_dominio())]
        return [
            {
                "id": r.id, "materia_id": r.materia_id, "materia": nomi[r.materia_id],
                "inizio": r.inizio, "fine": r.fine, "durata_s": durata(r.a_dominio()),
            }
            for r in righe
        ]

    @app.delete("/sessioni/{sessione_id}", status_code=204)
    def elimina_sessione(sessione_id: int, db: Db):
        dbm.elimina_sessione(db, sessione_id)

    @app.delete("/giorni/{giorno}")
    def elimina_giorno(giorno: date, db: Db, adesso: Adesso):
        _timer_aggiornato(db, adesso)
        return {"eliminate": dbm.elimina_giorno(db, giorno)}

    # --- Statistiche, serie e bonsai (RF16-RF20) ---

    @app.get("/statistiche")
    def statistiche(db: Db, adesso: Adesso):
        _timer_aggiornato(db, adesso)
        sessioni = [r.a_dominio() for r in dbm.elenca_sessioni(db)]
        per_giorno = studio_per_giorno(sessioni)
        obiettivo = dbm.leggi_impostazioni(db).obiettivo_min
        ok = giorni_con_obiettivo(per_giorno, obiettivo)
        oggi = giorno_di(adesso)
        return {
            "oggi": oggi,
            "obiettivo_min": obiettivo,
            "studio_oggi_s": per_giorno.get(oggi, 0),
            "serie": serie(ok, oggi),
            "bonsai": stadio_bonsai(ok, oggi).value,
            "per_giorno": _per_data(per_giorno),
            "per_settimana": _per_data(studio_per_settimana(sessioni)),
        }

    @app.get("/statistiche/materie")
    def statistiche_materie(dal: date, al: date, db: Db, adesso: Adesso):
        _timer_aggiornato(db, adesso)
        nomi = dbm.nomi_materie(db)
        sessioni = [r.a_dominio() for r in dbm.elenca_sessioni(db)]
        totali = studio_per_materia(sessioni, dal, al)
        return [
            {"materia_id": m, "materia": nomi[m], "secondi": s}
            for m, s in sorted(totali.items(), key=lambda voce: -voce[1])
        ]

    # --- Esportazione (RF21) ---

    @app.get("/export.csv")
    def esporta(db: Db, adesso: Adesso):
        _timer_aggiornato(db, adesso)
        sessioni = [r.a_dominio() for r in dbm.elenca_sessioni(db)]
        return Response(
            esporta_csv(sessioni, dbm.nomi_materie(db)),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="flowstudy.csv"'},
        )

    return app
