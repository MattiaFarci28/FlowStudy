"""Test di unita' della logica di dominio: casi scelti a mano.

Ogni gruppo prova una funzione su esempi tipici e sui valori limite
(il primo e l'ultimo valore ammessi, e quelli subito fuori).
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from src.domain import (
    FUSO,
    PAUSA_MASSIMA_S,
    Impostazioni,
    Modalita,
    Sessione,
    Stadio,
    Stato,
    Timer,
    TransizioneNonValida,
    aggiorna,
    avvia,
    chiave_nome,
    durata,
    esporta_csv,
    giorni_con_obiettivo,
    giorno_di,
    normalizza_nome,
    pausa,
    pausa_spettante,
    ripartisci_per_giorno,
    riprendi,
    secondi_rimanenti,
    serie,
    sessioni_del_giorno,
    stadio_bonsai,
    studio_per_giorno,
    studio_per_materia,
    studio_per_settimana,
    termina,
)


def ora(*args):
    """Istante nell'ora italiana: ora(2026, 10, 27, 15, 0)."""
    return datetime(*args, tzinfo=FUSO)


STATICA = Impostazioni()                                # 25 di studio, 5 di pausa
DINAMICA = Impostazioni(modalita=Modalita.DINAMICA)
OGGI = date(2026, 10, 27)
T0 = ora(2026, 10, 27, 15, 0)


def in_studio(impostazioni=STATICA, inizio=T0):
    return Timer(1, impostazioni, Stato.STUDIO, inizio_sessione=inizio)


def in_pausa(fine_pausa=T0):
    return Timer(1, STATICA, Stato.PAUSA, fine_pausa=fine_pausa)


# --- Materie ---------------------------------------------------------------

def test_normalizza_nome_toglie_gli_spazi_esterni():
    assert normalizza_nome("  Analisi 2 ") == "Analisi 2"


@pytest.mark.parametrize("nome", ["a", "x" * 50, " " + "x" * 50 + " "])
def test_normalizza_nome_accetta_i_limiti(nome):
    assert normalizza_nome(nome) == nome.strip()


@pytest.mark.parametrize("nome", ["", "   ", "x" * 51])
def test_normalizza_nome_rifiuta_fuori_limite(nome):
    with pytest.raises(ValueError):
        normalizza_nome(nome)


def test_chiave_nome_ignora_maiuscole_e_spazi():
    assert chiave_nome("Analisi") == chiave_nome(" ANALISI ") == "analisi"


# --- Impostazioni ----------------------------------------------------------

def test_impostazioni_predefinite():
    assert Impostazioni() == Impostazioni(Modalita.STATICA, 25, 5, 120, "")


@pytest.mark.parametrize("campi", [
    {"studio_min": 1}, {"studio_min": 120},
    {"pausa_min": 1}, {"pausa_min": 60},
    {"obiettivo_min": 1}, {"obiettivo_min": 1440},
    {"nome": "x" * 30},
])
def test_impostazioni_accettano_i_limiti(campi):
    Impostazioni(**campi)


@pytest.mark.parametrize("campi", [
    {"studio_min": 0}, {"studio_min": 121},
    {"pausa_min": 0}, {"pausa_min": 61},
    {"obiettivo_min": 0}, {"obiettivo_min": 1441},
    {"nome": "x" * 31},
])
def test_impostazioni_rifiutano_fuori_limite(campi):
    with pytest.raises(ValueError):
        Impostazioni(**campi)


# --- Pausa spettante -------------------------------------------------------

def test_pausa_statica_e_quella_impostata():
    assert pausa_spettante(3 * 3600, Impostazioni(pausa_min=10)) == 600


@pytest.mark.parametrize("studio_s, pausa_s", [
    (0, 0),
    (4, 0),
    (5, 1),
    (7 * 60, 84),                   # 7 min -> 1 min e 24 s
    (50 * 60, 600),                 # 50 min -> 10 min
    (5 * PAUSA_MASSIMA_S - 5, PAUSA_MASSIMA_S - 1),
    (5 * PAUSA_MASSIMA_S, PAUSA_MASSIMA_S),
    (3 * 3600, PAUSA_MASSIMA_S),    # 3 ore -> tetto di 30 min
])
def test_pausa_dinamica(studio_s, pausa_s):
    assert pausa_spettante(studio_s, DINAMICA) == pausa_s


# --- Sessione e timer: invarianti ------------------------------------------

def test_durata_della_sessione():
    assert durata(Sessione(1, T0, T0 + timedelta(minutes=50))) == 3000


