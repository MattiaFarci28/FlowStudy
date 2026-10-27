"""Persistenza di FlowStudy su SQLite (RNF1).

Qui stanno le tabelle e le funzioni che leggono e scrivono i dati. Le regole
restano in ``src.domain``: questo modulo converte fra righe del database e
oggetti del dominio, e controlla solo cio' che richiede di guardare i dati
salvati (nomi gia' usati, materia con il timer attivo).

Le funzioni non fanno ``commit``: chi le chiama (l'API) conferma tutte le
modifiche di una richiesta insieme, cosi' una richiesta o riesce tutta o non
lascia tracce.
"""

from datetime import UTC, date, datetime

from sqlalchemy import DateTime, Engine, ForeignKey, String, create_engine, select
from sqlalchemy import Enum as EnumSQL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from src.domain import (
    Impostazioni,
    Modalita,
    Sessione,
    Stato,
    Timer,
    chiave_nome,
    normalizza_nome,
    ripartisci_per_giorno,
)


class NonTrovata(LookupError):
    """La materia o la sessione richiesta non esiste."""


class NomeGiaUsato(ValueError):
    """Esiste gia' una materia con lo stesso nome (RF1, RF3)."""


class MateriaInUso(ValueError):
    """La materia ha il timer attivo e non si puo' eliminare (RF4)."""


class IstanteUTC(TypeDecorator):
    """Istante con fuso orario, salvato in UTC.

    SQLite non conserva il fuso orario: si salva l'ora UTC senza fuso e lo si
    rimette in lettura. Cosi' l'istante salvato e quello letto coincidono.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


# --- Tabelle ---------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class MateriaDB(Base):
    __tablename__ = "materie"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(50))
    chiave: Mapped[str] = mapped_column(unique=True)    # chiave_nome(nome)
    archiviata: Mapped[bool] = mapped_column(default=False)
    sessioni: Mapped[list["SessioneDB"]] = relationship(
        back_populates="materia", cascade="all, delete-orphan"
    )


class SessioneDB(Base):
    __tablename__ = "sessioni"

    id: Mapped[int] = mapped_column(primary_key=True)
    materia_id: Mapped[int] = mapped_column(ForeignKey("materie.id"))
    inizio: Mapped[datetime] = mapped_column(IstanteUTC)
    fine: Mapped[datetime] = mapped_column(IstanteUTC)
    materia: Mapped[MateriaDB] = relationship(back_populates="sessioni")

    def a_dominio(self) -> Sessione:
        return Sessione(self.materia_id, self.inizio, self.fine)


class ImpostazioniDB(Base):
    """Una sola riga, con id 1: l'app ha un solo utente."""

    __tablename__ = "impostazioni"

    id: Mapped[int] = mapped_column(primary_key=True)
    modalita: Mapped[Modalita] = mapped_column(EnumSQL(Modalita))
    studio_min: Mapped[int]
    pausa_min: Mapped[int]
    obiettivo_min: Mapped[int]
    nome: Mapped[str] = mapped_column(String(30))


class TimerDB(Base):
    """Il timer attivo: al massimo una riga, con id 1 (RF9).

    Conserva le impostazioni con cui il timer e' partito (RF7).
    """

    __tablename__ = "timer"

    id: Mapped[int] = mapped_column(primary_key=True)
    materia_id: Mapped[int] = mapped_column(ForeignKey("materie.id"))
    stato: Mapped[Stato] = mapped_column(EnumSQL(Stato))
    modalita: Mapped[Modalita] = mapped_column(EnumSQL(Modalita))
    studio_min: Mapped[int]
    pausa_min: Mapped[int]
    inizio_sessione: Mapped[datetime | None] = mapped_column(IstanteUTC)
    fine_pausa: Mapped[datetime | None] = mapped_column(IstanteUTC)


def crea_motore(url: str) -> Engine:
    """Collega il database indicato da ``url`` e crea le tabelle mancanti."""
    motore = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(motore)
    return motore


# --- Materie (RF1-RF4) -----------------------------------------------------

def _materia(db: Session, materia_id: int) -> MateriaDB:
    materia = db.get(MateriaDB, materia_id)
    if materia is None:
        raise NonTrovata(f"materia {materia_id} inesistente")
    return materia


def _con_chiave(db: Session, chiave: str) -> MateriaDB | None:
    return db.scalar(select(MateriaDB).where(MateriaDB.chiave == chiave))


def crea_materia(db: Session, nome: str) -> MateriaDB:
    """Crea una materia, o riattiva quella archiviata con lo stesso nome (RF1).

    Solleva: ValueError se il nome non e' valido, NomeGiaUsato se esiste gia'
             una materia attiva con lo stesso nome.
    """
    nome = normalizza_nome(nome)
    materia = _con_chiave(db, chiave_nome(nome))
    if materia is None:
        materia = MateriaDB(nome=nome, chiave=chiave_nome(nome))
        db.add(materia)
    elif materia.archiviata:
        materia.archiviata = False
        materia.nome = nome
    else:
        raise NomeGiaUsato(f"la materia '{materia.nome}' esiste gia'")
    db.flush()
    return materia


