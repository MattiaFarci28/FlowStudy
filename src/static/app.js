"use strict";
// Interfaccia di FlowStudy: chiede i dati all'API e disegna le tre schermate.
// Le regole (pause, statistiche, serie, bonsai) stanno tutte nel server:
// qui si mostrano i risultati e si inoltrano i comandi dell'utente.

const $ = (selettore) => document.querySelector(selettore);
const NS = "http://www.w3.org/2000/svg";

const STADI = {
  "seme": [0, "Seme", "Raggiungi l'obiettivo di oggi per farlo germogliare."],
  "germoglio": [1, "Germoglio", "Ha messo le prime foglie: continua così."],
  "piantina": [2, "Piantina", "Sta crescendo con la tua costanza."],
  "alberello": [3, "Alberello", "Ha un tronco vero: lo studio è diventato un'abitudine."],
  "bonsai fiorito": [4, "Bonsai fiorito", "Almeno 20 giorni di obiettivo nell'ultimo mese. Splendido!"],
};

const stato = {
  impostazioni: null,
  materie: [],
  timer: { attivo: false },
  statistiche: null,
  calendario: { riferimento: null, espanso: false },  // giorno che decide settimana o mese mostrati
  giornoScelto: null,
  minutiGhiera: 25,
};

// --- Comunicazione con l'API ----------------------------------------------

async function api(metodo, percorso, corpo) {
  const opzioni = { method: metodo, headers: {} };
  if (corpo !== undefined) {
    opzioni.headers["Content-Type"] = "application/json";
    opzioni.body = JSON.stringify(corpo);
  }
  const risposta = await fetch(percorso, opzioni);
  if (!risposta.ok) {
    let messaggio = `Errore ${risposta.status}`;
    try {
      const dettaglio = (await risposta.json()).detail;
      messaggio = typeof dettaglio === "string" ? dettaglio : dettaglio.map((e) => e.msg).join("; ");
    } catch { /* risposta senza dettaglio: resta il codice */ }
    throw new Error(messaggio);
  }
  return risposta.status === 204 ? null : risposta.json();
}

function avvisa(testo) {
  const avviso = $("#avviso");
  avviso.textContent = testo;
  avviso.classList.add("visibile");
  clearTimeout(avvisa.attesa);
  avvisa.attesa = setTimeout(() => avviso.classList.remove("visibile"), 3500);
}

async function prova(azione) {
  try { await azione(); } catch (errore) { avvisa(errore.message); }
}

// --- Formati ----------------------------------------------------------------

const due = (n) => String(n).padStart(2, "0");
const ORA = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Rome" });

function cronometro(secondi) {
  const s = Math.max(0, Math.round(secondi));
  const ore = Math.floor(s / 3600);
  const minuti = Math.floor((s % 3600) / 60);
  return ore ? `${ore}:${due(minuti)}:${due(s % 60)}` : `${due(minuti)}:${due(s % 60)}`;
}

function durata(secondi) {
  if (secondi === 0) return "0 min";
  if (secondi < 60) return `${secondi} s`;
  const minuti = Math.round(secondi / 60);
  return minuti < 60 ? `${minuti} min` : `${Math.floor(minuti / 60)} h ${due(minuti % 60)}`;
}

const chiaveData = (d) => `${d.getFullYear()}-${due(d.getMonth() + 1)}-${due(d.getDate())}`;
const daChiave = (k) => { const [a, m, g] = k.split("-").map(Number); return new Date(a, m - 1, g); };
const piuGiorni = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const lunediDi = (d) => piuGiorni(d, -((d.getDay() + 6) % 7));
const limita = (x, min, max) => Math.min(max, Math.max(min, x));
const maiuscola = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function elemento(tag, testo, classe) {
  const e = document.createElement(tag);
  if (testo !== undefined) e.textContent = testo;
  if (classe) e.className = classe;
  return e;
}

function pulsante(testo, azione, classe) {
  const b = elemento("button", testo, classe);
  b.type = "button";
  b.addEventListener("click", (e) => { e.stopPropagation(); prova(azione); });
  return b;
}

const CESTINO = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" '
  + 'd="M9 3h6l1 2h4v2H4V5h4l1-2zm-3 6h12l-1 12H7L6 9zm4 2v8h2v-8h-2zm4 0v8h2v-8h-2z"/></svg>';

function cestino(etichetta, azione) {
  const b = pulsante("", azione, "cestino");
  b.innerHTML = CESTINO;
  b.setAttribute("aria-label", etichetta);
  return b;
}

