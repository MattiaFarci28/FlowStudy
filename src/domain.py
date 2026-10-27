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

import csv
import io
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("Europe/Rome")

NOME_MAX = 50                # caratteri del nome di una materia (RF1)
NOME_PROFILO_MAX = 30        # caratteri del nome nel profilo (RF6)
RAPPORTO_PAUSA = 5           # modalita' dinamica: 1 secondo di pausa ogni 5 di studio (RF10)
PAUSA_MASSIMA_S = 30 * 60    # tetto della pausa dinamica (RF10)
GIORNI_BONSAI = 30           # finestra della costanza per il bonsai (RF20)


class TransizioneNonValida(Exception):
    """Evento non ammesso nello stato corrente del timer (RF8)."""


def _utc(istante: datetime) -> datetime:
    """Converte in UTC prima di confrontare, sottrarre o sommare istanti.

    Python esegue queste operazioni sull'ora "da orologio" quando due istanti
    hanno lo stesso fuso: la notte del cambio dell'ora sbaglierebbe di un'ora.
    In UTC l'ora non salta mai.
    """
    return istante.astimezone(UTC)


def _secondi(da: datetime, a: datetime) -> int:
    """Secondi reali trascorsi da ``da`` ad ``a``."""
    return int((_utc(a) - _utc(da)).total_seconds())


# --- Materie ---------------------------------------------------------------

def normalizza_nome(nome: str) -> str:
    """Restituisce il nome di una materia pronto per essere salvato (RF1).

    Pre:  nessuna.
    Post: restituisce ``nome`` senza spazi iniziali e finali.
    Solleva: ValueError se il risultato ha meno di 1 o piu' di NOME_MAX
             caratteri.
    """
    pulito = nome.strip()
    if not 1 <= len(pulito) <= NOME_MAX:
        raise ValueError(f"il nome deve avere da 1 a {NOME_MAX} caratteri")
    return pulito


def chiave_nome(nome: str) -> str:
    """Chiave con cui confrontare i nomi delle materie (RF1, RF3).

    Due nomi indicano la stessa materia se e solo se hanno la stessa chiave.

    Pre:  ``nome`` e' accettato da ``normalizza_nome``.
    Post: restituisce ``normalizza_nome(nome)`` senza distinzione fra maiuscole
          e minuscole; ``chiave_nome("Analisi") == chiave_nome(" analisi ")``.
    """
    return normalizza_nome(nome).casefold()


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

    def __post_init__(self) -> None:
        if not 1 <= self.studio_min <= 120:
            raise ValueError("il tempo di studio deve essere fra 1 e 120 minuti")
        if not 1 <= self.pausa_min <= 60:
            raise ValueError("il tempo di pausa deve essere fra 1 e 60 minuti")
        if not 1 <= self.obiettivo_min <= 1440:
            raise ValueError("l'obiettivo deve essere fra 1 e 1440 minuti")
        if len(self.nome) > NOME_PROFILO_MAX:
            raise ValueError(f"il nome deve avere al massimo {NOME_PROFILO_MAX} caratteri")