def elenca_materie(db: Session) -> list[MateriaDB]:
    """Materie non archiviate in ordine alfabetico (RF2)."""
    attive = db.scalars(select(MateriaDB).where(MateriaDB.archiviata.is_(False)))
    return sorted(attive, key=lambda m: m.chiave)


def rinomina_materia(db: Session, materia_id: int, nome: str) -> MateriaDB:
    """Cambia il nome di una materia (RF3).

    Solleva: NonTrovata, ValueError se il nome non e' valido, NomeGiaUsato se
             il nome e' di un'altra materia, archiviata o no.
    """
    materia = _materia(db, materia_id)
    nome = normalizza_nome(nome)
    altra = _con_chiave(db, chiave_nome(nome))
    if altra is not None and altra.id != materia.id:
        raise NomeGiaUsato(f"la materia '{altra.nome}' esiste gia'")
    materia.nome, materia.chiave = nome, chiave_nome(nome)
    db.flush()
    return materia


def elimina_materia(db: Session, materia_id: int, conserva_sessioni: bool) -> None:
    """Elimina una materia con le sue sessioni, o la archivia tenendole (RF4).

    Solleva: NonTrovata, MateriaInUso se il timer attivo e' su questa materia.
    """
    materia = _materia(db, materia_id)
    timer = db.get(TimerDB, 1)
    if timer is not None and timer.materia_id == materia_id:
        raise MateriaInUso("il timer e' in corso su questa materia")
    if conserva_sessioni:
        materia.archiviata = True
    else:
        db.delete(materia)
    db.flush()


def nomi_materie(db: Session) -> dict[int, str]:
    """Nome di ogni materia, archiviate comprese (per statistiche ed export)."""
    return {m.id: m.nome for m in db.scalars(select(MateriaDB))}


# --- Impostazioni (RF5-RF7) ------------------------------------------------

def leggi_impostazioni(db: Session) -> Impostazioni:
    """Impostazioni salvate, o quelle predefinite se non sono mai state salvate."""
    riga = db.get(ImpostazioniDB, 1)
    if riga is None:
        return Impostazioni()
    return Impostazioni(riga.modalita, riga.studio_min, riga.pausa_min, riga.obiettivo_min, riga.nome)


def salva_impostazioni(db: Session, imp: Impostazioni) -> None:
    db.merge(ImpostazioniDB(
        id=1, modalita=imp.modalita, studio_min=imp.studio_min, pausa_min=imp.pausa_min,
        obiettivo_min=imp.obiettivo_min, nome=imp.nome,
    ))
    db.flush()


# --- Timer (RF8, RF9) ------------------------------------------------------

def leggi_timer(db: Session) -> Timer | None:
    """Il timer attivo, o None se non ce n'e' uno."""
    riga = db.get(TimerDB, 1)
    if riga is None:
        return None
    imp = Impostazioni(riga.modalita, riga.studio_min, riga.pausa_min)
    return Timer(riga.materia_id, imp, riga.stato, riga.inizio_sessione, riga.fine_pausa)


def salva_timer(db: Session, timer: Timer | None) -> None:
    """Salva il timer attivo; un timer concluso (o None) viene tolto."""
    riga = db.get(TimerDB, 1)
    if timer is None or timer.stato is Stato.CONCLUSO:
        if riga is not None:
            db.delete(riga)
    else:
        db.merge(TimerDB(
            id=1, materia_id=timer.materia_id, stato=timer.stato,
            modalita=timer.impostazioni.modalita, studio_min=timer.impostazioni.studio_min,
            pausa_min=timer.impostazioni.pausa_min,
            inizio_sessione=timer.inizio_sessione, fine_pausa=timer.fine_pausa,
        ))
    db.flush()


# --- Sessioni (RF13-RF15) --------------------------------------------------

def aggiungi_sessione(db: Session, sessione: Sessione) -> SessioneDB:
    riga = SessioneDB(materia_id=sessione.materia_id, inizio=sessione.inizio, fine=sessione.fine)
    db.add(riga)
    db.flush()
    return riga


def elenca_sessioni(db: Session) -> list[SessioneDB]:
    """Tutte le sessioni, in ordine di inizio."""
    return list(db.scalars(select(SessioneDB).order_by(SessioneDB.inizio, SessioneDB.id)))


def elimina_sessione(db: Session, sessione_id: int) -> None:
    """Solleva: NonTrovata se la sessione non esiste (RF14)."""
    riga = db.get(SessioneDB, sessione_id)
    if riga is None:
        raise NonTrovata(f"sessione {sessione_id} inesistente")
    db.delete(riga)
    db.flush()


def elimina_giorno(db: Session, giorno: date) -> int:
    """Elimina le sessioni che hanno studio in ``giorno`` e dice quante sono (RF15)."""
    da_togliere = [r for r in elenca_sessioni(db) if giorno in ripartisci_per_giorno(r.a_dominio())]
    for riga in da_togliere:
        db.delete(riga)
    db.flush()
    return len(da_togliere)
