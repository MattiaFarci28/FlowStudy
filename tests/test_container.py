"""Test sul container in esecuzione: il servizio vero, raggiunto via rete.

Si lanciano solo se FLOWSTUDY_URL indica dove risponde il container:

    docker run -d -p 8000:8000 --name flowstudy flowstudy
    FLOWSTUDY_URL=http://localhost:8000 pytest -m container

Altrimenti vengono saltati. Qui non c'e' l'orologio finto: si verifica che
l'immagine contenga tutto il necessario e che i pezzi funzionino insieme.
"""

import os
import uuid

import httpx2 as httpx
import pytest

URL = os.environ.get("FLOWSTUDY_URL")

pytestmark = [
    pytest.mark.container,
    pytest.mark.skipif(not URL, reason="FLOWSTUDY_URL non impostata: nessun container da provare"),
]


@pytest.fixture
def client():
    with httpx.Client(base_url=URL, timeout=10) as c:
        yield c


def test_il_servizio_risponde(client):
    assert client.get("/openapi.json").json()["info"]["title"] == "FlowStudy"


def test_una_sessione_di_studio_completa(client):
    # Il database del container puo' contenere dati di prove precedenti:
    # si usa un nome nuovo e si libera un eventuale timer rimasto attivo.
    if client.get("/timer").json()["attivo"]:
        client.post("/timer/termina")
    materia = client.post("/materie", json={"nome": f"Prova {uuid.uuid4().hex[:8]}"}).json()

    assert client.post("/timer", json={"materia_id": materia["id"]}).status_code == 201
    assert client.post("/timer/avvia").json()["stato"] == "studio"
    assert client.post("/timer/termina").json()["attivo"] is False

    assert client.get("/statistiche").status_code == 200
    assert client.get("/export.csv").text.startswith("materia,inizio,fine,durata_s")
    assert client.delete(f"/materie/{materia['id']}").status_code == 204
