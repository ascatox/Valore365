# Doctor 2.0 — Metodologia finanziaria delle policy personali

Versione metodologia: **`doctor-policy-1.0`** (`METHODOLOGY_VERSION`).
Codice: `src/backend/app/services/doctor_policy/` (`snapshot.py`, `metrics.py`,
`validator.py`, `evaluator.py`). Contratto: `docs/doctor2/api-contracts.md` §2–4.

Le policy sono **regole scritte dall'utente** (es. "nessun ETF oltre il 35%") e
verificate in modo deterministico sul portafoglio. Non sono un giudizio di
adeguatezza né un consiglio: i testi descrivono solo il rapporto fra il valore
misurato e la soglia scelta dall'utente. L'Health Score standard
(`portfolio_doctor/_health.py`) resta invariato e convive con la policy: un
portafoglio può avere Health 100/100 e violare una regola personale (esempio B
del PRD, coperto da test).

## 1. Snapshot

Uno snapshot (`DoctorSnapshot`) è l'insieme delle posizioni di uno scope (uno o
più portafogli) in un istante, letto una sola volta:

- scope validato come le altre funzioni aggregate del Doctor
  (`load_scope_portfolios`: proprietà di tutti i portafogli, stessa valuta base);
- posizioni da `get_positions` (un portafoglio) o `get_positions_multi` (più
  portafogli: lo stesso asset in due portafogli è **una** posizione);
- holdings costruiti da `portfolio_doctor._holdings` (`_holdings_from_positions`,
  `_merge_holdings_by_asset`), quindi con gli stessi input del classificatore
  comune usati da Health/X-Ray;
- freschezza dalle stesse funzioni del blocco MCP `data_freshness`
  (`sync_status`, `_latest_price_value`, `_note`): `Position.price_stale`,
  `price_date`/`last_price_at`, `price_fallback = "avg_cost"`.

`snapshot_id` = primi 16 caratteri esadecimali dello sha256 del JSON canonico di
(portafogli, valuta, cash, per ogni asset: asset_id, valore di mercato, peso,
input di classificazione, timestamp prezzo, flag stale/mancante, esito ultima
sincronizzazione). Stesso portafoglio e stessi prezzi → stesso id.

`snapshot_from_holdings(...)` è il costruttore puro (test, Scenario Lab): copia
gli holdings, ricalcola i pesi dai valori di mercato e non fa I/O.

### Denominatore comune: valore investito escluso cash (D02)

`invested_value` = somma dei valori di mercato (≥ 0) delle posizioni con
`asset_type != "cash"`. Il saldo di cassa e le posizioni di tipo cash sono
esclusi da **ogni** denominatore (stessa regola del denominatore di copertura
dello X-Ray) e riportati a parte in `cash_value`. I pesi sono ricalcolati
non arrotondati: `peso_i = valore_i / invested_value × 100` (il peso
arrotondato a 2 decimali della posizione non viene usato). Un fondo monetario
classificato `cash` dal classificatore resta nel denominatore ma non conta in
azioni/obbligazioni/oro.

## 2. Metriche (tutte in punti percentuali 0–100)

Ogni metrica produce un `MetricValue`: `value` (stima puntuale non arrotondata),
`lower`/`upper` (bound prudenziali), `coverage_pct`, `quality`, `source`,
`denominator`, `denominator_value`, `contributors` (max 10, per contributo),
`notes`. **Nessuno zero inventato**: un dato non disponibile è `value = None`,
`quality = "missing"`.

### 2.1 `equity_weight_pct`, `bond_weight_pct`, `gold_weight_pct`

- Classe: `holding_asset_class` (classificatore comune `classify_asset`).
- Mappatura oro (`policy_asset_class`): classe `gold` **più** i prodotti di
  classe `commodity` la cui descrizione (nome, nome ufficiale justETF,
  investment focus, indice, categoria) cita metalli preziosi: *precious metals*,
  *metalli preziosi*, *silver/argento*, *platinum/platino*,
  *palladium/palladio*. Le altre commodity (petrolio, paniere diversificato)
  non contano. I fondi su società minerarie sono già `equity` (override del
  classificatore) e restano azionari.
- Formula: `K_c = Σ peso_i` delle posizioni di classe c; `U = Σ peso_i` delle
  posizioni di classe `unknown`.
