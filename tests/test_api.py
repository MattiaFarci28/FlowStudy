"""Test di integrazione dell'API: richieste HTTP vere su un database vero.

Ogni test parte da un database nuovo in un file temporaneo. L'orologio e'
sostituito da uno finto, che il test fa avanzare a piacere: cosi' si provano
in pochi millisecondi scadenze di 25 minuti, la mezzanotte e il ritorno dopo
un'assenza.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api import crea_app, orologio
from src.domain import FUSO

pytestmark = pytest.mark.integrazione


class OrologioFinto:
    def __init__(self, istante):
        self.adesso = istante.astimezone(UTC)

    def __call__(self):
        return self.adesso

    def avanza(self, **durata):
        self.adesso += timedelta(**durata)


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path / 'flowstudy.db'}"


@pytest.fixture
def ora():
    return OrologioFinto(datetime(2026, 10, 27, 15, 0, tzinfo=FUSO))   # martedi'


def client_per(url, ora):
    app = crea_app(url)
    app.dependency_overrides[orologio] = ora
    return TestClient(app)


@pytest.fixture
def client(url, ora):
    return client_per(url, ora)


def nuova_materia(client, nome="Analisi 2"):
    risposta = client.post("/materie", json={"nome": nome})
    assert risposta.status_code == 201
    return risposta.json()["id"]


def imposta(client, **campi):
    corpo = {"modalita": "statica", "studio_min": 25, "pausa_min": 5, "obiettivo_min": 120} | campi
    assert client.put("/impostazioni", json=corpo).status_code == 200


def avvia_timer(client, materia_id):
    assert client.post("/timer", json={"materia_id": materia_id}).status_code == 201
    return client.post("/timer/avvia").json()


def durate(client, **filtro):
    return [s["durata_s"] for s in client.get("/sessioni", params=filtro).json()]


# --- Materie ---------------------------------------------------------------

def test_creare_ed_elencare_materie(client):
    risposta = client.post("/materie", json={"nome": "  chimica "})
    assert risposta.status_code == 201 and risposta.json()["nome"] == "chimica"
    nuova_materia(client, "Analisi 2")
    assert [m["nome"] for m in client.get("/materie").json()] == ["Analisi 2", "chimica"]


@pytest.mark.parametrize("corpo, codice", [
    ({"nome": "analisi 2"}, 409),     # stesso nome, maiuscole diverse
    ({"nome": "   "}, 422),
    ({"nome": "x" * 51}, 422),
    ({}, 422),                        # campo mancante
])
def test_creare_materia_non_valida(client, corpo, codice):
    nuova_materia(client)
    assert client.post("/materie", json=corpo).status_code == codice
    assert len(client.get("/materie").json()) == 1


def test_rinominare_materia(client):
    m = nuova_materia(client)
    nuova_materia(client, "Fisica")
    assert client.patch(f"/materie/{m}", json={"nome": "Analisi II"}).json()["nome"] == "Analisi II"
    assert client.patch(f"/materie/{m}", json={"nome": "FISICA"}).status_code == 409
    assert client.patch("/materie/99", json={"nome": "Chimica"}).status_code == 404


def test_eliminare_materia_e_sessioni(client, ora):
    m = nuova_materia(client)
    avvia_timer(client, m)
    ora.avanza(minutes=10)
    client.post("/timer/termina")
    assert client.delete(f"/materie/{m}").status_code == 204
    assert client.get("/materie").json() == [] and client.get("/sessioni").json() == []


def test_archiviare_materia_e_poi_riattivarla(client, ora):
    m = nuova_materia(client)
    avvia_timer(client, m)
    ora.avanza(minutes=10)
    client.post("/timer/termina")
    assert client.delete(f"/materie/{m}", params={"conserva_sessioni": True}).status_code == 204
    assert client.get("/materie").json() == []
    assert client.get("/sessioni").json()[0]["materia"] == "Analisi 2"     # le ore restano
    assert client.post("/timer", json={"materia_id": m}).status_code == 404  # non si usa piu'
    assert nuova_materia(client, "analisi 2") == m                          # riattivata


def test_non_si_elimina_la_materia_del_timer_attivo(client):
    m = nuova_materia(client)
    avvia_timer(client, m)
    assert client.delete(f"/materie/{m}").status_code == 409
    assert client.delete("/materie/99").status_code == 404


# --- Impostazioni ----------------------------------------------------------

def test_impostazioni_predefinite_e_salvate(client):
    assert client.get("/impostazioni").json() == {
        "modalita": "statica", "studio_min": 25, "pausa_min": 5, "obiettivo_min": 120, "nome": "",
    }
    imposta(client, modalita="dinamica", obiettivo_min=90, nome="Mattia")
    assert client.get("/impostazioni").json()["nome"] == "Mattia"


@pytest.mark.parametrize("campi", [
    {"studio_min": 0}, {"pausa_min": 61}, {"obiettivo_min": 1441},
    {"nome": "x" * 31}, {"modalita": "a caso"},
])
def test_impostazioni_non_valide_lasciano_le_precedenti(client, campi):
    corpo = {"modalita": "statica", "studio_min": 25, "pausa_min": 5, "obiettivo_min": 120} | campi
    assert client.put("/impostazioni", json=corpo).status_code == 422
    assert client.get("/impostazioni").json()["obiettivo_min"] == 120


def test_il_timer_avviato_tiene_le_sue_impostazioni(client, ora):
    m = nuova_materia(client)
    avvia_timer(client, m)                      # partito con 25 minuti di studio
    imposta(client, studio_min=50)
    ora.avanza(minutes=25)
    assert client.get("/timer").json()["stato"] == "pausa"


# --- Timer -----------------------------------------------------------------

def test_senza_timer(client):
    assert client.get("/timer").json() == {"attivo": False, "suona": False}
    assert client.post("/timer/avvia").status_code == 404


def test_creare_il_timer(client):
    m = nuova_materia(client)
    risposta = client.post("/timer", json={"materia_id": m})
    assert risposta.status_code == 201 and risposta.json()["stato"] == "pronto"
    assert client.post("/timer", json={"materia_id": m}).status_code == 409   # uno alla volta
    assert client.post("/timer/termina").json()["attivo"] is False
    assert client.post("/timer", json={"materia_id": 99}).status_code == 404


def test_pomeriggio_in_modalita_statica(client, ora):
    """L'esempio di docs/02-statechart.md, passo per passo."""
    m = nuova_materia(client)
    assert avvia_timer(client, m)["secondi_rimanenti"] == 25 * 60     # 15:00

    ora.avanza(minutes=25)                                              # 15:25
    t = client.get("/timer").json()
    assert (t["stato"], t["suona"], t["secondi_rimanenti"]) == ("pausa", True, 5 * 60)
    assert client.get("/timer").json()["suona"] is False               # suona una volta sola

    ora.avanza(minutes=5)                                               # 15:30
    t = client.get("/timer").json()
    assert (t["stato"], t["suona"], t["secondi_rimanenti"]) == ("pronto", True, None)

    ora.avanza(minutes=2)                                               # 15:32
    client.post("/timer/avvia")
    ora.avanza(minutes=8)                                               # 15:40
    assert client.post("/timer/termina").json()["attivo"] is False
    assert durate(client) == [25 * 60, 8 * 60]