/**
 * Finestra di dialogo. Con ``campo`` mostra una casella di testo e restituisce
 * cio' che si e' scritto; altrimenti il valore della scelta. Chiusa: null.
 */
function chiedi(testo, scelte, campo) {
  return new Promise((risolvi) => {
    const dialogo = $("#dialogo");
    const casella = $("#dialogo-campo");
    $("#dialogo-testo").textContent = testo;
    casella.hidden = campo === undefined;
    casella.value = campo ?? "";
    $("#dialogo-scelte").replaceChildren(...scelte.map((s) => {
      const b = elemento("button", s.testo, s.classe);
      b.type = s.classe === "primario" ? "submit" : "button";     // Invio = scelta principale
      b.addEventListener("click", () => {
        risolvi(campo === undefined || !s.valore ? s.valore : casella.value);
        dialogo.close();
      });
      return b;
    }));
    dialogo.addEventListener("close", () => risolvi(null), { once: true });
    dialogo.showModal();
    if (campo !== undefined) casella.select();
  });
}

const conferma = (testo) => chiedi(testo, [
  { testo: "Annulla", valore: false },
  { testo: "Elimina", valore: true, classe: "primario" },
]);

const chiediNome = (testo, attuale = "") => chiedi(testo, [
  { testo: "Annulla", valore: null },
  { testo: "Salva", valore: true, classe: "primario" },
], attuale);

// --- Schede ------------------------------------------------------------------

document.querySelectorAll(".scheda").forEach((scheda) => scheda.addEventListener("click", () => {
  document.querySelectorAll(".scheda").forEach((s) => {
    s.classList.toggle("attiva", s === scheda);
    if (s === scheda) s.setAttribute("aria-current", "page");
    else s.removeAttribute("aria-current");
  });
  document.querySelectorAll(".schermata").forEach((s) => { s.hidden = s.id !== scheda.dataset.scheda; });
  if (scheda.dataset.scheda === "progressi") prova(caricaProgressi);
}));

// --- Suono -------------------------------------------------------------------
// I browser permettono l'audio solo dopo un gesto dell'utente: il contesto
// audio si prepara al primo clic o tasto.

let audio = null;

function preparaAudio() {
  audio ??= new AudioContext();
  if (audio.state === "suspended") audio.resume();
}
document.addEventListener("pointerdown", preparaAudio);
document.addEventListener("keydown", preparaAudio);

