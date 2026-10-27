# Requisiti di FlowStudy

## In breve

FlowStudy è un timer per lo studio. Si sceglie la materia, si avvia il timer e si studia; quando ci si ferma, l'app concede una pausa e poi si riparte. Ogni tratto di studio viene salvato, e da lì l'app ricava quanto si è studiato ogni giorno, ogni settimana e per ogni materia.

Per restare motivati si può fissare un obiettivo di minuti al giorno: i giorni di fila in cui lo si raggiunge formano la **serie**, e un **bonsai** cresce man mano che si è costanti.

**Un pomeriggio con FlowStudy.** Si sceglie "Analisi 2" e si avvia il timer alle 15:00. Alle 15:50 ci si ferma: l'app salva 50 minuti di studio e concede 10 minuti di pausa. Alle 16:00 suona la fine della pausa, si riparte e si studia fino alle 17:10, poi si termina. Totale della giornata: 2 ore. Con un obiettivo di 120 minuti, la giornata conta per la serie e il bonsai cresce.

## Le tre schermate

- **Home.** Al centro c'è un pomodoro da cucina: lo si gira per impostare il tempo, si avvia e suona quando il tempo scade. Sotto c'è un **calendario** del mese con i giorni di studio evidenziati; toccando un giorno si vede cosa si è studiato e per quanto, e da lì si possono eliminare una sessione o l'intera giornata.
- **Progressi.** Il bonsai, la serie e tutte le statistiche: tempo di studio per giorno, per settimana e per materia.
- **Impostazioni.** Il profilo, l'obiettivo giornaliero, la modalità della pausa, le materie e il download dei dati.

## Le parole che usiamo

| Parola | Cosa vuol dire |
|---|---|
| **Materia** | Quello che si sta studiando, per esempio "Analisi 2". |
| **Timer** | Il cronometro con cui si studia una materia, da quando lo si avvia a quando lo si termina. |
| **Sessione** | Un tratto di studio **senza interruzioni**. Ogni pausa chiude una sessione e la ripresa ne apre una nuova: nell'esempio sopra le sessioni sono due, 15:00–15:50 e 16:00–17:10. |
| **Pausa spettante** | Quanto può durare la pausa dopo una sessione. |
| **Giorno** | Un giorno di calendario secondo l'ora italiana, dalle 00:00:00 alle 23:59:59. |
| **Obiettivo** | I minuti di studio da fare ogni giorno. |
| **Serie** | Quanti giorni di fila si è raggiunto l'obiettivo. |
| **Bonsai** | Una pianta che cresce se si studia con costanza e appassisce piano piano se si smette. |

## Requisiti funzionali

Descrivono cosa fa l'app, cioè cosa si può fare usandola.

### Materie