def pausa_spettante(durata_studio_s: int, impostazioni: Impostazioni) -> int:
    """Durata in secondi della pausa concessa dopo una sessione (RF10).

    Pre:  durata_studio_s >= 0.
    Post: in modalita' statica restituisce ``impostazioni.pausa_min * 60``;
          in modalita' dinamica restituisce
          ``min(durata_studio_s // RAPPORTO_PAUSA, PAUSA_MASSIMA_S)``,
          quindi 0 <= risultato <= PAUSA_MASSIMA_S.
    """
    if impostazioni.modalita is Modalita.STATICA:
        return impostazioni.pausa_min * 60
    return min(durata_studio_s // RAPPORTO_PAUSA, PAUSA_MASSIMA_S)


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
    Solleva: ValueError alla creazione se l'invariante non vale.
    """

    materia_id: int
    inizio: datetime
    fine: datetime

    def __post_init__(self) -> None:
        if _utc(self.inizio) >= _utc(self.fine):
            raise ValueError("una sessione deve finire dopo il suo inizio")


def durata(sessione: Sessione) -> int:
    """Durata della sessione in secondi.

    Pre:  nessuna.
    Post: restituisce ``(fine - inizio)`` in secondi, sempre > 0.
    """
    return _secondi(sessione.inizio, sessione.fine)


@dataclass(frozen=True)
class Timer:
    """Timer di studio su una materia (RF8, statechart in docs/02-statechart.md).

    Invariante:
    - ``inizio_sessione`` e' valorizzato se e solo se ``stato`` e' STUDIO;
    - ``fine_pausa`` e' valorizzato se e solo se ``stato`` e' PAUSA.
    Le impostazioni sono quelle in vigore all'avvio e non cambiano (RF7).
    Solleva: ValueError alla creazione se l'invariante non vale.
    """

    materia_id: int
    impostazioni: Impostazioni
    stato: Stato = Stato.PRONTO
    inizio_sessione: datetime | None = None
    fine_pausa: datetime | None = None

    def __post_init__(self) -> None:
        if (self.stato is Stato.STUDIO) != (self.inizio_sessione is not None):
            raise ValueError("inizio_sessione va indicato solo in STUDIO")
        if (self.stato is Stato.PAUSA) != (self.fine_pausa is not None):
            raise ValueError("fine_pausa va indicata solo in PAUSA")


def _richiedi(timer: Timer, evento: str, *ammessi: Stato) -> None:
    if timer.stato not in ammessi:
        raise TransizioneNonValida(f"'{evento}' non e' ammesso nello stato {timer.stato.value}")


def _chiudi_sessione(timer: Timer, fine: datetime) -> Sessione | None:
    """Uscita da STUDIO: la sessione aperta, o None se ha durata nulla (RF13)."""
    if _secondi(timer.inizio_sessione, fine) <= 0:
        return None
    return Sessione(timer.materia_id, timer.inizio_sessione, fine)


def _scadenza_studio(timer: Timer) -> datetime | None:
    """Istante in cui scade lo studio: esiste solo in STUDIO statico."""
    if timer.stato is Stato.STUDIO and timer.impostazioni.modalita is Modalita.STATICA:
        return _utc(timer.inizio_sessione) + timedelta(minutes=timer.impostazioni.studio_min)
    return None


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
    _richiedi(timer, "avvia", Stato.PRONTO)
    return replace(timer, stato=Stato.STUDIO, inizio_sessione=adesso)


def pausa(timer: Timer, adesso: datetime) -> tuple[Timer, Sessione | None]:
    """Evento "pausa": STUDIO -> PAUSA, chiude la sessione (RF8, RF10).

    Pre:  precondizioni comuni.
    Post: restituisce il timer in PAUSA e la sessione
          ``[timer.inizio_sessione, adesso)``, oppure None se ha durata nulla
          (RF13). ``fine_pausa == adesso + pausa_spettante(durata studiata)``.
    Solleva: TransizioneNonValida se ``timer.stato`` non e' STUDIO.
    """
    _richiedi(timer, "pausa", Stato.STUDIO)
    sessione = _chiudi_sessione(timer, adesso)
    studiato = durata(sessione) if sessione else 0
    fine_pausa = _utc(adesso) + timedelta(seconds=pausa_spettante(studiato, timer.impostazioni))
    return replace(timer, stato=Stato.PAUSA, inizio_sessione=None, fine_pausa=fine_pausa), sessione


def riprendi(timer: Timer, adesso: datetime) -> Timer:
    """Evento "riprendi": PAUSA -> STUDIO, apre una sessione (RF8, RF11).

    Pre:  precondizioni comuni.
    Post: restituisce il timer in STUDIO con ``inizio_sessione == adesso``;
          la pausa residua viene persa.
    Solleva: TransizioneNonValida se ``timer.stato`` non e' PAUSA.
    """
    _richiedi(timer, "riprendi", Stato.PAUSA)
    return replace(timer, stato=Stato.STUDIO, inizio_sessione=adesso, fine_pausa=None)


def termina(timer: Timer, adesso: datetime) -> tuple[Timer, Sessione | None]:
    """Evento "termina": PRONTO, STUDIO o PAUSA -> CONCLUSO (RF8).

    Pre:  precondizioni comuni.
    Post: restituisce il timer in CONCLUSO e, se il timer era in STUDIO, la
          sessione ``[timer.inizio_sessione, adesso)`` (None se di durata
          nulla); negli altri casi None.
    Solleva: TransizioneNonValida se ``timer.stato`` e' CONCLUSO.
    """
    _richiedi(timer, "termina", Stato.PRONTO, Stato.STUDIO, Stato.PAUSA)
    sessione = _chiudi_sessione(timer, adesso) if timer.stato is Stato.STUDIO else None
    return replace(timer, stato=Stato.CONCLUSO, inizio_sessione=None, fine_pausa=None), sessione


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
    sessione = None
    suona = False
    scadenza = _scadenza_studio(timer)
    if scadenza is not None and _utc(adesso) >= scadenza:
        timer, sessione = pausa(timer, scadenza)
        suona = True
    if timer.stato is Stato.PAUSA and _utc(adesso) >= _utc(timer.fine_pausa):
        timer = replace(timer, stato=Stato.PRONTO, fine_pausa=None)
        suona = True
    return timer, sessione, suona


def secondi_rimanenti(timer: Timer, adesso: datetime) -> int | None:
    """Secondi alla prossima scadenza, per il quadrante del pomodoro (RF12).

    Pre:  non ci sono scadenze pendenti (vedi precondizioni comuni).
    Post: in STUDIO statico e in PAUSA restituisce i secondi alla scadenza,
          sempre > 0; negli altri casi (STUDIO dinamico, PRONTO, CONCLUSO)
          restituisce None, perche' non c'e' una scadenza.
    """
    scadenza = _scadenza_studio(timer) or timer.fine_pausa
    if scadenza is None:
        return None
    return _secondi(adesso, scadenza)


# --- Giorni e statistiche --------------------------------------------------

def giorno_di(istante: datetime) -> date:
    """Giorno di calendario, nell'ora italiana, a cui appartiene ``istante``.

    Pre:  ``istante`` ha il fuso orario.
    Post: restituisce la data di ``istante`` convertito in FUSO.
    """
    return istante.astimezone(FUSO).date()


def ripartisci_per_giorno(sessione: Sessione) -> dict[date, int]:
    """Divide la durata della sessione fra i giorni in cui e' avvenuta (RF16).

    Pre:  nessuna.
    Post: le chiavi sono i giorni da ``giorno_di(inizio)`` a quello che contiene
          l'ultimo secondo della sessione, e ogni valore e' > 0;
          ``sum(risultato.values()) == durata(sessione)``.
          Esempio: 23:00 -> 00:30 da' {primo giorno: 3600, secondo: 1800}.
    """
    quote = {}
    giorno = giorno_di(sessione.inizio)
    da = _utc(sessione.inizio)
    fine = _utc(sessione.fine)
    while da < fine:
        mezzanotte = _utc(datetime.combine(giorno + timedelta(days=1), time(), tzinfo=FUSO))
        a = min(mezzanotte, fine)
        quote[giorno] = _secondi(da, a)
        da = a
        giorno += timedelta(days=1)
    return quote


def studio_per_giorno(sessioni: Iterable[Sessione]) -> dict[date, int]:
    """Secondi di studio attribuiti a ciascun giorno (RF16, RF17).

    Pre:  nessuna.
    Post: per ogni giorno ``g`` il valore e' la somma di
          ``ripartisci_per_giorno(s).get(g, 0)`` sulle sessioni; compaiono solo
          i giorni con valore > 0. Con nessuna sessione restituisce {}.
    """
    totale = Counter()
    for sessione in sessioni:
        totale.update(ripartisci_per_giorno(sessione))
    return dict(totale)


def studio_per_settimana(sessioni: Iterable[Sessione]) -> dict[date, int]:
    """Secondi di studio per settimana, da lunedi' a domenica (RF17).

    Pre:  nessuna.
    Post: ogni chiave e' un lunedi'; il valore e' la somma di
          ``studio_per_giorno`` sui sette giorni che iniziano da quel lunedi'.
          La somma dei valori e' uguale a quella di ``studio_per_giorno``.
    """
    totale = Counter()
    for giorno, secondi in studio_per_giorno(sessioni).items():
        totale[giorno - timedelta(days=giorno.weekday())] += secondi
    return dict(totale)


def studio_per_materia(sessioni: Iterable[Sessione], dal: date, al: date) -> dict[int, int]:
    """Secondi di studio per materia nei giorni da ``dal`` ad ``al`` compresi (RF17).

    Pre:  dal <= al.
    Post: per ogni materia il valore e' la somma delle quote di
          ``ripartisci_per_giorno`` che cadono in ``[dal, al]``; compaiono solo
          le materie con valore > 0.
    Solleva: ValueError se dal > al.
    """
    if dal > al:
        raise ValueError("l'intervallo deve iniziare prima di finire")
    totale = Counter()
    for sessione in sessioni:
        for giorno, secondi in ripartisci_per_giorno(sessione).items():
            if dal <= giorno <= al:
                totale[sessione.materia_id] += secondi
    return dict(totale)


def sessioni_del_giorno(sessioni: Iterable[Sessione], giorno: date) -> list[Sessione]:
    """Sessioni da eliminare con la giornata ``giorno`` (RF15).

    Pre:  nessuna.
    Post: restituisce le sessioni ``s`` con ``giorno`` in
          ``ripartisci_per_giorno(s)``. Tolte queste, lo studio di ``giorno``
          e' zero.
    """
    return [s for s in sessioni if giorno in ripartisci_per_giorno(s)]


# --- Obiettivo, serie e bonsai ---------------------------------------------

def giorni_con_obiettivo(per_giorno: Mapping[date, int], obiettivo_min: int) -> set[date]:
    """Giorni in cui l'obiettivo e' raggiunto (RF18).

    Pre:  obiettivo_min >= 1.
    Post: restituisce i giorni ``g`` con ``per_giorno[g] >= obiettivo_min * 60``.
    """
    return {g for g, secondi in per_giorno.items() if secondi >= obiettivo_min * 60}


def serie(giorni_ok: set[date], oggi: date) -> int:
    """Giorni consecutivi con obiettivo raggiunto (RF19).

    Pre:  nessuna.
    Post: detto ``n`` il numero di giorni consecutivi in ``giorni_ok`` che
          terminano ieri, restituisce ``n + 1`` se ``oggi`` e' in ``giorni_ok``,
          altrimenti ``n``. I giorni successivi a ``oggi`` sono ignorati.
    """
    n = 0
    giorno = oggi - timedelta(days=1)
    while giorno in giorni_ok:
        n += 1
        giorno -= timedelta(days=1)
    return n + (oggi in giorni_ok)


class Stadio(Enum):
    SEME = "seme"
    GERMOGLIO = "germoglio"
    PIANTINA = "piantina"
    ALBERELLO = "alberello"
    BONSAI_FIORITO = "bonsai fiorito"


# Giorni minimi per ogni stadio, dal piu' alto al piu' basso (RF20).
_SOGLIE_BONSAI = (
    (20, Stadio.BONSAI_FIORITO),
    (10, Stadio.ALBERELLO),
    (4, Stadio.PIANTINA),
    (1, Stadio.GERMOGLIO),
)


def costanza(giorni_ok: set[date], oggi: date) -> int:
    """Quanti giorni di ``giorni_ok`` cadono negli ultimi GIORNI_BONSAI giorni, oggi incluso (RF20)."""
    primo = oggi - timedelta(days=GIORNI_BONSAI - 1)
    return sum(1 for g in giorni_ok if primo <= g <= oggi)


def prossima_soglia(k: int) -> int | None:
    """Giorni di costanza che servono per lo stadio successivo; None se il bonsai e' gia' fiorito."""
    return min((soglia for soglia, _ in _SOGLIE_BONSAI if soglia > k), default=None)


def stadio_bonsai(giorni_ok: set[date], oggi: date) -> Stadio:
    """Stadio del bonsai in base alla costanza recente (RF20).

    Pre:  nessuna.
    Post: detto ``k`` il numero di giorni di ``giorni_ok`` compresi negli
          ultimi GIORNI_BONSAI giorni, oggi incluso, restituisce SEME se k = 0,
          GERMOGLIO se 1 <= k <= 3, PIANTINA se 4 <= k <= 9, ALBERELLO se
          10 <= k <= 19, BONSAI_FIORITO se k >= 20.
          Monotonia: aggiungere giorni a ``giorni_ok`` non abbassa lo stadio.
    """
    k = costanza(giorni_ok, oggi)
    for soglia, stadio in _SOGLIE_BONSAI:
        if k >= soglia:
            return stadio
    return Stadio.SEME


# --- Esportazione ----------------------------------------------------------

def esporta_csv(sessioni: Iterable[Sessione], nomi: Mapping[int, str]) -> str:
    """Testo CSV con tutte le sessioni, pronto da aprire con Excel in italiano (RF21).

    Pre:  ogni ``materia_id`` delle sessioni e' una chiave di ``nomi``.
    Post: i campi sono separati da ``;``, il separatore di Excel in italiano.
          La prima riga e' ``Materia;Giorno;Inizio;Fine;Minuti``; segue una riga
          per sessione, in ordine di inizio, con il giorno (gg/mm/aaaa) e le ore
          (hh:mm) di inizio e fine nell'ora italiana, e la durata in minuti con
          al piu' un decimale dopo la virgola. Un nome che contiene ``;`` o
          virgolette e' racchiuso fra virgolette secondo le regole del CSV.
    """
    testo = io.StringIO()
    scrittore = csv.writer(testo, delimiter=";", lineterminator="\n")
    scrittore.writerow(["Materia", "Giorno", "Inizio", "Fine", "Minuti"])
    for s in sorted(sessioni, key=lambda s: _utc(s.inizio)):
        inizio, fine = s.inizio.astimezone(FUSO), s.fine.astimezone(FUSO)
        minuti = f"{durata(s) / 60:.1f}".removesuffix(".0").replace(".", ",")
        scrittore.writerow([
            nomi[s.materia_id],
            inizio.strftime("%d/%m/%Y"),
            inizio.strftime("%H:%M"),
            fine.strftime("%H:%M"),
            minuti,
        ])
    return testo.getvalue()
