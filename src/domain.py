"""Logica di dominio di FlowStudy.

Il modulo e' puro: non legge l'orologio, non accede al database e non ha
effetti collaterali. L'ora corrente arriva sempre come parametro (``adesso``),
cosi' ogni funzione si puo' provare in qualsiasi istante, mezzanotte e cambio
dell'ora legale compresi (RNF3).

Convenzioni valide per tutto il modulo:
- gli istanti sono ``datetime`` con fuso orario e senza microsecondi;
- le durate sono numeri interi di secondi;
- i giorni sono calcolati nell'ora italiana (``FUSO``);
- un intervallo ``[inizio, fine)`` comprende ``inizio`` ed esclude ``fine``.

I riferimenti RFn rimandano a docs/01-requisiti.md.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("Europe/Rome")

NOME_MAX = 50                # caratteri del nome di una materia (RF1)
RAPPORTO_PAUSA = 5           # modalita' dinamica: 1 secondo di pausa ogni 5 di studio (RF10)
PAUSA_MASSIMA_S = 30 * 60    # tetto della pausa dinamica (RF10)
GIORNI_BONSAI = 30           # finestra della costanza per il bonsai (RF20)


class TransizioneNonValida(Exception):
    """Evento non ammesso nello stato corrente del timer (RF8)."""


# --- Materie ---------------------------------------------------------------

def normalizza_nome(nome: str) -> str:
    """Restituisce il nome di una materia pronto per essere salvato (RF1).

    Pre:  nessuna.
    Post: restituisce ``nome`` senza spazi iniziali e finali.
    Solleva: ValueError se il risultato ha meno di 1 o piu' di NOME_MAX
             caratteri.
    """
    raise NotImplementedError


def chiave_nome(nome: str) -> str:
    """Chiave con cui confrontare i nomi delle materie (RF1, RF3).

    Due nomi indicano la stessa materia se e solo se hanno la stessa chiave.

    Pre:  ``nome`` e' accettato da ``normalizza_nome``.
    Post: restituisce ``normalizza_nome(nome)`` senza distinzione fra maiuscole
          e minuscole; ``chiave_nome("Analisi") == chiave_nome(" analisi ")``.
    """
    raise NotImplementedError


# --- Impostazioni ----------------------------------------------------------

class Modalita(Enum):
    STATICA = "statica"      # Pomodoro: studio e pausa fissi
    DINAMICA = "dinamica"    # Flowtime: pausa proporzionale allo studio


@dataclass(frozen=True)
class Impostazioni:
    """Profilo e preferenze dell'utente (RF5, RF6).

    Invariante: 1 <= studio_min <= 120, 1 <= pausa_min <= 60,
                1 <= obiettivo_min <= 1440, ``nome`` ha al massimo 30
                caratteri (puo' essere vuoto).
    Solleva: ValueError alla creazione se l'invariante non vale.
    ``studio_min`` e ``pausa_min`` si usano solo in modalita' statica.
    """

    modalita: Modalita = Modalita.STATICA
    studio_min: int = 25
    pausa_min: int = 5
    obiettivo_min: int = 120
    nome: str = ""


def pausa_spettante(durata_studio_s: int, impostazioni: Impostazioni) -> int:
    """Durata in secondi della pausa concessa dopo una sessione (RF10).

    Pre:  durata_studio_s >= 0.
    Post: in modalita' statica restituisce ``impostazioni.pausa_min * 60``;
          in modalita' dinamica restituisce
          ``min(durata_studio_s // RAPPORTO_PAUSA, PAUSA_MASSIMA_S)``.
          In entrambi i casi 0 <= risultato <= PAUSA_MASSIMA_S.
    """
    raise NotImplementedError


# --- Timer -----------------------------------------------------------------

class Stato(Enum):
    PRONTO = "pronto"
    STUDIO = "studio"
    PAUSA = "pausa"
    CONCLUSO = "concluso"


@dataclass(frozen=True)
class Sessione:
    """Tratto continuo di studio su una materia (RF13).

    Invariante: ``inizio < fine``.
    """

    materia_id: int
    inizio: datetime
    fine: datetime


def durata(sessione: Sessione) -> int:
    """Durata della sessione in secondi.

    Pre:  nessuna.
    Post: restituisce ``(fine - inizio)`` in secondi, sempre > 0.
    """
    raise NotImplementedError


@dataclass(frozen=True)
class Timer:
    """Timer di studio su una materia (RF8, statechart in docs/02-statechart.md).

    Invariante:
    - ``inizio_sessione`` e' valorizzato se e solo se ``stato`` e' STUDIO;
    - ``fine_pausa`` e' valorizzato se e solo se ``stato`` e' PAUSA.
    Le impostazioni sono quelle in vigore all'avvio e non cambiano (RF7).
    """

    materia_id: int
    impostazioni: Impostazioni
    stato: Stato = Stato.PRONTO
    inizio_sessione: datetime | None = None
    fine_pausa: datetime | None = None


# Precondizioni comuni agli eventi del timer (avvia, pausa, riprendi, termina):
# - ``adesso`` non precede gli istanti registrati nel timer;
# - non ci sono scadenze pendenti, cioe' ``aggiorna(timer, adesso)`` lascerebbe
#   il timer invariato. Chi chiama applica prima ``aggiorna``.


def avvia(timer: Timer, adesso: datetime) -> Timer:
    """Evento "avvia": PRONTO -> STUDIO, apre una sessione (RF8).

    Pre:  precondizioni comuni.
    Post: restituisce il timer in STUDIO con ``inizio_sessione == adesso``.
    Solleva: TransizioneNonValida se ``timer.stato`` non e' PRONTO.
    """
    raise NotImplementedError


def pausa(timer: Timer, adesso: datetime) -> tuple[Timer, Sessione | None]:
    """Evento "pausa": STUDIO -> PAUSA, chiude la sessione (RF8, RF10).

    Pre:  precondizioni comuni.
    Post: restituisce il timer in PAUSA e la sessione
          ``[timer.inizio_sessione, adesso)``, oppure None se ha durata nulla
          (RF13). ``fine_pausa == adesso + pausa_spettante(durata studiata)``.
    Solleva: TransizioneNonValida se ``timer.stato`` non e' STUDIO.
    """
    raise NotImplementedError


def riprendi(timer: Timer, adesso: datetime) -> Timer:
    """Evento "riprendi": PAUSA -> STUDIO, apre una sessione (RF8, RF11).

    Pre:  precondizioni comuni.
    Post: restituisce il timer in STUDIO con ``inizio_sessione == adesso``;
          la pausa residua viene persa.
    Solleva: TransizioneNonValida se ``timer.stato`` non e' PAUSA.
    """
    raise NotImplementedError


def termina(timer: Timer, adesso: datetime) -> tuple[Timer, Sessione | None]:
    """Evento "termina": PRONTO, STUDIO o PAUSA -> CONCLUSO (RF8).

    Pre:  precondizioni comuni.
    Post: restituisce il timer in CONCLUSO e, se il timer era in STUDIO, la
          sessione ``[timer.inizio_sessione, adesso)`` (None se di durata
          nulla); negli altri casi None.
    Solleva: TransizioneNonValida se ``timer.stato`` e' CONCLUSO.
    """
    raise NotImplementedError


def aggiorna(timer: Timer, adesso: datetime) -> tuple[Timer, Sessione | None, bool]:
    """Applica le scadenze avvenute fino ad ``adesso`` (RF8, RF12).

    Le scadenze sono le transizioni a tempo dello statechart:
    - STUDIO in modalita' statica scade a ``inizio_sessione + studio_min``:
      la sessione si chiude in quell'istante e il timer va in PAUSA;
    - PAUSA scade a ``fine_pausa``: il timer va in PRONTO.
    Se sono scadute entrambe, le applica in ordine.

    Pre:  ``adesso`` non precede gli istanti registrati nel timer.
    Post: restituisce (timer aggiornato, sessione chiusa o None, suona), dove
          ``suona`` e' True se e solo se e' scattata almeno una scadenza.
          La sessione chiusa termina all'istante della scadenza, non ad
          ``adesso``: il tempo passato lontano dal timer non conta come studio.
          ``aggiorna`` e' idempotente: applicarla due volte con lo stesso
          ``adesso`` equivale ad applicarla una volta.
    """
    raise NotImplementedError


def secondi_rimanenti(timer: Timer, adesso: datetime) -> int | None:
    """Secondi alla prossima scadenza, per il quadrante del pomodoro (RF12).

    Pre:  non ci sono scadenze pendenti (vedi precondizioni comuni).
    Post: in STUDIO statico e in PAUSA restituisce i secondi alla scadenza,
          sempre > 0; negli altri casi (STUDIO dinamico, PRONTO, CONCLUSO)
          restituisce None, perche' non c'e' una scadenza.
    """
    raise NotImplementedError


# --- Giorni e statistiche --------------------------------------------------

def giorno_di(istante: datetime) -> date:
    """Giorno di calendario, nell'ora italiana, a cui appartiene ``istante``.

    Pre:  ``istante`` ha il fuso orario.
    Post: restituisce la data di ``istante`` convertito in FUSO.
    """
    raise NotImplementedError


def ripartisci_per_giorno(sessione: Sessione) -> dict[date, int]:
    """Divide la durata della sessione fra i giorni in cui e' avvenuta (RF16).

    Pre:  nessuna.
    Post: le chiavi sono i giorni da ``giorno_di(inizio)`` a quello che contiene
          l'ultimo secondo della sessione, e ogni valore e' > 0;
          ``sum(risultato.values()) == durata(sessione)``.
          Esempio: 23:00 -> 00:30 da' {primo giorno: 3600, secondo: 1800}.
    """
    raise NotImplementedError


def studio_per_giorno(sessioni: Iterable[Sessione]) -> dict[date, int]:
    """Secondi di studio attribuiti a ciascun giorno (RF16, RF17).

    Pre:  nessuna.
    Post: per ogni giorno ``g`` il valore e' la somma di
          ``ripartisci_per_giorno(s).get(g, 0)`` sulle sessioni; compaiono solo
          i giorni con valore > 0. Con nessuna sessione restituisce {}.
    """
    raise NotImplementedError


def studio_per_settimana(sessioni: Iterable[Sessione]) -> dict[date, int]:
    """Secondi di studio per settimana, da lunedi' a domenica (RF17).

    Pre:  nessuna.
    Post: ogni chiave e' un lunedi'; il valore e' la somma di
          ``studio_per_giorno`` sui sette giorni che iniziano da quel lunedi'.
          La somma dei valori e' uguale a quella di ``studio_per_giorno``.
    """
    raise NotImplementedError


def studio_per_materia(sessioni: Iterable[Sessione], dal: date, al: date) -> dict[int, int]:
    """Secondi di studio per materia nei giorni da ``dal`` ad ``al`` compresi (RF17).

    Pre:  dal <= al.
    Post: per ogni materia il valore e' la somma delle quote di
          ``ripartisci_per_giorno`` che cadono in ``[dal, al]``; compaiono solo
          le materie con valore > 0.
    Solleva: ValueError se dal > al.
    """
    raise NotImplementedError


def sessioni_del_giorno(sessioni: Iterable[Sessione], giorno: date) -> list[Sessione]:
    """Sessioni da eliminare con la giornata ``giorno`` (RF15).

    Pre:  nessuna.
    Post: restituisce le sessioni ``s`` con ``giorno`` in
          ``ripartisci_per_giorno(s)``. Tolte queste, lo studio di ``giorno``
          e' zero.
    """
    raise NotImplementedError


# --- Obiettivo, serie e bonsai ---------------------------------------------

def giorni_con_obiettivo(per_giorno: Mapping[date, int], obiettivo_min: int) -> set[date]:
    """Giorni in cui l'obiettivo e' raggiunto (RF18).

    Pre:  obiettivo_min >= 1.
    Post: restituisce i giorni ``g`` con ``per_giorno[g] >= obiettivo_min * 60``.
    """
    raise NotImplementedError


def serie(giorni_ok: set[date], oggi: date) -> int:
    """Giorni consecutivi con obiettivo raggiunto (RF19).

    Pre:  nessuna.
    Post: detto ``n`` il numero di giorni consecutivi in ``giorni_ok`` che
          terminano ieri, restituisce ``n + 1`` se ``oggi`` e' in ``giorni_ok``,
          altrimenti ``n``. I giorni successivi a ``oggi`` sono ignorati.
    """
    raise NotImplementedError


class Stadio(Enum):
    SEME = "seme"
    GERMOGLIO = "germoglio"
    PIANTINA = "piantina"
    ALBERELLO = "alberello"
    BONSAI_FIORITO = "bonsai fiorito"


def stadio_bonsai(giorni_ok: set[date], oggi: date) -> Stadio:
    """Stadio del bonsai in base alla costanza recente (RF20).

    Pre:  nessuna.
    Post: detto ``k`` il numero di giorni di ``giorni_ok`` compresi negli
          ultimi GIORNI_BONSAI giorni, oggi incluso, restituisce SEME se k = 0,
          GERMOGLIO se 1 <= k <= 3, PIANTINA se 4 <= k <= 9, ALBERELLO se
          10 <= k <= 19, BONSAI_FIORITO se k >= 20.
          Monotonia: aggiungere giorni a ``giorni_ok`` non abbassa lo stadio.
    """
    raise NotImplementedError


# --- Esportazione ----------------------------------------------------------

def esporta_csv(sessioni: Iterable[Sessione], nomi: Mapping[int, str]) -> str:
    """Testo CSV con tutte le sessioni (RF21).

    Pre:  ogni ``materia_id`` delle sessioni e' una chiave di ``nomi``.
    Post: la prima riga e' ``materia,inizio,fine,durata_s``; segue una riga per
          sessione, in ordine di inizio, con gli istanti in formato ISO 8601
          nell'ora italiana. Un nome che contiene virgole o virgolette e'
          racchiuso fra virgolette secondo le regole del formato CSV.
    """
    raise NotImplementedError
