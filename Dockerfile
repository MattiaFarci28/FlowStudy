# Immagine del servizio FlowStudy (RNF4).
#
#   docker build -t flowstudy .
#   docker run -d -p 8000:8000 -v flowstudy-dati:/dati --name flowstudy flowstudy
#
# Stessa versione di Python dell'ambiente di sviluppo e della pipeline.
FROM python:3.12-slim

# Niente file .pyc e output dei log subito visibile con "docker logs".
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Prima solo le dipendenze: finche' requirements.txt non cambia, Docker
# riusa questo strato e una modifica al codice non le reinstalla.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

# Il servizio non gira come root. I dati stanno in /dati, un volume:
# sopravvivono quando il container viene ricreato.
RUN useradd --create-home flowstudy && mkdir /dati && chown flowstudy /dati
USER flowstudy
ENV FLOWSTUDY_DB=sqlite:////dati/flowstudy.db
VOLUME /dati

EXPOSE 8000

# Docker controlla ogni 30 secondi che il servizio risponda.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/openapi.json')"]

CMD ["uvicorn", "--factory", "src.api:crea_app", "--host", "0.0.0.0", "--port", "8000"]