- Bounds: `lower = K_c`, `upper = K_c + U`; `coverage = 100 − U`;
  `value = K_c / coverage × 100` (stima sulla parte classificata; uguale ai
  bounds quando `U = 0`). Coverage 0 → `value = None`, `missing`.
- Crypto e commodity non preziose sono classi note (non azioni, non
  obbligazioni): non allargano i bounds.

### 2.2 `max_single_position_pct`, `top3_positions_pct` (D03)

- Strumento canonico: ISIN (maiuscolo), in mancanza `asset_id`. Due listing
  dello stesso ISIN (VWCE.MI e VWCE.DE) o lo stesso asset in due portafogli
  sono **uno** strumento; la nota elenca i listing aggregati.
- Include ETF/fondi: è la concentrazione per *posizione* scelta dall'utente
  (diversa da `max_single_security_weight` dell'Health, che esclude i fondi).
- `max_single = max(peso canonico)`, `top3 = somma dei tre pesi canonici
  maggiori`. Coverage 100, `quality = ok`.

### 2.3 `usa_exposure_pct` (look-through con quota non classificata esplicita)

- Fonti per posizione, nello stesso ordine di `compute_geographic_exposure`:
  1. pesi paese justETF salvati (`etf_enrichment.country_weights`, letti con
     `repo.get_etf_enrichment_bulk`), mappati con `_country_to_region`;
     la parte che non arriva a 100 è **non classificata**;
  2. altrimenti `infer_region_profile` (indice/nome, poi valuta per le azioni
     singole); un ETF/fondo con indice non riconosciuto restituisce `{}` =
     100% non classificato. Oro, commodity e crypto non hanno paese:
     classificati come "altro" (USA = 0).
- Formula: `K = Σ peso_i × usa_i / 100`, `U = Σ peso_i × (100 − classificato_i) / 100`.
- `lower = K`, `upper = K + U`, `coverage = 100 − U`, `value = K / coverage × 100`.
- Golden: USA nota 35 + non classificata 30, limite max 60 → intervallo 35–65,
  coverage 70 < 80 → **UNKNOWN** «Non possiamo verificare il limite USA:
  copertura insufficiente (…)».
- Le obbligazioni contano (denominatore = valore investito escluso cash).
- Senza repository (Scenario Lab) si usa solo l'inferenza: `source =
  "region_inference"` e nota esplicita; con repository `source =
  "geographic_lookthrough"`.
- Lo X-Ray completo (top holdings via provider) non viene chiamato: la
  metrica deve essere deterministica e senza rete.

### 2.4 `weighted_ter_pct`

- TER per posizione: `resolve_holding_ters` (justETF → yFinance → `infer_ter`).
  Senza repository solo `infer_ter` (`source = "ter_inferred"`); con
  repository `source = "ter_registry"`. La quota stimata da `infer_ter` è
  dichiarata in nota.
- Universo coperto `C = Σ peso_i` delle posizioni con TER noto.
- `value = Σ (peso_i × TER_i) / C` (non arrotondato, a differenza di
  `compute_weighted_ter` che arrotonda a 2 decimali).
- `coverage = C`. Bounds: con copertura piena `lower = upper = value`;
  altrimenti `lower = Σ (peso_i × TER_i) / 100` (TER mancanti ≥ 0) e
  `upper = None` (nessun limite superiore noto). Un limite max può quindi
  fallire anche con copertura bassa se perfino il bound inferiore lo supera.
  Con copertura ≥ `min_coverage_pct` la regola è decisa sul valore
  dell'universo coperto (`quality = partial`, copertura nel testo: «su 92% del
  portafoglio coperto»); sotto, solo il bound inferiore può decidere (FAIL).
- Nessun TER noto → `missing`. Golden: TER coperto 60%, `min_coverage_pct`
  80 → **UNKNOWN**.

### 2.5 `etf_overlap_pct` (D03)

- `compute_overlap_score` (euristica del Doctor) sui soli fondi/ETF
  (`asset_type` etf/fund o prodotto quotato secondo il classificatore),
  dopo l'aggregazione per ISIN (un fondo non si sovrappone con sé stesso).
- Misura diversa dalla concentrazione; il valore è arrotondato a 0,1 dalla
  funzione condivisa. Meno di due fondi → 0 con nota (nessuna coppia).

## 3. Stati di qualità

| quality | significato |
|---|---|
| `ok` | dato completo (coverage 100) e prezzi non segnalati |
| `partial` | parte del denominatore non classificata/coperta: bounds espliciti |
| `stale` | almeno una quotazione ferma (`price_stale`) o sincronizzazione fallita |
| `missing` | dato non disponibile (`value = None`) |

`data_quality.status` della risposta: `stale` (quote ferme o sync fallita) >
`partial` (prezzi mancanti, posizione valorizzata al costo) > `unknown`
(nessuna informazione di sincronizzazione né di prezzo, tipico degli snapshot
simulati) > `ok`.

## 4. Valutazione delle regole

Confronti su valori **non arrotondati** con `EPSILON = 1e-9`; estremi
**inclusivi** (`max`: passa se `x ≤ max + ε`; `min`: passa se `x ≥ min − ε`).
L'arrotondamento (`precision` 0–3 della regola) è solo per i testi/UI.

Per una regola attiva, in ordine:

1. **Dati stale** → `UNKNOWN`, mai `PASS`: una posizione investita con
   quotazione più vecchia di `max_data_age_days` giorni di calendario (rispetto
   a `now`), o segnalata `price_stale`, o l'ultima sincronizzazione `failed`.
2. **Prezzi mancanti** per una quota del valore investito maggiore di
   `100 − min_coverage_pct` → `UNKNOWN`.
3. **Metrica non disponibile** → `UNKNOWN` («dati non disponibili»).
4. **Bounds decisivi** (look-through parziale): `max` → `PASS` se
   `upper ≤ max`, `FAIL` se `lower > max`; `min` → `PASS` se `lower ≥ min`,
   `FAIL` se `upper < min`; `range` → `FAIL` se un lato fallisce, `PASS` se
   entrambi passano. Un bound mancante è illimitato. Vale anche sotto la
   copertura minima (il risultato è certo).
5. Solo per una metrica **senza upper bound** (TER con copertura parziale):
   bounds non decisivi e `coverage ≥ min_coverage_pct` → stato del valore
   sull'universo coperto, con `quality = "partial"` e la copertura nel testo
   («TER medio ponderato 0,20% su 92% del portafoglio coperto: entro…»).
6. Altrimenti `UNKNOWN`. Per una metrica con quota non classificata
   (`lower ≠ upper`: asset class, USA) il **valore puntuale non decide mai**,
   qualunque sia la copertura («mai verde automatico su dati sconosciuti»):
   il testo riporta l'intervallo «tra X% e Y%»; sotto `min_coverage_pct` il
   testo è «copertura insufficiente (classificato il …, minimo richiesto …;
   valore tra X% e Y%)». `min_coverage_pct` è quindi un cancello: sotto la
   soglia solo i bounds possono decidere; sopra, decidono comunque solo i
   bounds (salvo il TER, punto 5).

Esempio: USA nota 50 + non classificata 15 (coverage 85 ≥ 80), limite max 60
→ intervallo 50–65 non decisivo → **UNKNOWN** «… valore tra 50,0% e 65,0%
(quota non classificata 15,0% del valore investito)», anche se la stima
puntuale (58,8%) sarebbe sotto il limite.

`breach_amount` (solo `FAIL`) = punti percentuali oltre la soglia violata,
calcolato sul valore prudenziale (`lower` per un massimo, `upper` per un
minimo), arrotondato a 1e-6 per eliminare il rumore floating point. Nel testo
compare con `precision` decimali e virgola italiana; se il risultato viene dai
bounds il valore è preceduto da «almeno» / «al massimo».

`near_limit` (flag aggiuntivo, solo su `PASS`): distanza dalla soglia più
vicina ≤ `warning_margin` (+ε). Default del margine per metrica: 2 pp per i
pesi e l'esposizione USA, 0,05 pp per il TER, 5 pp per l'overlap.

Altri stati: regola disattivata → `INACTIVE`; portafoglio senza valore
investito → risposta `empty_portfolio` e regole attive `NOT_APPLICABLE`;
nessun documento → `no_policy`.

Ordinamento: `FAIL` (severity desc, breach desc) → `UNKNOWN` (severity desc) →
`PASS` near limit → `PASS` → `NOT_APPLICABLE` → `INACTIVE`; a parità, ordine
del documento.

Testi (esempi esatti):
- «VWRA 46,6%: supera il tuo limite 35% di 11,6 punti percentuali»
- «Quota azionaria 70,0%: supera il tuo limite 65% di 5,0 punti percentuali»
- «Non possiamo verificare il limite USA: copertura insufficiente (…)»
- «Quota azionaria 63,5%: entro il tuo limite 65%, a 1,5 punti percentuali dalla soglia»

Le soglie sono mostrate senza zeri superflui (35%, 0,25%). Nessun testo usa
termini di adeguatezza/MiFID o giudizi («pericoloso», «consigliamo»): un test
lo verifica (D09).

## 5. Validazione (sintesi)

Allowlist delle 8 metriche, operatori ammessi dal registry, unità `pct`,
valori numerici JSON in [0, 100] (stringhe, booleani, NaN rifiutati: nessuna
espressione viene mai valutata), `precision` intero 0–3, nessun campo extra,
max 20 regole, `rule_id` e `metric_code` univoci. Fattibilità (solo regole
attive, solo casi certi): somma dei minimi azioni+obbligazioni+oro > 100 →
`infeasible` (55+50+10 = 115%); limite top3 < limite singola posizione →
`inconsistent`. `document_hash` = sha256 del JSON canonico del documento
normalizzato (`35` e `35.0` danno lo stesso hash).

## 6. Decisioni (registro PRD §17, D01–D10)

| id | domanda PRD | decisione | motivazione |
|---|---|---|---|
| D01 | TER: solo OCF/TER dei prodotti o anche fee consulenziali/trading? | `weighted_ter_pct` misura **solo** OCF/TER dei prodotti, con perimetro e coverage dichiarati; fee di consulenza/trading sono fuori MVP e saranno metriche separate | metriche separate con perimetro esplicito evitano di mischiare costi ricorrenti di prodotto e costi operativi |
| D02 | Escludere il cash dai pesi asset class? | Cash (saldo e posizioni `cash`) escluso da tutti i denominatori; il cash non è una metrica MVP (sarà metrica distinta) | i limiti riguardano la parte investita; la liquidità in attesa non deve diluire i pesi |
| D03 | Concentrazione per simbolo, ISIN o emittente? | Security canonica (ISIN, fallback asset_id) aggregata fra listing e portafogli; overlap ETF misura separata | lo stesso ETF su due borse è un unico rischio; l'overlap fra fondi diversi non è concentrazione |
| D04 | Quanta copertura X-Ray serve per PASS di geografia/settore? | Bounds conservativi: PASS se `upper ≤ max`, FAIL se `lower > max`, altrimenti UNKNOWN (con «tra X% e Y%»); la stima puntuale non decide mai una metrica con quota non classificata. `min_coverage_pct` (default 80) è un cancello: sotto la soglia UNKNOWN salvo bounds decisivi. Eccezione TER (nessun upper bound): PASS/FAIL sull'universo coperto solo con coverage ≥ minimo, `quality = partial` e copertura nel testo; FAIL anche se il solo lower bound supera il limite | non dichiarare rispettato un limite che la parte non classificata potrebbe violare |
| D05 | Scope aggregato: fingerprint di ID o gruppo salvato? | MVP: fingerprint normalizzato `p:<id ordinati>` + nome leggibile; proprietà di tutti i membri verificata a ogni lettura/scrittura | semplice, deterministico, invariante all'ordine; nessuna fusione con le policy singole |
| D06 | Quale modello di volatilità per le policy? | Nessuna metrica di volatilità nell'MVP; quando arriverà avrà definizione unica e versionata, separata da Health e Stress. Nel Lab la volatilità post-scenario è `N/D` motivato | evitare di mischiare modelli diversi sotto lo stesso nome |
| D07 | Fiscalità negli scenari? | MVP lordo (`tax_model: "none"`) con caveat esplicito; nessuna simulazione fiscale senza regole validate | evitare falsa precisione |
| D08 | Scritture via Copilot? | Solo con autenticazione e conferma UI esplicita (token monouso lato server); MCP esterno resta read-only | nessuna modifica da un semplice messaggio |
| D09 | Terminologia | Nessun termine che sottintenda certificazione consulenziale o adeguatezza MiFID; nessun «investimento pericoloso»; frasi fattuali su valore e soglia (verificato da test) | prodotto personale, non consulenza |
| D10 | Naming | UI «I miei parametri»; codice `DoctorPolicy` e `PolicyEvaluation` | coerenza con PRD |

Principi tecnici trasversali (non numerati nel PRD):
- Confronti su valori non arrotondati, `EPSILON = 1e-9`, estremi inclusivi; arrotondamento solo in UI.
- Dati stale (età > `max_data_age_days`, `price_stale`, sync fallita) → UNKNOWN, mai PASS.