def test_pausa_dinamica_proporzionale_allo_studio(client, ora):
    imposta(client, modalita="dinamica")
    m = nuova_materia(client)
    assert avvia_timer(client, m)["secondi_rimanenti"] is None          # si studia quanto si vuole
    ora.avanza(minutes=50)
    assert client.get("/timer").json()["stato"] == "studio"             # nessuna scadenza
    t = client.post("/timer/pausa").json()
    assert (t["stato"], t["secondi_rimanenti"]) == ("pausa", 10 * 60)
    ora.avanza(minutes=4)
    assert client.post("/timer/riprendi").json()["stato"] == "studio"   # si riprende prima
    assert durate(client) == [50 * 60]


def test_eventi_non_ammessi(client):
    m = nuova_materia(client)
    avvia_timer(client, m)
    assert client.post("/timer/riprendi").status_code == 409
    assert client.post("/timer/avvia").status_code == 409
    assert client.post("/timer/salta").status_code == 422              # evento inesistente
    assert client.get("/timer").json()["stato"] == "studio"


def test_al_ritorno_la_sessione_finisce_alla_scadenza(client, ora):
    m = nuova_materia(client)
    avvia_timer(client, m)
    ora.avanza(hours=3)                                                 # ci si era dimenticati
    t = client.get("/timer").json()
    assert (t["stato"], t["suona"]) == ("pronto", True)
    assert durate(client) == [25 * 60]


def test_il_timer_sopravvive_al_riavvio_del_servizio(url, ora):
    m = nuova_materia(client_per(url, ora))
    avvia_timer(client_per(url, ora), m)
    ora.avanza(minutes=10)
    t = client_per(url, ora).get("/timer").json()                       # nuovo processo
    assert (t["stato"], t["secondi_rimanenti"]) == ("studio", 15 * 60)


def test_una_richiesta_rifiutata_non_lascia_tracce(client, ora):
    m = nuova_materia(client)
    avvia_timer(client, m)
    ora.avanza(minutes=26)                     # lo studio e' scaduto, nessuno l'ha ancora visto
    assert client.post("/timer/pausa").status_code == 409   # ormai e' in pausa: rifiutato
    assert client.get("/timer").json()["stato"] == "pausa"
    assert durate(client) == [25 * 60]         # la sessione e' salvata una volta sola


