"""Property-based testing della logica di dominio.

Invece di casi scelti a mano, Hypothesis genera centinaia di input casuali
(istanti, sessioni, sequenze di eventi) e controlla che certe proprieta'
valgano sempre. Gli assiomi e i teoremi di docs/03-specifica-algebrica.md
compaiono qui come proprieta' (A1-A4, T1, T2).
"""

import csv
import io
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

from hypothesis import given
from hypothesis import strategies as st

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
    durata,
    esporta_csv,
    giorno_di,
    normalizza_nome,
    pausa,
    pausa_spettante,
    ripartisci_per_giorno,
    riprendi,
    serie,
    sessioni_del_giorno,
    stadio_bonsai,
    studio_per_giorno,
    studio_per_settimana,
    termina,
)

# --- Generatori ------------------------------------------------------------

# Istanti al secondo fra il 2026 e il 2027, nell'ora italiana: comprendono
# due cambi dell'ora legale e due di quella solare.
_INIZIO_2026 = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
istanti = st.integers(_INIZIO_2026, _INIZIO_2026 + 2 * 365 * 86400).map(
    lambda s: datetime.fromtimestamp(s, FUSO)
)


def dopo(istante, secondi):
    """Istante che segue ``istante`` di ``secondi`` reali (anche col cambio d'ora)."""
    return (istante.astimezone(UTC) + timedelta(seconds=secondi)).astimezone(FUSO)


@st.composite
def sessioni(draw):
    inizio = draw(istanti)
    return Sessione(draw(st.integers(1, 3)), inizio, dopo(inizio, draw(st.integers(1, 3 * 86400))))


registri = st.lists(sessioni(), max_size=8)
giorni = st.dates(date(2025, 12, 1), date(2028, 1, 31))
impostazioni = st.builds(
    Impostazioni,
    modalita=st.sampled_from(Modalita),
    studio_min=st.integers(1, 120),
    pausa_min=st.integers(1, 60),
)


def studio(registro, giorno):
    return studio_per_giorno(registro).get(giorno, 0)


def quota(sessione, giorno):
    return ripartisci_per_giorno(sessione).get(giorno, 0)


def elimina_giorno(registro, giorno):
    da_togliere = sessioni_del_giorno(registro, giorno)
    return [s for s in registro if s not in da_togliere]


# --- Ripartizione per giorno (RF16) ----------------------------------------

@given(sessioni())
def test_la_ripartizione_conserva_la_durata(s):
    quote = ripartisci_per_giorno(s)
    assert sum(quote.values()) == durata(s)
    assert all(secondi > 0 for secondi in quote.values())


@given(sessioni())
def test_la_ripartizione_copre_giorni_consecutivi(s):
    elenco = sorted(ripartisci_per_giorno(s))
    assert elenco[0] == giorno_di(s.inizio)
    assert elenco == [elenco[0] + timedelta(days=i) for i in range(len(elenco))]


# --- Specifica algebrica del registro --------------------------------------

@given(giorni)
def test_A1_registro_vuoto(g):
    assert studio([], g) == 0


@given(registri, sessioni(), giorni)
def test_A2_aggiungere_una_sessione_somma_la_sua_quota(r, s, g):
    assert studio(r + [s], g) == studio(r, g) + quota(s, g)


@given(giorni)
def test_A3_eliminare_un_giorno_dal_registro_vuoto(g):
    assert elimina_giorno([], g) == []


@given(registri, sessioni(), giorni)
def test_A4_eliminare_un_giorno_dopo_un_aggiunta(r, s, g):
    if quota(s, g) > 0:
        assert elimina_giorno(r + [s], g) == elimina_giorno(r, g)
    else:
        assert elimina_giorno(r + [s], g) == elimina_giorno(r, g) + [s]


@given(registri, st.data())
def test_T1_dopo_aver_eliminato_un_giorno_il_suo_studio_e_zero(r, data):
    # Si sceglie spesso un giorno toccato dal registro, altrimenti il test
    # sarebbe banale.
    toccati = sorted(studio_per_giorno(r))
    g = data.draw(st.sampled_from(toccati) if toccati else giorni)
    assert studio(elimina_giorno(r, g), g) == 0


@given(registri, st.data())
def test_T2_l_ordine_delle_sessioni_non_conta(r, data):
    rimescolato = data.draw(st.permutations(r))
    assert studio_per_giorno(rimescolato) == studio_per_giorno(r)


@given(registri)
def test_le_settimane_sommano_quanto_i_giorni(r):
    settimane = studio_per_settimana(r)
    assert sum(settimane.values()) == sum(studio_per_giorno(r).values())
    assert all(lunedi.weekday() == 0 for lunedi in settimane)


# --- Pausa spettante (RF10) ------------------------------------------------

