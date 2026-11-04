# Audit TWR/MWR aggregati — Validazione (prima/dopo)

**Data:** 4 novembre 2026 · **Task:** TASK-55 · **Finding:** [twr-mwr-aggregate-findings.md](twr-mwr-aggregate-findings.md)

## 1. Dati e periodo utilizzati

| Fonte | Usata in questa consegna | Nota |
|---|---|---|
| Fixture sintetiche A–G + casi extra del solver | **Sì** | `tests/unit/test_performance_golden_audit.py`: nessun dato reale |
| Scenario a due portafogli (depositi, acquisto oltre la cassa, trasferimento incrociato) | **Sì** | `tests/unit/test_performance_audit_export.py`, periodo 2026-01-01 → 2026-07-01 |
| Osservazioni MCP del proprietario sull'aggregato 19+26 (4/11/2026) | Solo come riferimento | Valori riportati nella specifica; **non** ricalcolati |
| Storico reale di Parent (19) e Wealth (26) | **No** | In questa sessione non sono disponibili né il connettore MCP Valore365 né il database |

**Conseguenza.** Questa consegna dimostra che il codice calcola correttamente TWR e MWR **sui dati che
riceve**, confrontandolo con un'implementazione indipendente. **Non** certifica i rendimenti reali di
19+26: quella validazione richiede l'esecuzione dell'export sul database di produzione (§5) e resta
comunque condizionata alla completezza degli storici dei broker.

## 2. Risultati MCP osservati (prima, dalla specifica)

| Periodo | TWR MCP | MWR MCP | Apporti impliciti |
|---|---:|---:|---:|
| 1m | −1,89% | non esposto | 25.844,86 EUR |
| 3m | −2,29% | non esposto | 26.844,86 EUR |
| YTD | +7,14% | non esposto | 45.556,12 EUR |
| 1y | +9,23% | non esposto | 80.784,69 EUR |

**Cosa cambia per questi numeri dopo le correzioni:**

- **TWR.** Cambia solo se nella finestra c'è un flusso datato **oggi** (data `end`), cioè un deposito,
  un prelievo o un acquisto oltre la cassa (AUDIT-F1). Negli altri giorni il valore è identico. Non è
  possibile stabilire dai soli dati sintetici se il 4/11/2026 l'aggregato avesse un flusso di questo
  tipo: va verificato con l'export (`external_flows` con `date == end_date`).
- **MWR.** È ora leggibile via MCP (`mwr_1m`…`mwr_1y`). Nessun valore è stato stimato o inventato.
- **AUDIT-F2** interviene solo se il valore aggregato all'inizio della finestra è ≤ 0, cosa improbabile
  per 19+26 salvo quotazioni mancanti.

## 3. Golden test: valore attuale → atteso indipendente → delta

Tolleranze: 0,01 punti percentuali sui rendimenti, 0,01 EUR sugli importi e sul residuo NPV.

| Caso | Metrica | Prima delle correzioni | Dopo | Atteso indipendente | Delta dopo |
|---|---|---:|---:|---:|---:|
| A | TWR / MWR periodo / MWR annuo | 10,0 / 10,0 / 10,0 | 10,0 / 10,0 / 10,0 | 10,0 / 10,0 / 10,0 | 0 |
| B | TWR | 10,0 | 10,0 | 10,0 | 0 |
| B | MWR (365 gg) | 10,4873 | 10,4873 | 10,4873 | 3e-5 |
| C | flussi esterni / TWR / MWR | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| D | apporto implicito / TWR | 1.000 il giorno D / 0 | uguale | 1.000 il giorno D / 0 | 0 |
| E1 | flusso netto aggregato | 0 | 0 | 0 | 0 |
| E2 | flusso netto aggregato (Parent senza cassa) | +500 | +500 | 0 se trasferimento abbinato | decisione aperta |
| E3 | TWR aggregato (singoli +10% / −10%) | 2,4390 | 2,4390 | 2,4390 (la media sarebbe 0) | 0 |
| **F** | **TWR con deposito il giorno `end`** | **0,8333** | **10,0000** | **10,0000** | **0** |
| F2 | MWR con valore iniziale 0 | 12,0469 su 364 gg | 10,0000 su 305 gg | 10,0000 su 305 gg | 0 |
| G0 | flussi dello stesso segno | `null`, `converged=false` | uguale | `null` | — |
| G1 | radici multiple (10% / 20%) | 10% annuo, nessun flag | 10% annuo, `multiple_roots=true` | {10%, 20%} | 0 |
| X | prelievo parziale (MWR annuo) | 23,6713 | 23,6713 | 23,6713 | 2e-5 |
| X | primo investimento da 0 (MWR periodo) | 10,2876 su 375 gg | 10,0000 su 365 gg | 10,0000 | 0 |
| X | finestra di 500 gg (annuo / periodo) | 15,4637 / 21,7704 | uguale | 15,4637 / 21,7704 | ~1e-6 |
| X | finestra di 30 gg (MWR / annuo) | 2,0 / `null` | uguale | 2,0 / `null` | 0 |