# --- Sessioni --------------------------------------------------------------

def test_sessione_a_cavallo_della_mezzanotte(client, ora):
    imposta(client, modalita="dinamica")
    m = nuova_materia(client)
    ora.adesso = datetime(2026, 10, 27, 23, 30, tzinfo=FUSO).astimezone(UTC)
    avvia_timer(client, m)
    ora.avanza(hours=1)
    client.post("/timer/termina")
    assert client.get("/statistiche").json()["per_giorno"] == {"2026-10-27": 1800, "2026-10-28": 1800}
    assert durate(client, giorno="2026-10-27") == durate(client, giorno="2026-10-28") == [3600]
    assert durate(client, giorno="2026-10-29") == []


def test_eliminare_sessioni_e_giornate(client, ora):
    imposta(client, modalita="dinamica")
    m = nuova_materia(client)
    for _ in range(3):
        avvia_timer(client, m)
        ora.avanza(minutes=30)
        client.post("/timer/termina")
    prima, *altre = client.get("/sessioni").json()
    assert client.delete(f"/sessioni/{prima['id']}").status_code == 204
    assert client.delete(f"/sessioni/{prima['id']}").status_code == 404
    assert client.delete("/giorni/2026-10-27").json() == {"eliminate": 2}
    assert client.get("/sessioni").json() == []
    assert client.delete("/giorni/27-10-2026").status_code == 422


# --- Statistiche -----------------------------------------------------------

def test_statistiche_senza_studio(client):
    s = client.get("/statistiche").json()
    assert (s["oggi"], s["studio_oggi_s"], s["serie"], s["bonsai"]) == ("2026-10-27", 0, 0, "seme")


def studia(client, ora, giorno, minuti, materia_id, alle=9):
    ora.adesso = datetime(2026, 10, giorno, alle, 0, tzinfo=FUSO).astimezone(UTC)
    avvia_timer(client, materia_id)
    ora.avanza(minutes=minuti)
    client.post("/timer/termina")


def test_serie_bonsai_e_settimane(client, ora):
    imposta(client, modalita="dinamica", obiettivo_min=60)
    m = nuova_materia(client)
    for giorno, minuti in [(22, 60), (24, 90), (25, 60), (26, 60), (27, 30)]:
        studia(client, ora, giorno, minuti, m)
    s = client.get("/statistiche").json()
    assert s["studio_oggi_s"] == 30 * 60
    assert s["serie"] == 3                  # 24, 25, 26; oggi (30 min) non interrompe
    assert s["bonsai"] == "piantina"        # 4 giorni con obiettivo negli ultimi 30
    assert s["per_settimana"] == {"2026-10-19": 210 * 60, "2026-10-26": 90 * 60}


def test_statistiche_per_materia(client, ora):
    imposta(client, modalita="dinamica")
    analisi, fisica = nuova_materia(client), nuova_materia(client, "Fisica")
    studia(client, ora, 26, 30, analisi)
    studia(client, ora, 27, 45, fisica)
    studia(client, ora, 27, 15, analisi, alle=11)
    risposta = client.get("/statistiche/materie", params={"dal": "2026-10-27", "al": "2026-10-27"})
    assert [(r["materia"], r["secondi"]) for r in risposta.json()] == [("Fisica", 2700), ("Analisi 2", 900)]
    assert client.get("/statistiche/materie", params={"dal": "2026-10-28", "al": "2026-10-27"}).status_code == 422


# --- Esportazione ----------------------------------------------------------

def test_esportazione_csv(client, ora):
    m = nuova_materia(client, 'Analisi, "2"')
    avvia_timer(client, m)
    ora.avanza(minutes=10)
    client.post("/timer/termina")
    risposta = client.get("/export.csv")
    assert risposta.headers["content-type"].startswith("text/csv")
    assert "flowstudy.csv" in risposta.headers["content-disposition"]
    assert risposta.text.splitlines() == [
        "materia,inizio,fine,durata_s",
        '"Analisi, ""2""",2026-10-27T15:00:00+01:00,2026-10-27T15:10:00+01:00,600',
    ]


# --- Configurazione --------------------------------------------------------

def test_l_orologio_vero_da_l_ora_utc_al_secondo():
    adesso = orologio()
    assert adesso.tzinfo is UTC and adesso.microsecond == 0
    assert abs(datetime.now(UTC) - adesso) < timedelta(seconds=5)


def test_il_database_si_sceglie_con_la_variabile_d_ambiente(tmp_path, monkeypatch):
    percorso = tmp_path / "scelto.db"
    monkeypatch.setenv("FLOWSTUDY_DB", f"sqlite:///{percorso}")
    nuova_materia(TestClient(crea_app()))
    assert percorso.exists()