def test_durata_fra_fusi_diversi():
    # Le 15:00 italiane d'autunno sono le 14:00 UTC.
    assert durata(Sessione(1, T0, datetime(2026, 10, 27, 14, 30, tzinfo=UTC))) == 1800


@pytest.mark.parametrize("fine", [T0, T0 - timedelta(seconds=1)])
def test_sessione_deve_finire_dopo_l_inizio(fine):
    with pytest.raises(ValueError):
        Sessione(1, T0, fine)


@pytest.mark.parametrize("stato, inizio, fine_pausa", [
    (Stato.STUDIO, None, None),
    (Stato.PAUSA, None, None),
    (Stato.PRONTO, T0, None),
    (Stato.PRONTO, None, T0),
    (Stato.CONCLUSO, T0, None),
])
def test_timer_rifiuta_stati_incoerenti(stato, inizio, fine_pausa):
    with pytest.raises(ValueError):
        Timer(1, STATICA, stato, inizio, fine_pausa)


# --- Timer: transizioni ----------------------------------------------------

def test_nuovo_timer_e_pronto():
    assert Timer(1, STATICA).stato is Stato.PRONTO


def test_avvia_apre_una_sessione():
    t = avvia(Timer(1, STATICA), T0)
    assert t.stato is Stato.STUDIO and t.inizio_sessione == T0


def test_pausa_chiude_la_sessione_e_calcola_la_fine_pausa():
    adesso = T0 + timedelta(minutes=50)
    t, s = pausa(in_studio(DINAMICA), adesso)
    assert t.stato is Stato.PAUSA and t.inizio_sessione is None
    assert s == Sessione(1, T0, adesso)
    assert t.fine_pausa == adesso + timedelta(minutes=10)


def test_pausa_subito_dopo_l_avvio_non_salva_sessioni():
    t, s = pausa(in_studio(), T0)
    assert t.stato is Stato.PAUSA and s is None


def test_riprendi_apre_una_nuova_sessione():
    adesso = T0 - timedelta(minutes=2)          # prima della fine della pausa
    t = riprendi(in_pausa(), adesso)
    assert t.stato is Stato.STUDIO and t.inizio_sessione == adesso and t.fine_pausa is None


def test_termina_da_studio_chiude_la_sessione():
    adesso = T0 + timedelta(minutes=8)
    t, s = termina(in_studio(), adesso)
    assert t.stato is Stato.CONCLUSO and s == Sessione(1, T0, adesso)


@pytest.mark.parametrize("timer", [Timer(1, STATICA), in_pausa()])
def test_termina_da_pronto_o_pausa_non_salva_sessioni(timer):
    t, s = termina(timer, T0)
    assert t == Timer(1, STATICA, Stato.CONCLUSO) and s is None


def test_termina_subito_dopo_l_avvio_non_salva_sessioni():
    assert termina(in_studio(), T0)[1] is None


def _evento(nome, timer):
    funzioni = {"avvia": avvia, "pausa": pausa, "riprendi": riprendi, "termina": termina}
    return funzioni[nome](timer, T0)


@pytest.mark.parametrize("timer, evento", [
    (Timer(1, STATICA), "pausa"),
    (Timer(1, STATICA), "riprendi"),
    (in_studio(), "avvia"),
    (in_studio(), "riprendi"),
    (in_pausa(), "avvia"),
    (in_pausa(), "pausa"),
    (Timer(1, STATICA, Stato.CONCLUSO), "avvia"),
    (Timer(1, STATICA, Stato.CONCLUSO), "pausa"),
    (Timer(1, STATICA, Stato.CONCLUSO), "riprendi"),
    (Timer(1, STATICA, Stato.CONCLUSO), "termina"),
])
def test_eventi_non_ammessi_sono_rifiutati(timer, evento):
    with pytest.raises(TransizioneNonValida):
        _evento(evento, timer)


# --- Timer: scadenze -------------------------------------------------------

def test_aggiorna_senza_scadenze_non_cambia_nulla():
    t = in_studio()
    assert aggiorna(t, T0 + timedelta(minutes=24, seconds=59)) == (t, None, False)


def test_aggiorna_alla_fine_dello_studio_va_in_pausa_e_suona():
    fine_studio = T0 + timedelta(minutes=25)
    t, s, suona = aggiorna(in_studio(), fine_studio)
    assert suona and t.stato is Stato.PAUSA
    assert s == Sessione(1, T0, fine_studio)
    assert t.fine_pausa == fine_studio + timedelta(minutes=5)