## 4. Auditor offline sull'export diagnostico (fixture a due portafogli)

Comando: `python scripts/audit/twr_mwr_offline_auditor.py export.json` (sola libreria standard).
L'export è prodotto da `build_performance_audit_export` sullo scenario di
`test_performance_audit_export.py`, con un deposito di 100 sul portafoglio 1 il giorno `end`.

**Prima** della correzione AUDIT-F1 (commit `35e479a`):

```text
metrica               servizio       auditor    delta pp  esito
TWR %                   3.8448        7.0899      3.2451  DIFF
MWR % (period)          7.2860        7.2860      0.0000  OK
XIRR annuo auditor: 0.15237119  residuo NPV: -0.000000
Tolleranza 0.01 pp: DISCREPANZA   (exit 1)
```

**Dopo:**

```text
metrica               servizio       auditor    delta pp  esito
TWR %                   7.0899        7.0899      0.0000  OK
MWR % (period)          7.2860        7.2860      0.0000  OK
XIRR annuo auditor: 0.15237119  residuo NPV: -0.000000
XIRR annuo servizio (da mwr_pct): 0.15237107  residuo NPV: 0.000149
Tolleranza 0.01 pp: OK   (exit 0)
```

Flussi dello scenario: depositi espliciti, un apporto implicito di 500 (acquisto di 1.500 con 1.000 di
cassa, `synthetic_flow=true`) e un trasferimento incrociato di 300 netto a 0. Il
`consistency_check.flows_match_service` è `true`: l'export contiene esattamente i flussi usati da
`PerformanceService`.

## 5. Procedura per la validazione sui dati reali (19 + 26), in sola lettura

1. Leggere via MCP `get_aggregate_performance([19, 26])`: TWR e MWR dei quattro periodi e
   `calculation_windows` (le date di TWR e MWR devono coincidere).
2. Leggere `get_aggregate_performance_audit([19, 26])`: export del periodo `1y`, al massimo 200 flussi.
   Se `truncated=true`, oppure per `1m`/`3m`/`ytd`, chiamare
   `build_performance_audit_export(service, [19, 26], user_id, period=..., offset=...)` da una shell
   del backend.
3. Salvare il JSON ed eseguire l'auditor offline: un delta superiore a 0,01 pp è una discrepanza da
   classificare (bug, metodologia, dato mancante, FX/prezzi, cassa).
4. Controllare `data_quality.prices_missing` / `fx_missing` e la freschezza (`data_freshness`; il sync
   del 4/11 era `partial`).
5. Riconciliare gli apporti impliciti (`synthetic_flow=true`) con gli estratti conto dei broker, per
   portafoglio. Non azzerarli né spostarli per ottenere rendimenti più plausibili.

## 6. Disponibilità di prezzi e FX

Sui dati reali non è stata verificata in questa sessione. L'export espone `fx_missing` (valute senza
cambio, dal dettaglio di cassa) e `prices_missing` (date di flusso con valorizzazione ≤ 0). Il sync
dichiarato `partial` il 4/11 non è un errore numerico dimostrato, ma va ricontrollato al punto 4.

## 7. Test eseguiti

| Suite | Prima | Dopo |
|---|---|---|
| `tests/unit` | 858 passed | **897 passed**, 0 xfail |
| `tests/integration/test_mcp_server.py` (schema MCP, scoping utente, limiti, tool pesanti) | 127 passed | **127 passed** |
| `tests` completo (unit + integration API/MCP) | 1020 passed | **1059 passed** |

Sicurezza: l'export chiama `resolve_portfolio_scope` (proprietà dei portafogli e stessa valuta base)
prima di ogni lettura, non usa metodi di scrittura e ha limiti di numerosità (500 flussi, 200 via MCP,
quota dei tool pesanti). Un utente diverso viene rifiutato (`test_mcp_aggregate_audit_tool_is_registered_and_scoped`).
