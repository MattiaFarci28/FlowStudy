# Specifica algebrica del registro delle sessioni

Il **registro** è l'insieme delle sessioni salvate. La specifica descrive, solo
attraverso assiomi, quanto si è studiato in un giorno (RF16) e cosa succede
eliminando una giornata (RF15).

## Segnatura

```
tipo  Registro
usa   Sessione, Giorno, Nat

costruttori
    vuoto          :                     -> Registro
    aggiungi       : Registro x Sessione -> Registro

operazioni
    studio         : Registro x Giorno   -> Nat
    elimina_giorno : Registro x Giorno   -> Registro

ausiliaria (definita su Sessione)
    quota          : Sessione x Giorno   -> Nat
        secondi della sessione che cadono nel giorno
```

## Assiomi

Per ogni `r : Registro`, `s : Sessione`, `g : Giorno`:

```
[A1] studio(vuoto, g) = 0
[A2] studio(aggiungi(r, s), g) = studio(r, g) + quota(s, g)

[A3] elimina_giorno(vuoto, g) = vuoto
[A4] elimina_giorno(aggiungi(r, s), g) =
         if quota(s, g) > 0
         then elimina_giorno(r, g)
         else aggiungi(elimina_giorno(r, g), s)
```

Gli assiomi coprono ogni operazione applicata a ogni costruttore, quindi la
specifica è **completa**: `studio` ed `elimina_giorno` sono definite su
qualunque registro.

## Teoremi

**T1 — Dopo aver eliminato una giornata, lo studio di quel giorno è zero.**

```
studio(elimina_giorno(r, g), g) = 0
```

Dimostrazione per induzione strutturale su `r`.

- *Base*, `r = vuoto`:
  `studio(elimina_giorno(vuoto, g), g)` =[A3] `studio(vuoto, g)` =[A1] `0`.
- *Passo*, `r = aggiungi(r', s)`, supponendo T1 vero per `r'`:
  - se `quota(s, g) > 0`:
    `studio(elimina_giorno(aggiungi(r', s), g), g)` =[A4]
    `studio(elimina_giorno(r', g), g)` = `0` per ipotesi induttiva;
  - se `quota(s, g) = 0`:
    `studio(elimina_giorno(aggiungi(r', s), g), g)` =[A4]
    `studio(aggiungi(elimina_giorno(r', g), s), g)` =[A2]
    `studio(elimina_giorno(r', g), g) + quota(s, g)` = `0 + 0` = `0`. ∎

**T2 — L'ordine in cui si aggiungono le sessioni non conta.**

```
studio(aggiungi(aggiungi(r, s1), s2), g) = studio(aggiungi(aggiungi(r, s2), s1), g)
```

Applicando due volte [A2] entrambi i membri diventano
`studio(r, g) + quota(s1, g) + quota(s2, g)`, e la somma è commutativa. ∎

## Corrispondenza con il codice

| Specifica | `src/domain.py` |
|---|---|
| `Registro` | lista di `Sessione` |
| `vuoto` | `[]` |
| `aggiungi(r, s)` | `r + [s]` |
| `quota(s, g)` | `ripartisci_per_giorno(s).get(g, 0)` |
| `studio(r, g)` | `studio_per_giorno(r).get(g, 0)` |
| `elimina_giorno(r, g)` | `r` senza le sessioni di `sessioni_del_giorno(r, g)` |

Assiomi e teoremi diventano **proprietà** da verificare con il property-based
testing: su registri e giorni generati a caso, il codice deve rispettarli.
