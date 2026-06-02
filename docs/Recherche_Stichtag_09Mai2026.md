# Recherche-Bündel — Stichtag 09. Mai 2026 (Anker-Datum)

> Zweck: Gesammelte Ergebnisse der Datenrecherche zum **fixen Anker-/Einstiegsdatum 09. Mai 2026**.
> Da der 09.05. ein Samstag ist, beziehen sich Kurse auf den nächstliegenden Handelstag **Fr, 08.05.2026**.
> Diese Datei dient als Referenz für zukünftige Chats/Sessions, damit der Recherchestand nicht verloren geht.
>
> Quellen: 1× Gemini-Report, 2× ChatGPT-Deep-Research-Reports. „GPT" = beide ChatGPT-Reports zu einer Spalte zusammengefasst.

---

## 1. Kurs-Vergleich (Kernergebnis)

Verglichen wird der **Kurs zum 09.05.2026** gegen unseren in der App hinterlegten Hardcoded-Anker (`GROUPS` in `index.html`).
✅ = mindestens 2 von 3 Quellen stimmen überein.

| Ticker | Claude (App-Anker) | GPT (beide Reports) | Gemini | 2/3 gleich? |
|--------|-------------------|---------------------|--------|:---:|
| **SXR8** | 675 € | 674,76 € | 794,51 € | ✅ |
| **CPXJ** | 203 € | 205,68 € *(≈242,68 USD)* | 243,03 € | ✅ |
| **CSKR** | 485 € | 522,00 GBp / – | 432,13 € *(502,81 USD)* | — |
| **IJPA** | 65 € | 66,90 € | 78,56 € | ✅ |
| **WHCS** | 8 $ | 7,26 $ / – | 7,31 $ | ✅ |
| **AGED** | 8 € | 9,89 $ / – | – | — |
| **PHAG** | 62 € | – | – | — |
| **PHPT** | 161 € | – | – | — |
| **COPA** | 46 € | – | – | — |
| **EIMI** | 44 € | 54,89 € *(eigtl. USD)* | 47,04 € *(54,74 USD)* | ✅ |
| **ALV** | 370 € | 369,10 € | 370,10 € | ✅ |
| **ISF** | 1007 GBp | 1005,00 GBp | – | ✅ |

**Ergebnis: 7 von 12 bestätigt** (SXR8, CPXJ, IJPA, WHCS, EIMI, ALV, ISF).

### Lesart-Hinweise
- **EIMI**: GPT „54,89 €" ist faktisch der **USD**-Wert (deckt sich mit Geminis 54,74 USD). In USD stimmen GPT & Gemini überein → ✅. App-Anker 44 € liegt darunter.
- **CPXJ**: GPT & Gemini nennen die Rohzahl ~242–243, aber in unterschiedlicher Währung (GPT-Lesart ≈ 205 € / Gemini direkt 243 €). App-Anker 203 € deckt sich mit GPTs EUR-Umrechnung → ✅; Gemini ist Ausreißer.
- **CSKR**: GPTs „522,00 GBp" sind Pence und für einen ~480-€-Anteil unplausibel.

---

## 2. Bewertung Hardcoded vs. real (nur bestätigte Werte)

### Differenz > 1 € — Nachschärfen sinnvoll
| Ticker | Hardcoded | Realer Wert (09.05.) | Differenz |
|--------|-----------|---------------------|:---:|
| **EIMI** | 44 € | ~47,04 € *(54,7 USD)* | ≈ 3,04 € |
| **CPXJ** | 203 € | ~205,68 € | ≈ 2,68 € |
| **IJPA** | 65 € | 66,90 € | ≈ 1,90 € |

### Differenz < 1 € — kann so bleiben
| Ticker | Hardcoded | Realer Wert | Differenz |
|--------|-----------|------------|:---:|
| **SXR8** | 675 € | 674,76 € | 0,24 € |
| **ALV** | 370 € | 369,10–370,10 € | < 1 € |
| **WHCS** | 8 $ | ~7,28 $ | ~0,7 $ |
| **ISF** | 1007 GBp | 1005 GBp | 2 GBp (≈ 0,02 £) |

### Unsicher — Entscheidung durch Nutzer nötig
| Ticker | Problem |
|--------|---------|
| **CSKR** | Alle drei unterschiedlich: App 485 € / Gemini 432 € / GPT 522 GBp. |
| **AGED** | Nur 2 Werte (App 8 € / GPT 9,89 $ ≈ 8,5 €), ~6 % auseinander, Gemini fehlt. |
| **PHAG** | Nur App-Anker (62 €), keine externe Bestätigung. |
| **PHPT** | Nur App-Anker (161 €), keine externe Bestätigung. |
| **COPA** | Nur App-Anker (46 €), keine externe Bestätigung. |

---

## 3. Stammdaten (TER / AuM / Positionen / Replikation)

Zusammengetragen aus beiden ChatGPT-Reports + Gemini. AuM in Mio. der jeweiligen Fondswährung. Leer = nicht gefunden.

