"""Test della persistenza: dominio e database SQLite lavorano insieme.

Ogni test usa un database nuovo, in un file temporaneo.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from src.database import (
    MateriaInUso,
    NomeGiaUsato,
    NonTrovata,
    aggiungi_sessione,
    crea_materia,
    crea_motore,
    elenca_materie,
    elenca_sessioni,
    elimina_giorno,
    elimina_materia,
    elimina_sessione,
    leggi_impostazioni,
    leggi_timer,
    nomi_materie,
    rinomina_materia,
    salva_impostazioni,
    salva_timer,
)
from src.domain import FUSO, Impostazioni, Modalita, Sessione, Stato, Timer, durata


def ora(*args):
    return datetime(*args, tzinfo=FUSO)


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path / 'flowstudy.db'}"


@pytest.fixture
def db(url):
    with Session(crea_motore(url)) as sessione:
        yield sessione


def nomi(materie):
    return [m.nome for m in materie]


# --- Materie ---------------------------------------------------------------

def test_le_materie_sono_in_ordine_alfabetico_senza_maiuscole(db):
    for nome in ["chimica", "Analisi 2", " biologia "]:
        crea_materia(db, nome)
    assert nomi(elenca_materie(db)) == ["Analisi 2", "biologia", "chimica"]


def test_non_si_creano_due_materie_con_lo_stesso_nome(db):
    crea_materia(db, "Analisi")
    with pytest.raises(NomeGiaUsato):
        crea_materia(db, " ANALISI ")


def test_un_nome_non_valido_e_rifiutato(db):
    with pytest.raises(ValueError):
        crea_materia(db, "   ")


def test_rinominare_una_materia(db):
    m = crea_materia(db, "analisi")
    rinomina_materia(db, m.id, "Analisi")          # solo maiuscole: e' lei stessa
    assert nomi(elenca_materie(db)) == ["Analisi"]


def test_non_si_rinomina_col_nome_di_un_altra_materia(db):
    crea_materia(db, "Fisica")
    archiviata = crea_materia(db, "Chimica")
    elimina_materia(db, archiviata.id, conserva_sessioni=True)
    m = crea_materia(db, "Analisi")
    for nome in ["fisica", "CHIMICA"]:
        with pytest.raises(NomeGiaUsato):
            rinomina_materia(db, m.id, nome)


def test_rinominare_una_materia_inesistente(db):
    with pytest.raises(NonTrovata):
        rinomina_materia(db, 99, "Analisi")


def test_eliminare_una_materia_con_le_sue_sessioni(db):
    m = crea_materia(db, "Analisi")
    aggiungi_sessione(db, Sessione(m.id, ora(2026, 10, 27, 15), ora(2026, 10, 27, 16)))
    elimina_materia(db, m.id, conserva_sessioni=False)
    assert elenca_materie(db) == [] and elenca_sessioni(db) == []


def test_archiviare_una_materia_conserva_le_sessioni(db):
    m = crea_materia(db, "Analisi")
    aggiungi_sessione(db, Sessione(m.id, ora(2026, 10, 27, 15), ora(2026, 10, 27, 16)))
    elimina_materia(db, m.id, conserva_sessioni=True)
    assert elenca_materie(db) == []
    assert len(elenca_sessioni(db)) == 1
    assert nomi_materie(db) == {m.id: "Analisi"}


def test_ricreare_una_materia_archiviata_la_riattiva(db):
    m = crea_materia(db, "Analisi")
    aggiungi_sessione(db, Sessione(m.id, ora(2026, 10, 27, 15), ora(2026, 10, 27, 16)))
    elimina_materia(db, m.id, conserva_sessioni=True)
    riattivata = crea_materia(db, "analisi")
    assert riattivata.id == m.id and len(riattivata.sessioni) == 1
    assert nomi(elenca_materie(db)) == ["analisi"]


def test_non_si_elimina_la_materia_del_timer_attivo(db):
    m = crea_materia(db, "Analisi")
    salva_timer(db, Timer(m.id, Impostazioni()))
    with pytest.raises(MateriaInUso):
        elimina_materia(db, m.id, conserva_sessioni=False)


def test_eliminare_una_materia_inesistente(db):
    with pytest.raises(NonTrovata):
        elimina_materia(db, 99, conserva_sessioni=False)


# --- Impostazioni ----------------------------------------------------------

def test_senza_impostazioni_salvate_valgono_le_predefinite(db):
    assert leggi_impostazioni(db) == Impostazioni()


def test_le_impostazioni_si_salvano_e_si_sovrascrivono(db):
    salva_impostazioni(db, Impostazioni(Modalita.DINAMICA, 50, 10, 90, "Mattia"))
    nuove = Impostazioni(Modalita.STATICA, 30, 6, 180, "")
    salva_impostazioni(db, nuove)
    assert leggi_impostazioni(db) == nuove


# --- Timer -----------------------------------------------------------------

@pytest.mark.parametrize("timer", [
    Timer(1, Impostazioni()),
    Timer(1, Impostazioni(Modalita.DINAMICA, 40, 8), Stato.STUDIO, inizio_sessione=ora(2026, 10, 27, 15)),
    Timer(1, Impostazioni(), Stato.PAUSA, fine_pausa=ora(2026, 10, 27, 15, 30)),
])
def test_il_timer_si_salva_e_si_rilegge_uguale(db, timer):
    crea_materia(db, "Analisi")
    salva_timer(db, timer)
    assert leggi_timer(db) == timer


@pytest.mark.parametrize("fine", [None, Timer(1, Impostazioni(), Stato.CONCLUSO)])
def test_un_timer_concluso_viene_tolto(db, fine):
    crea_materia(db, "Analisi")
    salva_timer(db, Timer(1, Impostazioni()))
    salva_timer(db, fine)
    assert leggi_timer(db) is None


def test_senza_timer_attivo(db):
    assert leggi_timer(db) is None
    salva_timer(db, None)
    assert leggi_timer(db) is None


# --- Sessioni --------------------------------------------------------------

def test_una_sessione_si_rilegge_con_lo_stesso_istante(db):
    # Notte del cambio d'ora: le 2:30 esistono due volte, qui e' la prima (ora legale).
    m = crea_materia(db, "Analisi")
    originale = Sessione(m.id, ora(2026, 10, 25, 2, 30), ora(2026, 10, 25, 3, 30))
    aggiungi_sessione(db, originale)
    db.expire_all()                                     # costringe a rileggere dal file
    riletta = elenca_sessioni(db)[0].a_dominio()
    # Si confronta in UTC: Python considera diversi due istanti di fusi
    # diversi quando uno dei due cade nell'ora che si ripete.
    assert riletta.inizio == originale.inizio.astimezone(UTC)
    assert riletta.fine == originale.fine.astimezone(UTC)
    assert durata(riletta) == durata(originale) == 2 * 3600


def test_le_sessioni_sono_in_ordine_di_inizio(db):
    m = crea_materia(db, "Analisi")
    tardi = aggiungi_sessione(db, Sessione(m.id, ora(2026, 10, 27, 18), ora(2026, 10, 27, 19)))
    presto = aggiungi_sessione(db, Sessione(m.id, ora(2026, 10, 27, 9), ora(2026, 10, 27, 10)))
    assert elenca_sessioni(db) == [presto, tardi]


def test_eliminare_una_sessione(db):
    m = crea_materia(db, "Analisi")
    s = aggiungi_sessione(db, Sessione(m.id, ora(2026, 10, 27, 9), ora(2026, 10, 27, 10)))
    elimina_sessione(db, s.id)
    assert elenca_sessioni(db) == []
    with pytest.raises(NonTrovata):
        elimina_sessione(db, s.id)


def test_eliminare_un_giorno_toglie_anche_le_sessioni_a_cavallo(db):
    m = crea_materia(db, "Analisi")
    for inizio, fine in [
        (ora(2026, 10, 26, 23), ora(2026, 10, 27, 0, 30)),   # a cavallo: va tolta
        (ora(2026, 10, 27, 15), ora(2026, 10, 27, 16)),      # del giorno: va tolta
        (ora(2026, 10, 28, 9), ora(2026, 10, 28, 10)),       # di un altro giorno: resta
    ]:
        aggiungi_sessione(db, Sessione(m.id, inizio, fine))
    assert elimina_giorno(db, date(2026, 10, 27)) == 2
    assert [s.inizio for s in elenca_sessioni(db)] == [ora(2026, 10, 28, 9)]


# --- Persistenza -----------------------------------------------------------

def test_i_dati_confermati_restano_dopo_aver_riaperto_il_database(url):
    with Session(crea_motore(url)) as db:
        m = crea_materia(db, "Analisi")
        aggiungi_sessione(db, Sessione(m.id, ora(2026, 10, 27, 9), ora(2026, 10, 27, 10)))
        salva_impostazioni(db, Impostazioni(obiettivo_min=60))
        db.commit()
    with Session(crea_motore(url)) as db:
        assert nomi(elenca_materie(db)) == ["Analisi"]
        assert len(elenca_sessioni(db)) == 1
        assert leggi_impostazioni(db).obiettivo_min == 60


def test_le_modifiche_non_confermate_vanno_perse(url):
    with Session(crea_motore(url)) as db:
        crea_materia(db, "Analisi")
        db.rollback()
    with Session(crea_motore(url)) as db:
        assert elenca_materie(db) == []