/** Notifica di sistema allo scadere, utile se la scheda non e' in primo piano. */
function notifica(testo) {
  if (!("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
  new Notification("FlowStudy", { body: testo, icon: "/static/icona.png" });
}

/** Il permesso per le notifiche si chiede una volta, quando si avvia il primo timer. */
function chiediPermessoNotifiche() {
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
}

function suona() {
  if (!audio) return;
  const t = audio.currentTime;
  for (const ritardo of [0, 0.35, 0.7]) {
    const oscillatore = audio.createOscillator();
    const volume = audio.createGain();
    oscillatore.frequency.value = 880;
    volume.gain.setValueAtTime(0.0001, t + ritardo);
    volume.gain.exponentialRampToValueAtTime(0.3, t + ritardo + 0.02);
    volume.gain.exponentialRampToValueAtTime(0.0001, t + ritardo + 0.25);
    oscillatore.connect(volume).connect(audio.destination);
    oscillatore.start(t + ritardo);
    oscillatore.stop(t + ritardo + 0.3);
  }
}

// --- Pomodoro ----------------------------------------------------------------
// Il pomodoro e' visto di fronte, come un timer da cucina: la fascia con i
// minuti e' un tamburo che gira, e sotto l'indice c'e' il tempo che resta.

const LARGHEZZA = 391;    // larghezza del disegno (viewBox)
const CENTRO = 195;       // asse verticale del pomodoro, dove sta l'indice
const PASSO = 9;          // gradi di tamburo fra un minuto e il successivo
const RAGGIO = 180;       // raggio del tamburo, in unita' del disegno
const FASCIA = 343;       // altezza della fascia scura su cui poggiano le tacche
const PIXEL_PER_MINUTO = RAGGIO * Math.sin((PASSO * Math.PI) / 180);

function disegnaTamburo(minuti) {
  const tacche = [];
  for (let m = Math.max(0, Math.floor(minuti - 10)); m <= minuti + 10; m++) {
    const angolo = ((m - minuti) * PASSO * Math.PI) / 180;
    const profondita = Math.cos(angolo);             // 1 davanti, 0 sul bordo
    if (profondita < 0.05) continue;
    const x = CENTRO + RAGGIO * Math.sin(angolo);
    const lunga = m % 5 === 0;
    const tacca = document.createElementNS(NS, "rect");
    const larghezza = (lunga ? 6 : 4) * profondita;
    const altezza = lunga ? 30 : 15;
    tacca.setAttribute("x", x - larghezza / 2);
    tacca.setAttribute("y", FASCIA - altezza);
    tacca.setAttribute("width", larghezza);
    tacca.setAttribute("height", altezza);
    tacca.setAttribute("rx", 2);
    tacca.setAttribute("fill", "#fff");
    tacca.setAttribute("opacity", 0.3 + 0.7 * profondita);
    tacche.push(tacca);
    if (lunga) {
      const cifra = document.createElementNS(NS, "text");
      cifra.textContent = m;
      cifra.setAttribute("class", "cifra");
      cifra.setAttribute("text-anchor", "middle");
      cifra.setAttribute("transform", `translate(${x} ${FASCIA - 42}) scale(${profondita} 1)`);
      cifra.setAttribute("opacity", 0.3 + 0.7 * profondita);
      tacche.push(cifra);
    }
  }
  $("#tamburo").replaceChildren(...tacche);
}

/** Secondi alla prossima scadenza, contati in locale fra una risposta e l'altra. */
function restanti() {
  const t = stato.timer;
  if (t.secondi_rimanenti == null) return null;
  return t.secondi_rimanenti - (Date.now() - t.ricevuto) / 1000;
}

const nomeMateria = (id) => stato.materie.find((m) => m.id === id)?.nome ?? "";
const ghieraLibera = () => !stato.timer.attivo && stato.impostazioni?.modalita === "statica";

function disegnaTimer() {
  const t = stato.timer;
  let secondi;
  let etichetta;
  if (!t.attivo) {
    const statica = stato.impostazioni.modalita === "statica";
    secondi = statica ? stato.minutiGhiera * 60 : 0;
    etichetta = statica ? "Scorri il pomodoro per scegliere i minuti" : "Studia quanto vuoi: la pausa cresce con lo studio";
  } else if (t.stato === "pronto") {
    secondi = 0;
    etichetta = "Pausa finita: si riparte?";
  } else if (t.stato === "studio" && t.secondi_rimanenti == null) {
    secondi = (Date.now() - Date.parse(t.inizio_sessione)) / 1000;    // dinamica: tempo studiato
    etichetta = `Studio · ${nomeMateria(t.materia_id)}`;
  } else {
    secondi = restanti();
    etichetta = t.stato === "studio" ? `Studio · ${nomeMateria(t.materia_id)}` : "Pausa";
  }
  $("#tempo").textContent = cronometro(secondi);
  $("#etichetta").textContent = etichetta;
  // In modalita' dinamica si vede quanta pausa si e' gia' guadagnata (la calcola il server).
  const maturata = $("#maturata");
  maturata.hidden = t.pausa_maturata_s == null;
  if (!maturata.hidden) maturata.textContent = `☕ Pausa maturata ${cronometro(t.pausa_maturata_s)}`;
  // Il tempo anche nel titolo della scheda, per vederlo da un'altra scheda.
  const inCorso = t.attivo && (t.stato === "studio" || t.stato === "pausa");
  document.title = inCorso ? `(${cronometro(secondi)}) ${t.stato === "pausa" ? "Pausa · " : ""}FlowStudy` : "FlowStudy";
  disegnaTamburo(Math.max(0, secondi) / 60);
  const pomodoro = $("#pomodoro");
  pomodoro.classList.toggle("regolabile", ghieraLibera());
  // In pausa il pomodoro diventa verde: il cambio di stato si vede a colpo d'occhio.
  $(".timer").classList.toggle("in-pausa", t.attivo && t.stato === "pausa");
  pomodoro.setAttribute("aria-valuenow", Math.round(Math.max(0, secondi) / 60));
}

function disegnaComandi() {
  const t = stato.timer;
  // I pulsanti si ridisegnano solo se lo stato cambia: un clic non va perso
  // perche' il pulsante e' stato sostituito mentre lo si premeva.
  const chiave = t.attivo ? t.stato : "nessuno";
  if (chiave === disegnaComandi.ultima) return;
  disegnaComandi.ultima = chiave;
  const comandi = [];
  if (!t.attivo) comandi.push(pulsante("Avvia", avviaNuovoTimer, "primario"));
  else if (t.stato === "pronto") comandi.push(pulsante("Avvia", () => evento("avvia"), "primario"));
  else if (t.stato === "studio") comandi.push(pulsante("Pausa", () => evento("pausa"), "primario"));
  else comandi.push(pulsante("Riprendi", () => evento("riprendi"), "primario"));
  if (t.attivo) comandi.push(pulsante("Termina", terminaConConferma));
  $("#comandi").replaceChildren(...comandi);
  $("#materia").disabled = t.attivo;
  $("#nuova-materia").disabled = t.attivo;
  disegnaInterruttore();
}

/** "Termina" e' accanto a "Pausa": si chiede conferma per evitare clic per sbaglio. */
async function terminaConConferma() {
  const scelta = await chiedi("Terminare il timer? La sessione in corso viene salvata.", [
    { testo: "Continua", valore: false },
    { testo: "Termina", valore: true, classe: "primario" },
  ]);
  if (scelta) await evento("termina");
}

// Interruttore Pomodoro / Flowtime nella Home: cambia la modalita' senza
// passare dalle Impostazioni. Non si usa mentre un timer e' attivo (RF7).
function disegnaInterruttore() {
  for (const b of document.querySelectorAll(".interruttore button")) {
    b.setAttribute("aria-pressed", b.dataset.modalita === stato.impostazioni?.modalita);
    b.disabled = stato.timer.attivo;
  }
}

document.querySelectorAll(".interruttore button").forEach((b) => b.addEventListener("click", () => prova(async () => {
  if (b.dataset.modalita === stato.impostazioni.modalita) return;
  stato.impostazioni = await api("PUT", "/impostazioni", { ...stato.impostazioni, modalita: b.dataset.modalita });
  compilaImpostazioni();
})));

function riceviTimer(timer) {
  timer.ricevuto = Date.now();
  stato.timer = timer;
  if (timer.attivo) $("#materia").value = timer.materia_id;
  if (timer.suona) {
    const messaggio = timer.stato === "pausa" ? "Tempo di studio finito: pausa!" : "La pausa è finita.";
    suona();
    notifica(messaggio);
    avvisa(messaggio);
    prova(caricaCalendario);
  }
  disegnaTimer();
  disegnaComandi();
}

async function avviaNuovoTimer() {
  const materia = Number($("#materia").value);
  if (!materia) throw new Error("Prima aggiungi una materia con il pulsante +.");
  chiediPermessoNotifiche();
  await api("POST", "/timer", { materia_id: materia });
  await evento("avvia");
}

async function evento(nome) {
  riceviTimer(await api("POST", `/timer/${nome}`));
  if (nome === "pausa" || nome === "termina") await caricaCalendario();
}

// Trascinando a sinistra il tamburo porta sotto l'indice minuti piu' alti,
// a destra minuti piu' bassi; lo stesso fanno le frecce e la rotella.
const pomodoro = $("#pomodoro");
let presa = null;

function cambiaMinuti(minuti) {
  stato.minutiGhiera = limita(Math.round(minuti), 1, 120);
  disegnaTimer();
  clearTimeout(salvaMinutiGhiera.attesa);
  salvaMinutiGhiera.attesa = setTimeout(() => prova(salvaMinutiGhiera), 600);
}

pomodoro.addEventListener("pointerdown", (e) => {
  if (!ghieraLibera()) return;
  presa = { x: e.clientX, minuti: stato.minutiGhiera };
  pomodoro.setPointerCapture(e.pointerId);
});
pomodoro.addEventListener("pointermove", (e) => {
  if (!presa) return;
  const spostamento = ((e.clientX - presa.x) / pomodoro.getBoundingClientRect().width) * LARGHEZZA;
  cambiaMinuti(presa.minuti - spostamento / PIXEL_PER_MINUTO);
});
pomodoro.addEventListener("pointerup", () => { presa = null; });
pomodoro.addEventListener("wheel", (e) => {
  if (!ghieraLibera()) return;
  e.preventDefault();
  cambiaMinuti(stato.minutiGhiera + Math.sign(e.deltaX || e.deltaY));
}, { passive: false });
pomodoro.addEventListener("keydown", (e) => {
  const passo = { ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1 }[e.key];
  if (!passo || !ghieraLibera()) return;
  e.preventDefault();
  cambiaMinuti(stato.minutiGhiera + passo);
});

async function salvaMinutiGhiera() {
  if (stato.minutiGhiera === stato.impostazioni.studio_min) return;
  stato.impostazioni = await api("PUT", "/impostazioni", { ...stato.impostazioni, studio_min: stato.minutiGhiera });
  compilaImpostazioni();
}

$("#nuova-materia").addEventListener("click", () => prova(async () => {
  const nome = await chiediNome("Nuova materia");
  if (!nome) return;
  const materia = await api("POST", "/materie", { nome });
  await caricaMaterie();
  $("#materia").value = materia.id;
  ricordaMateria(materia.id);
  avvisa(`Materia aggiunta: ${materia.nome}`);
}));

// --- Calendario --------------------------------------------------------------
// Chiuso mostra la settimana; toccando il titolo si apre sul mese intero.
// Sotto ci sono le sessioni: le ultime giornate di studio, o quelle del
// giorno scelto.

async function caricaCalendario() {
  stato.statistiche = await api("GET", "/statistiche");
  stato.calendario.riferimento ??= daChiave(stato.statistiche.oggi);
  disegnaOggiHome();
  disegnaCalendario();
  await disegnaSessioni();
}

/** Sotto il timer: quanto si e' studiato oggi rispetto all'obiettivo. */
function disegnaOggiHome() {
  const s = stato.statistiche;
  const obiettivo = s.obiettivo_min * 60;
  $("#home-barra").style.width = `${limita((s.studio_oggi_s / obiettivo) * 100, 0, 100)}%`;
  $("#home-oggi").textContent = s.studio_oggi_s >= obiettivo
    ? `Oggi ${durata(s.studio_oggi_s)}: obiettivo raggiunto 🌿`
    : `Oggi ${durata(s.studio_oggi_s)} di ${s.obiettivo_min} min`;
}

function cellaGiorno(data) {
  const s = stato.statistiche;
  const chiave = chiaveData(data);
  const secondi = s.per_giorno[chiave] ?? 0;
  const raggiunto = secondi >= s.obiettivo_min * 60;
  const cella = pulsante(String(data.getDate()), () => scegliGiorno(chiave), "giorno-cal");
  cella.classList.toggle("oggi", chiave === s.oggi);
  cella.classList.toggle("studio", secondi > 0);
  cella.classList.toggle("raggiunto", raggiunto);
  cella.classList.toggle("scelto", chiave === stato.giornoScelto);
  const descrizione = secondi ? `${durata(secondi)}${raggiunto ? ", obiettivo raggiunto" : ""}` : "nessuno studio";
  cella.setAttribute("aria-label", `${data.toLocaleDateString("it-IT", { day: "numeric", month: "long" })}: ${descrizione}`);
  return cella;
}

function disegnaCalendario() {
  const { riferimento, espanso } = stato.calendario;
  const titolo = $("#mese-titolo");
  titolo.textContent = maiuscola(riferimento.toLocaleDateString("it-IT", { month: "long", year: "numeric" }));
  titolo.setAttribute("aria-expanded", espanso);
  const celle = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"].map((g) => elemento("span", g, "intestazione"));
  if (espanso) {
    const primo = new Date(riferimento.getFullYear(), riferimento.getMonth(), 1);
    for (let i = 0; i < (primo.getDay() + 6) % 7; i++) celle.push(elemento("span"));
    const giorni = new Date(primo.getFullYear(), primo.getMonth() + 1, 0).getDate();
    for (let g = 1; g <= giorni; g++) celle.push(cellaGiorno(new Date(primo.getFullYear(), primo.getMonth(), g)));
  } else {
    const lunedi = lunediDi(riferimento);
    for (let i = 0; i < 7; i++) celle.push(cellaGiorno(piuGiorni(lunedi, i)));
  }
  const calendario = $("#calendario");
  calendario.classList.toggle("espanso", espanso);
  calendario.replaceChildren(...celle);
}

$("#mese-titolo").addEventListener("click", () => {
  stato.calendario.espanso = !stato.calendario.espanso;
  disegnaCalendario();
});

function sposta(verso) {
  const c = stato.calendario;
  c.riferimento = c.espanso
    ? new Date(c.riferimento.getFullYear(), c.riferimento.getMonth() + verso, 1)
    : piuGiorni(c.riferimento, 7 * verso);
  disegnaCalendario();
}
$("#mese-prima").addEventListener("click", () => sposta(-1));
$("#mese-dopo").addEventListener("click", () => sposta(1));

async function scegliGiorno(chiave) {
  stato.giornoScelto = stato.giornoScelto === chiave ? null : chiave;
  disegnaCalendario();
  await disegnaSessioni();
}

function quantoFa(chiave) {
  const giorni = Math.round((daChiave(stato.statistiche.oggi) - daChiave(chiave)) / 86400000);
  return giorni === 0 ? "oggi" : giorni === 1 ? "ieri" : `${giorni} giorni fa`;
}

/** Una riga della linea del tempo: data a sinistra, pallino, testo, cestino. */
function rigaTempo(sopra, sotto, titolo, dettaglio, eliminazione, scelta) {
  const riga = elemento("li", undefined, "tappa");
  const quando = elemento("div", undefined, "quando");
  quando.append(elemento("b", sopra), elemento("span", sotto));
  const testo = elemento("div", undefined, "cosa");
  testo.append(titolo, elemento("span", dettaglio));
  riga.append(quando, elemento("span", undefined, "pallino"), testo, eliminazione);
  if (scelta) {
    riga.classList.add("cliccabile");
    riga.addEventListener("click", () => prova(scelta));
  }
  return riga;
}

async function disegnaSessioni() {
  const s = stato.statistiche;
  const contenitore = $("#sessioni");
  const elenco = elemento("ul", undefined, "linea-tempo");

  if (stato.giornoScelto) {
    const chiave = stato.giornoScelto;
    const data = daChiave(chiave).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
    const sessioni = await api("GET", `/sessioni?giorno=${chiave}`);
    for (const sessione of sessioni) {
      const inizio = ORA.format(new Date(sessione.inizio));
      const orario = `${inizio}–${ORA.format(new Date(sessione.fine))}`;
      elenco.append(rigaTempo(inizio, "", elemento("b", sessione.materia),
        `${durata(sessione.durata_s)} · ${orario}`,
        cestino("Elimina sessione", async () => {
          if (!(await conferma(`Eliminare la sessione di ${sessione.materia} (${orario})?`))) return;
          await api("DELETE", `/sessioni/${sessione.id}`);
          await caricaCalendario();
        })));
    }
    const azioni = elemento("div", undefined, "azioni-giorno");
    azioni.append(pulsante("‹ Tutte le giornate", () => scegliGiorno(chiave), "testo"));
    if (sessioni.length) {
      azioni.append(pulsante("Elimina la giornata", async () => {
        if (!(await conferma(`Eliminare tutte le sessioni di ${data}?`))) return;
        const { eliminate } = await api("DELETE", `/giorni/${chiave}`);
        avvisa(`Sessioni eliminate: ${eliminate}`);
        await caricaCalendario();
      }, "testo pericolo"));
    }
    contenitore.replaceChildren(elemento("h3", maiuscola(data), "titolo-giorno"),
      sessioni.length ? elenco : elemento("p", "Nessuna sessione in questo giorno.", "nota"), azioni);
    return;
  }

  const giorni = Object.keys(s.per_giorno).sort().reverse().slice(0, 10);
  for (const chiave of giorni) {
    const secondi = s.per_giorno[chiave];
    const raggiunto = secondi >= s.obiettivo_min * 60;
    const data = daChiave(chiave);
    // Tono "zen": niente giudizi, solo una pianta che cresce (🌱 in crescita, 🌿 obiettivo).
    const titolo = elemento("b", maiuscola(data.toLocaleDateString("it-IT", { weekday: "long" })));
    const icona = elemento("span", raggiunto ? " 🌿" : " 🌱");
    icona.title = raggiunto ? "Obiettivo raggiunto" : "In crescita";
    titolo.append(icona);
    elenco.append(rigaTempo(
      data.toLocaleDateString("it-IT", { day: "numeric", month: "short" }), quantoFa(chiave), titolo,
      `${durata(secondi)} di studio · obiettivo ${s.obiettivo_min} min`,
      cestino("Elimina la giornata", async () => {
        if (!(await conferma(`Eliminare tutte le sessioni del ${data.toLocaleDateString("it-IT")}?`))) return;
        await api("DELETE", `/giorni/${chiave}`);
        await caricaCalendario();
      }),
      () => scegliGiorno(chiave)));
  }
  contenitore.replaceChildren(giorni.length ? elenco
    : elemento("p", "Ancora nessuna sessione: scegli una materia e avvia il timer.", "nota"));
}

// --- Progressi ---------------------------------------------------------------

async function caricaProgressi() {
  const s = (stato.statistiche = await api("GET", "/statistiche"));
  const [indice, nome, descrizione] = STADI[s.bonsai];
  document.querySelectorAll("#bonsai g[data-stadi]").forEach((g) => {
    g.style.opacity = g.dataset.stadi.split(" ").includes(String(indice)) ? 1 : 0;
  });
  $("#stadio").textContent = nome;
  $("#stadio-testo").textContent = descrizione;
  const k = s.giorni_bonsai;
  const giorni = k === 1 ? "1 giorno" : `${k} giorni`;
  $("#bonsai-barra").style.width = `${s.soglia_prossima ? (k / s.soglia_prossima) * 100 : 100}%`;
  $("#bonsai-conta").textContent = s.soglia_prossima
    ? `${giorni} con l'obiettivo negli ultimi 30 · ne ${s.soglia_prossima - k === 1 ? "manca 1" : `mancano ${s.soglia_prossima - k}`} per diventare ${Object.values(STADI)[indice + 1][1].toLowerCase()}`
    : `${giorni} con l'obiettivo negli ultimi 30: più di così non cresce!`;

  const percentuale = limita((s.studio_oggi_s / (s.obiettivo_min * 60)) * 100, 0, 100);
  $("#oggi-minuti").textContent = durata(s.studio_oggi_s);
  const anello = $("#oggi-anello");
  anello.style.strokeDasharray = `${percentuale} 100`;
  anello.style.opacity = percentuale > 0 ? 1 : 0;     // a zero l'estremo arrotondato sembrerebbe un punto
  $("#oggi-obiettivo").textContent = percentuale >= 100 ? "obiettivo raggiunto!" : `di ${s.obiettivo_min} min`;
  $("#serie").textContent = s.serie;
  $("#serie-testo").textContent = s.serie === 1 ? "giorno di fila" : "giorni di fila";

  const lunedi = lunediDi(daChiave(s.oggi));
  const settimane = Array.from({ length: 8 }, (_, i) => piuGiorni(lunedi, -7 * (7 - i)));
  const valori = settimane.map((d) => s.per_settimana[chiaveData(d)] ?? 0);
  const obiettivo = s.obiettivo_min * 60 * 7;
  const massimo = Math.max(...valori, obiettivo);
  $("#settimane").replaceChildren(...settimane.map((d, i) => {
    const colonna = elemento("div", undefined, "colonna");
    const area = elemento("div", undefined, "area");
    const pieno = elemento("div", undefined, !valori[i] ? "pieno vuoto" : valori[i] >= obiettivo ? "pieno" : "pieno parziale");
    pieno.style.height = `${(valori[i] / massimo) * 100}%`;
    const linea = elemento("span", undefined, "linea-obiettivo");
    linea.style.bottom = `${(obiettivo / massimo) * 100}%`;
    area.append(pieno, linea);
    colonna.append(area, elemento("span", valori[i] ? durata(valori[i]) : "", "valore"),
      elemento("span", `${d.getDate()}/${d.getMonth() + 1}`, "data"));
    return colonna;
  }));
  $("#settimane-obiettivo").textContent = `Obiettivo della settimana: ${durata(obiettivo)}`;
  await caricaPerMateria();
}

async function caricaPerMateria() {
  const al = stato.statistiche.oggi;
  const dal = chiaveData(piuGiorni(daChiave(al), 1 - Number($("#periodo").value)));
  const righe = await api("GET", `/statistiche/materie?dal=${dal}&al=${al}`);
  const massimo = Math.max(...righe.map((r) => r.secondi), 1);
  const totale = righe.reduce((somma, r) => somma + r.secondi, 0);
  $("#per-materia").replaceChildren(...(righe.length ? righe.map((r) => {
    const riga = elemento("div", undefined, "riga-materia");
    const barra = elemento("div", undefined, "barra");
    const pieno = elemento("div");
    pieno.style.width = `${(r.secondi / massimo) * 100}%`;
    barra.append(pieno);
    const quota = elemento("span", durata(r.secondi));
    quota.append(elemento("small", ` · ${Math.round((r.secondi / totale) * 100)}%`));
    riga.append(elemento("span", r.materia), quota, barra);
    return riga;
  }) : [elemento("p", "Nessuno studio in questo periodo.", "nota")]));
}
$("#periodo").addEventListener("change", () => prova(caricaPerMateria));

// --- Impostazioni ------------------------------------------------------------

const modulo = $("#form-impostazioni");

function compilaImpostazioni() {
  const i = stato.impostazioni;
  modulo.nome.value = i.nome;
  modulo.obiettivo_min.value = i.obiettivo_min;
  modulo.modalita.value = i.modalita;
  modulo.studio_min.value = i.studio_min;
  modulo.pausa_min.value = i.pausa_min;
  aggiornaCampiPausa();
  disegnaInterruttore();
  $("#saluto").textContent = i.nome ? `Ciao, ${i.nome}!` : "";
  stato.minutiGhiera = i.studio_min;
  disegnaTimer();
}

const SPIEGAZIONI = {
  statica: "Scegli tu quanto studiare e quanto riposare; il timer suona alla fine di ognuno.",
  dinamica: "Studi finché sei concentrato; la pausa cresce con lo studio: 1 minuto ogni 5, al massimo 30.",
};

function aggiornaCampiPausa() {
  const dinamica = modulo.modalita.value === "dinamica";
  // I campi nascosti si disattivano anche, cosi' il browser non li controlla.
  for (const campo of document.querySelectorAll(".solo-statica")) campo.hidden = dinamica;
  modulo.studio_min.disabled = dinamica;
  modulo.pausa_min.disabled = dinamica;
  $("#spiega-modalita").textContent = SPIEGAZIONI[modulo.modalita.value];
}
modulo.addEventListener("change", aggiornaCampiPausa);

modulo.addEventListener("submit", (e) => {
  e.preventDefault();
  prova(async () => {
    stato.impostazioni = await api("PUT", "/impostazioni", {
      nome: modulo.nome.value.trim(),
      obiettivo_min: Number(modulo.obiettivo_min.value),
      modalita: modulo.modalita.value,
      studio_min: Number(modulo.studio_min.value),
      pausa_min: Number(modulo.pausa_min.value),
    });
    compilaImpostazioni();
    avvisa("Impostazioni salvate.");
    await caricaCalendario();
  });
});

function ricordaMateria(id) {
  try { localStorage.setItem("materia", id); } catch { /* memoria non disponibile */ }
}

async function caricaMaterie() {
  stato.materie = await api("GET", "/materie");
  const scelta = $("#materia");
  let ricordata = scelta.value;
  try { ricordata ||= localStorage.getItem("materia") ?? ""; } catch { /* memoria non disponibile */ }
  scelta.replaceChildren(...(stato.materie.length
    ? stato.materie.map((m) => new Option(m.nome, m.id))
    : [new Option("Nessuna materia", "")]));
  if (stato.materie.some((m) => String(m.id) === ricordata)) scelta.value = ricordata;
  if (stato.timer.attivo) scelta.value = stato.timer.materia_id;

  $("#elenco-materie").replaceChildren(...(stato.materie.length ? stato.materie.map((m) => {
    const riga = elemento("li");
    riga.append(elemento("span", m.nome),
      pulsante("Rinomina", async () => {
        const nome = await chiediNome("Nuovo nome della materia", m.nome);
        if (!nome) return;
        await api("PATCH", `/materie/${m.id}`, { nome });
        await caricaMaterie();
      }),
      pulsante("Elimina", async () => {
        const decisione = await chiedi(`Eliminare "${m.nome}"? Cosa vuoi fare delle sue sessioni?`, [
          { testo: "Annulla", valore: null },
          { testo: "Tienile", valore: "tieni" },
          { testo: "Eliminale", valore: "elimina", classe: "primario" },
        ]);
        if (!decisione) return;
        await api("DELETE", `/materie/${m.id}?conserva_sessioni=${decisione === "tieni"}`);
        avvisa(decisione === "tieni" ? "Materia archiviata: le sue ore restano nelle statistiche." : "Materia eliminata.");
        await caricaMaterie();
        await caricaCalendario();
      }, "pericolo"));
    return riga;
  }) : [elemento("li", "Ancora nessuna materia.", "nota")]));
}

$("#materia").addEventListener("change", (e) => ricordaMateria(e.target.value));

$("#form-materia").addEventListener("submit", (e) => {
  e.preventDefault();
  prova(async () => {
    const campo = e.target.nome;
    const materia = await api("POST", "/materie", { nome: campo.value });
    campo.value = "";
    await caricaMaterie();
    avvisa(`Materia aggiunta: ${materia.nome}`);
  });
});

// --- Avvio -------------------------------------------------------------------

let battiti = 0;

function battito() {
  if (!stato.timer.attivo) return;
  disegnaTimer();
  const r = restanti();
  // Ogni 5 secondi, o allo scadere, si chiede al server lo stato vero. In
  // Flowtime ogni secondo, cosi' la pausa maturata cresce sotto gli occhi.
  const flowtime = stato.timer.pausa_maturata_s != null;
  if (flowtime || ++battiti % 5 === 0 || (r !== null && r <= 0)) {
    prova(async () => riceviTimer(await api("GET", "/timer")));
  }
}

prova(async () => {
  stato.impostazioni = await api("GET", "/impostazioni");
  compilaImpostazioni();
  await caricaMaterie();
  riceviTimer(await api("GET", "/timer"));
  await caricaCalendario();
  setInterval(battito, 1000);
});