| Ticker | TER % | AuM (Mio.) | Positionen | Ausschüttung | Fondswährung | Replikation |
|--------|------|-----------|-----------|--------------|--------------|-------------|
| SXR8 | 0,07 | 128.875 (GPT) / 144.648 (Gemini) | ~503–504 | thesaurierend | USD | physisch (vollst.) |
| CPXJ | 0,20 | 3.750 (Gemini) / 8.278 (GPT) | 85–94 | thesaurierend | USD | physisch |
| CSKR | 0,59 (GPT) / 0,65 (Gemini) | 2.025–2.538 | 80–118 | thesaurierend | USD | physisch |
| IJPA | 0,12 (Gemini) / 0,20 (GPT) | 4.108 | 818–957 | thesaurierend | USD | physisch |
| WHCS | 0,18 | – | – | ausschüttend | USD | physisch |
| AGED | 0,35 | 167 | 60 | thesaurierend | USD | physisch |
| PHAG | 0,49 | 1.275 | — (ETC) | ausschüttend | USD | physisch (Silber) |
| PHPT | 0,49 | 380 | — (ETC) | ausschüttend | USD | physisch (Platin) |
| COPA | 0,49 | 1.340 | — (ETC) | ausschüttend | USD | physisch (Kupfer) |
| EIMI | 0,18 | 37.019 (GPT) / 44.899 (Gemini) | 3.117–4.186 | thesaurierend | USD | physisch |
| ALV | — | — | 1 (Einzelaktie) | — | EUR | — |
| ISF | 0,07 | 8.099–18.140 | 94–101 | ausschüttend | GBP | physisch |

---

## 4. Holdings / Sektoren / Länder (nur Gemini lieferte Stichtags-nahe Aufteilungen)

Die ChatGPT-Reports lieferten **keine** Holdings/Sektoren/Länder. Gemini lieferte folgende (Stand jeweils Factsheet nahe Mai 2026, nicht exakt 09.05.):

### SXR8 — Top-Holdings (Stand ~29.05.2026)
NVIDIA 7,84 % · Apple 6,44 % · Microsoft 4,90 % · Amazon 4,19 % · Alphabet A 3,62 % · Broadcom 3,20 % · Alphabet C 2,89 % · Meta A 2,16 % · Tesla 1,74 %
Länder: USA 99,82 %, Cash 0,18 %.

### CPXJ — Top-Holdings
Commonwealth Bank of Australia 9,26 % · BHP Group 8,70 % · AIA Group 5,07 % · DBS Group 4,34 % · Westpac 4,21 % · National Australia Bank 3,90 % · ANZ Group 3,53 % · HK Exchanges 2,76 % · Macquarie 2,72 % · Wesfarmers 2,64 % (Top-10 ≈ 47,13 %).

### CSKR — Top-Holdings (Stand 30.04.2026)
Samsung Electronics 26,86 % · SK Hynix 18,74 % · Samsung Electronics Pref. 3,32 % · SK Square 2,84 % · Hyundai Motor 2,58 % · KB Financial 2,13 %. Land: Korea 100 %.

### IJPA
Land: Japan 100 %. (Keine Einzel-Holdings im Report; Schwergewichte u. a. Toyota, Sony, Keyence.)

### EIMI — Top-Holdings (Stand ~29.05.2026)
TSMC 12,31 % · Samsung Electronics 5,22 % · SK Hynix 3,49 % · Tencent 2,83 % · Alibaba 2,04 % · Delta Electronics 0,98 % · MediaTek 0,93 % · China Construction Bank H 0,80 % · HDFC Bank 0,69 % · Reliance 0,67 %.
Sektoren (Morningstar, Stand 27.05.2026): Technologie 40,92 % · Finanzdienstl. 16,94 % · Zykl. Konsum 8,75 % · Industrie 8,16 % · Rohstoffe 6,30 % · Telekom 5,73 % · Gesundheit 3,36 % · Energie 3,32 % · Def. Konsum 2,98 % · Versorger 1,99 % · Immobilien 1,54 %.

### ISF — Top-Holdings & Sektoren (Stand 22.05.2026)
HSBC 9,32 % · AstraZeneca 8,24 % · Shell 7,20 % · Rolls-Royce 4,18 % · BAT 4,05 % · Unilever 3,61 % · BP 3,41 % · Rio Tinto 3,18 % · GSK 3,02 % · National Grid 2,51 %.
Sektoren: Finanzdienstl. 24,98 % · Industrie 13,71 % · Gesundheit 13,59 % · Def. Konsum 13,18 % · Energie 11,27 % · Rohstoffe 8,89 % · Versorger 5,10 % · Zykl. Konsum 4,96 % · Telekom 2,59 % · Immobilien 0,92 % · Technologie 0,80 %.
Länder: UK 83,62 % · Schweiz 2,76 % · Irland 1,13 %.

### ALV
Sektor: Versicherungen 100 % (Einzelaktie). Ex-Dividende am 08.05.2026: 17,10 € je Aktie (GJ 2025) — erklärt den Kursabschlag von 387,00 € (07.05.) auf 370,10 € (08.05.).

### WHCS / AGED / PHAG / PHPT / COPA
Keine Stichtags-nahen Aufteilungen gefunden (ETCs: jeweils 100 % physischer Rohstoff bzw. bei COPA Futures-basiert).

---

## 5. Offene Punkte für künftige Chats

- **Nachschärfen (Diff > 1 €):** EIMI 44 → ~47 €, CPXJ 203 → ~206 €, IJPA 65 → ~67 €.
- **Nutzer-Entscheidung nötig:** CSKR (widersprüchlich), AGED (dünn), PHAG/PHPT/COPA (nur App-Wert).
- **Holdings/Sektoren/Länder** existieren nur als Gemini-Daten und sind **nicht exakt auf 09.05.** datiert (meist Ende Mai 2026) — als Näherung, nicht als Stichtagswert behandeln.

*Stand der Bündelung: 02.06.2026.*