def test_aggiorna_chiude_la_sessione_alla_scadenza_non_al_ritorno():
    # Si torna alle 15:28: la sessione finisce comunque alle 15:25.
    t, s, suona = aggiorna(in_studio(), T0 + timedelta(minutes=28))
    assert s.fine == T0 + timedelta(minutes=25) and t.stato is Stato.PAUSA


def test_aggiorna_applica_entrambe_le_scadenze():
    t, s, suona = aggiorna(in_studio(), T0 + timedelta(hours=1))
    assert suona and t.stato is Stato.PRONTO and durata(s) == 25 * 60


def test_aggiorna_in_dinamica_non_fa_scadere_lo_studio():
    t = in_studio(DINAMICA)
    assert aggiorna(t, T0 + timedelta(hours=5)) == (t, None, False)


def test_aggiorna_alla_fine_della_pausa_torna_pronto():
    t, s, suona = aggiorna(in_pausa(), T0)
    assert (t.stato, s, suona) == (Stato.PRONTO, None, True)


def test_aggiorna_e_idempotente():
    adesso = T0 + timedelta(hours=1)
    primo = aggiorna(in_studio(), adesso)[0]
    assert aggiorna(primo, adesso) == (primo, None, False)


def test_pausa_dinamica_di_zero_secondi_scade_subito():
    t, _ = pausa(in_studio(DINAMICA), T0 + timedelta(seconds=3))
    assert aggiorna(t, t.fine_pausa)[0].stato is Stato.PRONTO


@pytest.mark.parametrize("timer, atteso", [
    (in_studio(), 15 * 60),                         # statica: 25 - 10 minuti
    (in_pausa(T0 + timedelta(minutes=12)), 2 * 60),
    (in_studio(DINAMICA), None),
    (Timer(1, STATICA), None),
    (Timer(1, STATICA, Stato.CONCLUSO), None),
])
def test_secondi_rimanenti(timer, atteso):
    assert secondi_rimanenti(timer, T0 + timedelta(minutes=10)) == atteso


# --- Giorni ----------------------------------------------------------------

@pytest.mark.parametrize("istante, giorno", [
    (ora(2026, 10, 27, 0, 0, 0), date(2026, 10, 27)),
    (ora(2026, 10, 27, 23, 59, 59), date(2026, 10, 27)),
    (datetime(2026, 10, 27, 23, 30, tzinfo=UTC), date(2026, 10, 28)),  # 00:30 in Italia
])
def test_giorno_di_usa_l_ora_italiana(istante, giorno):
    assert giorno_di(istante) == giorno


def test_ripartisci_sessione_nello_stesso_giorno():
    s = Sessione(1, T0, T0 + timedelta(hours=1))
    assert ripartisci_per_giorno(s) == {OGGI: 3600}


def test_ripartisci_sessione_a_cavallo_della_mezzanotte():
    s = Sessione(1, ora(2026, 10, 27, 23, 0), ora(2026, 10, 28, 0, 30))
    assert ripartisci_per_giorno(s) == {OGGI: 3600, date(2026, 10, 28): 1800}


def test_ripartisci_sessione_che_finisce_a_mezzanotte():
    s = Sessione(1, ora(2026, 10, 27, 23, 0), ora(2026, 10, 28, 0, 0))
    assert ripartisci_per_giorno(s) == {OGGI: 3600}


def test_ripartisci_su_piu_giorni():
    s = Sessione(1, ora(2026, 10, 27, 12, 0), ora(2026, 10, 29, 12, 0))
    assert ripartisci_per_giorno(s) == {
        OGGI: 12 * 3600, date(2026, 10, 28): 24 * 3600, date(2026, 10, 29): 12 * 3600,
    }


@pytest.mark.parametrize("giorno, ore", [
    (date(2026, 3, 29), 23),     # ora legale: si salta dalle 2 alle 3
    (date(2026, 10, 25), 25),    # ora solare: le 3 tornano alle 2
])
def test_ripartisci_nei_giorni_del_cambio_dell_ora(giorno, ore):
    s = Sessione(1, ora(giorno.year, giorno.month, giorno.day), ora(giorno.year, giorno.month, giorno.day + 1))
    assert durata(s) == ore * 3600
    assert ripartisci_per_giorno(s) == {giorno: ore * 3600}


# --- Statistiche -----------------------------------------------------------