@given(st.integers(0, 10**6), st.integers(0, 10**6))
def test_la_pausa_dinamica_cresce_con_lo_studio_fino_al_tetto(a, b):
    din = Impostazioni(modalita=Modalita.DINAMICA)
    meno, piu = sorted((a, b))
    assert 0 <= pausa_spettante(meno, din) <= pausa_spettante(piu, din) <= PAUSA_MASSIMA_S


# --- Serie e bonsai (RF19, RF20) -------------------------------------------

@given(st.sets(giorni), giorni)
def test_raggiungere_l_obiettivo_oggi_allunga_la_serie_di_uno(ok, oggi):
    senza_oggi = ok - {oggi}
    assert serie(senza_oggi | {oggi}, oggi) == serie(senza_oggi, oggi) + 1


@given(st.sets(giorni), giorni)
def test_la_serie_non_supera_i_giorni_raggiunti(ok, oggi):
    assert serie(ok, oggi) <= len({g for g in ok if g <= oggi})


@given(st.sets(giorni), st.sets(giorni), giorni)
def test_il_bonsai_non_regredisce_aggiungendo_giorni(ok, altri, oggi):
    ordine = list(Stadio)       # dal seme al bonsai fiorito
    prima = ordine.index(stadio_bonsai(ok, oggi))
    assert ordine.index(stadio_bonsai(ok | altri, oggi)) >= prima


# --- Timer (RF8, statechart) -----------------------------------------------

EVENTI = {"avvia": avvia, "pausa": pausa, "riprendi": riprendi, "termina": termina}


@given(
    impostazioni,
    istanti,
    st.lists(st.tuples(st.sampled_from(sorted(EVENTI)), st.integers(0, 3 * 3600)), max_size=15),
)
def test_qualsiasi_sequenza_di_eventi_rispetta_lo_statechart(imp, inizio, passi):
    """Simula un utente che preme pulsanti a caso, a intervalli casuali.

    Come fara' l'API, prima di ogni evento si applicano le scadenze. Alla fine:
    - le sessioni non si sovrappongono e cadono nel tempo trascorso;
    - in modalita' statica nessuna sessione supera il tempo di studio.
    """
    timer = Timer(1, imp)
    adesso = inizio
    salvate = []
    for nome, attesa in passi:
        adesso = dopo(adesso, attesa)
        timer, sessione, _ = aggiorna(timer, adesso)
        salvate.append(sessione)
        try:
            esito = EVENTI[nome](timer, adesso)
        except TransizioneNonValida:
            continue
        timer, sessione = esito if isinstance(esito, tuple) else (esito, None)
        salvate.append(sessione)

    # Confronti in UTC: fra istanti con lo stesso fuso Python ignora l'ora legale.
    salvate = [(s.inizio.astimezone(UTC), s.fine.astimezone(UTC), s) for s in salvate if s]
    for (_, fine, _), (inizio_dopo, _, _) in pairwise(salvate):
        assert fine <= inizio_dopo
    assert all(inizio <= da and a <= adesso for da, a, _ in salvate)
    salvate = [s for _, _, s in salvate]
    if imp.modalita is Modalita.STATICA:
        assert all(durata(s) <= imp.studio_min * 60 for s in salvate)


@given(impostazioni, istanti, st.integers(0, 10 * 3600))
def test_aggiorna_e_idempotente(imp, inizio, attesa):
    timer = Timer(1, imp, Stato.STUDIO, inizio_sessione=inizio)
    adesso = dopo(inizio, attesa)
    una_volta = aggiorna(timer, adesso)[0]
    assert aggiorna(una_volta, adesso) == (una_volta, None, False)


# --- Materie ed esportazione (RF1, RF21) -----------------------------------

nomi = st.text(min_size=1, max_size=50).filter(lambda n: n.strip() == n and n)


@given(nomi)
def test_normalizzare_due_volte_non_cambia_il_nome(nome):
    assert normalizza_nome(normalizza_nome(nome)) == normalizza_nome(nome)


@given(registri, nomi, nomi, nomi)
def test_il_csv_si_rilegge_uguale(r, n1, n2, n3):
    nomi_materie = {1: n1, 2: n2, 3: n3}
    righe = list(csv.reader(io.StringIO(esporta_csv(r, nomi_materie)), delimiter=";"))
    attese = sorted(r, key=lambda s: s.inizio.astimezone(UTC))
    assert righe[0] == ["Materia", "Giorno", "Inizio", "Fine", "Minuti"]
    assert [riga[0] for riga in righe[1:]] == [nomi_materie[s.materia_id] for s in attese]
    minuti = [float(riga[4].replace(",", ".")) for riga in righe[1:]]
    assert minuti == [round(durata(s) / 60, 1) for s in attese]