- **RF1 — Creare una materia.** Basta darle un nome da 1 a 50 caratteri (gli spazi all'inizio e alla fine non contano). Non ci possono essere due materie con lo stesso nome, neanche se cambiano solo maiuscole e minuscole: "analisi" e "Analisi" sono la stessa materia. Se si ricrea una materia archiviata (vedi RF4), l'app la riattiva con tutte le sue sessioni invece di crearne una nuova.
- **RF2 — Vedere le materie.** L'elenco mostra le materie in ordine alfabetico, tranne quelle archiviate.
- **RF3 — Rinominare una materia.** Il nuovo nome segue le regole di RF1 e non può essere quello di un'altra materia, neanche archiviata. Le sessioni già fatte restano collegate alla materia e mostrano il nome nuovo.
- **RF4 — Eliminare una materia.** L'app chiede conferma e fa scegliere cosa fare delle sue sessioni:
  - **eliminarle**: spariscono la materia e tutte le sue sessioni;
  - **tenerle**: la materia viene **archiviata**. Non compare più nell'elenco e non si può usare per nuovi timer, ma le ore studiate restano nelle statistiche e nell'esportazione.

  Una materia non si può eliminare mentre il timer è in corso su di lei.

### Impostazioni

- **RF5 — Come funziona la pausa.** Le modalità sono due:
  - **statica**, come il metodo Pomodoro: si decide quanto studiare (da 1 a 120 minuti) e quanto riposare (da 1 a 60 minuti), e il timer suona alla fine di ognuno dei due. Di partenza sono 25 minuti di studio e 5 di pausa;
  - **dinamica**, come il metodo Flowtime: si studia quanto si vuole e la pausa la calcola l'app in base a quanto si è studiato (vedi RF10).
- **RF6 — Profilo e obiettivo.** Nel profilo si mette il nome con cui l'app saluta (fino a 30 caratteri, si può anche lasciare vuoto). L'obiettivo giornaliero va da 1 a 1440 minuti, cioè da un minuto a un giorno intero; di partenza è 120 minuti.
- **RF7 — Quando valgono le modifiche.** Le nuove impostazioni partono dal timer successivo. Un timer già avviato va avanti con le regole con cui è partito, così non cambia comportamento a metà.

### Timer

- **RF8 — Come si comporta il timer.** Il timer è sempre in uno di questi quattro stati:
  - **pronto**: aspetta che si inizi a studiare;
  - **studio**: si sta studiando e c'è una sessione aperta;
  - **pausa**: ci si sta riposando;
  - **concluso**: si è finito e il timer non si usa più.

  Ecco cosa lo fa passare da uno stato all'altro:

  | Da | Cosa succede | A |
  |---|---|---|
  | pronto | si preme "avvia" e si apre una sessione | studio |
  | studio | si preme "pausa" e la sessione si chiude | pausa |
  | studio | *solo in modalità statica:* finisce il tempo di studio, il timer suona e la sessione si chiude | pausa |
  | pausa | si preme "riprendi" e si apre una nuova sessione | studio |
  | pausa | finisce la pausa e il timer suona | pronto |
  | pronto, studio o pausa | si preme "termina" (se si stava studiando, la sessione si chiude) | concluso |

  Quello che non è in tabella non si può fare: per esempio non si può riprendere se si sta già studiando, e un timer concluso non si usa più. In questi casi l'app dà un errore e il timer resta com'era. Il disegno di questa tabella è in [02-statechart.md](02-statechart.md).
- **RF9 — Un timer alla volta.** Finché un timer non è concluso, non se ne può avviare un altro.
- **RF10 — Quanto dura la pausa.**
  - In modalità **statica** dura quanto impostato.
  - In modalità **dinamica** dura un quinto della sessione appena chiusa, e mai più di 30 minuti. Per esempio: 50 minuti di studio danno 10 minuti di pausa, 7 minuti danno 1 minuto e 24 secondi, 3 ore danno 30 minuti (il massimo).
- **RF11 — Riprendere prima.** La pausa si può interrompere quando si vuole per tornare a studiare. La pausa non usata non si mette da parte per dopo.
- **RF12 — Il timer non perde il conto.** L'app non conta i secondi uno a uno: si ricorda quando si è iniziato a studiare o a riposare e fa il conto con l'ora attuale. Così il tempo resta giusto anche se si chiude la pagina o il telefono va in standby.

### Sessioni

- **RF13 — Come nascono le sessioni.** Ogni sessione si ricorda la materia, quando è iniziata e quando è finita. Le crea **solo il timer**: non si possono aggiungere o modificare a mano, perché l'app deve registrare lo studio fatto davvero. Una sessione da zero secondi non viene salvata.
- **RF14 — Eliminare una sessione.** Si può cancellare una singola sessione, per esempio una fatta per sbaglio.
- **RF15 — Eliminare una giornata intera.** Dopo una conferma, l'app cancella tutte le sessioni che hanno anche solo un po' di studio in quel giorno; una sessione a cavallo della mezzanotte sparisce per intero. Alla fine quel giorno risulta senza studio.

### Statistiche

- **RF16 — Ogni minuto va al suo giorno.** Il tempo di una sessione viene contato nel giorno in cui è stato studiato davvero. Studiando dalle 23:00 alle 00:30, i primi 60 minuti vanno al primo giorno e gli altri 30 al giorno dopo.
- **RF17 — Quanto si è studiato.** L'app mostra il tempo di studio:
  - giorno per giorno, anche sul calendario della home, dove per ogni giorno si vedono le materie e i minuti;
  - settimana per settimana, da lunedì a domenica;
  - materia per materia, nel periodo che si sceglie.
- **RF18 — Obiettivo raggiunto.** Un giorno raggiunge l'obiettivo se quel giorno si è studiato almeno quanto l'obiettivo. Conta l'obiettivo impostato adesso: se lo si cambia, l'app ricalcola anche i giorni passati.
- **RF19 — La serie.** La serie conta i giorni di fila in cui si è raggiunto l'obiettivo, fino a ieri; se lo si è già raggiunto anche oggi, sale di uno. Oggi non interrompe mai la serie, perché la giornata non è ancora finita.
- **RF20 — Il bonsai.** Il bonsai cresce in base a quanti degli ultimi 30 giorni (oggi compreso) si è raggiunto l'obiettivo. Se si smette di studiare non torna subito a seme, ma regredisce un po' alla volta:

  | Giorni con l'obiettivo raggiunto | Bonsai |
  |---|---|
  | 0 | seme |
  | da 1 a 3 | germoglio |
  | da 4 a 9 | piantina |
  | da 10 a 19 | alberello |
  | da 20 a 30 | bonsai fiorito |

### Esportazione

- **RF21 — Scaricare i dati.** Si possono scaricare tutte le sessioni in un file CSV, che si apre anche con Excel: una riga per sessione con materia, inizio, fine e durata in secondi.

## Requisiti non funzionali

Non riguardano cosa fa l'app, ma come è costruita e con quali strumenti.

- **RNF1 — Architettura.** L'app è un servizio web con un'API REST che riceve e restituisce dati in JSON. I dati stanno in un database SQLite.
- **RNF2 — Tempo.** Le durate sono numeri interi di secondi. Gli istanti si salvano con il loro fuso orario e i giorni si calcolano sull'ora italiana, ora legale compresa.
- **RNF3 — Regole separate dal resto.** Le regole dell'app (pause, statistiche, serie, bonsai) stanno in un modulo che non guarda mai l'orologio e non tocca il database: l'ora attuale gli arriva come parametro. Così ogni regola si può provare in qualsiasi momento, anche a mezzanotte o la notte del cambio dell'ora.
- **RNF4 — Container.** Il servizio gira in un container Docker con Python 3.12.
- **RNF5 — Controlli automatici.** A ogni modifica pubblicata sul repository partono da soli i test, la misura della copertura e l'analisi statica del codice. Se va tutto bene, viene prodotta l'immagine del container.
- **RNF6 — Interfaccia.** L'interfaccia è una pagina web servita dallo stesso servizio, divisa nelle tre schermate descritte sopra. Il pomodoro e il bonsai sono disegnati in SVG.