REGISTRO = [
    Sessione(1, ora(2026, 10, 25, 22, 0), ora(2026, 10, 26, 1, 0)),   # domenica -> lunedi'
    Sessione(2, ora(2026, 10, 27, 9, 0), ora(2026, 10, 27, 10, 0)),
    Sessione(1, ora(2026, 10, 27, 15, 0), ora(2026, 10, 27, 15, 30)),
]


def test_studio_per_giorno():
    assert studio_per_giorno(REGISTRO) == {
        date(2026, 10, 25): 2 * 3600,
        date(2026, 10, 26): 3600,
        OGGI: 5400,
    }


def test_studio_per_giorno_senza_sessioni():
    assert studio_per_giorno([]) == {}


def test_studio_per_settimana_divide_domenica_e_lunedi():
    assert studio_per_settimana(REGISTRO) == {
        date(2026, 10, 19): 2 * 3600,     # settimana che finisce domenica 25
        date(2026, 10, 26): 3600 + 5400,  # settimana da lunedi' 26
    }


def test_studio_per_materia_nell_intervallo():
    assert studio_per_materia(REGISTRO, date(2026, 10, 26), OGGI) == {1: 3600 + 1800, 2: 3600}
    assert studio_per_materia(REGISTRO, OGGI, OGGI) == {1: 1800, 2: 3600}
    assert studio_per_materia(REGISTRO, date(2026, 10, 1), date(2026, 10, 2)) == {}


def test_studio_per_materia_rifiuta_intervallo_rovesciato():
    with pytest.raises(ValueError):
        studio_per_materia(REGISTRO, OGGI, OGGI - timedelta(days=1))


def test_sessioni_del_giorno_comprende_quelle_a_cavallo():
    assert sessioni_del_giorno(REGISTRO, date(2026, 10, 26)) == [REGISTRO[0]]
    assert sessioni_del_giorno(REGISTRO, OGGI) == REGISTRO[1:]
    assert sessioni_del_giorno(REGISTRO, date(2026, 10, 24)) == []


# --- Obiettivo, serie e bonsai ---------------------------------------------

def test_giorni_con_obiettivo_al_limite():
    per_giorno = {OGGI: 3600, date(2026, 10, 26): 3599}
    assert giorni_con_obiettivo(per_giorno, 60) == {OGGI}


def giorni_fa(*n):
    return {OGGI - timedelta(days=i) for i in n}


@pytest.mark.parametrize("giorni_ok, attesa", [
    (set(), 0),
    (giorni_fa(0), 1),
    (giorni_fa(1, 2, 3), 3),          # oggi non ancora raggiunto: la serie resta
    (giorni_fa(0, 1, 2, 3), 4),
    (giorni_fa(0, 2, 3), 1),          # ieri mancato: la serie riparte
    (giorni_fa(2, 3), 0),
    (giorni_fa(-1, 1), 1),            # i giorni futuri non contano
])
def test_serie(giorni_ok, attesa):
    assert serie(giorni_ok, OGGI) == attesa


@pytest.mark.parametrize("k, stadio", [
    (0, Stadio.SEME),
    (1, Stadio.GERMOGLIO), (3, Stadio.GERMOGLIO),
    (4, Stadio.PIANTINA), (9, Stadio.PIANTINA),
    (10, Stadio.ALBERELLO), (19, Stadio.ALBERELLO),
    (20, Stadio.BONSAI_FIORITO), (30, Stadio.BONSAI_FIORITO),
])
def test_stadio_bonsai_alle_soglie(k, stadio):
    assert stadio_bonsai(giorni_fa(*range(k)), OGGI) is stadio


def test_stadio_bonsai_conta_solo_gli_ultimi_30_giorni():
    # 29 giorni fa e' dentro la finestra, 30 giorni fa e domani sono fuori.
    assert stadio_bonsai(giorni_fa(29), OGGI) is Stadio.GERMOGLIO
    assert stadio_bonsai(giorni_fa(30, -1), OGGI) is Stadio.SEME


# --- Esportazione ----------------------------------------------------------

def test_esporta_csv():
    testo = esporta_csv(reversed(REGISTRO[1:]), {1: 'Analisi, "2"', 2: "Fisica"})
    assert testo.splitlines() == [
        "materia,inizio,fine,durata_s",
        "Fisica,2026-10-27T09:00:00+01:00,2026-10-27T10:00:00+01:00,3600",
        '"Analisi, ""2""",2026-10-27T15:00:00+01:00,2026-10-27T15:30:00+01:00,1800',
    ]


def test_esporta_csv_senza_sessioni():
    assert esporta_csv([], {}) == "materia,inizio,fine,durata_s\n"
