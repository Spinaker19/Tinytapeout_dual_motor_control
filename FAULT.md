# FAULT.md — Implémentation de la chaîne de scan DFT

## Contexte

Ce document décrit l'ajout d'une infrastructure de test de fabrication (*Design for Test*, DFT) au chip tt_rtmc via une **insertion manuelle de chaîne de scan MUX-D** dans le RTL SystemVerilog. L'approche automatique via l'outil Fault CLI (AUCOHL) a été évaluée et écartée (non disponible en binaire Linux ; l'outil PyPI `fault 4.0.1` est un outil différent — écosystème magma/Stanford). La chaîne insérée manuellement est équivalente fonctionnellement au résultat d'un outil automatique.

---

## Principe de la chaîne de scan MUX-D

Chaque flip-flop du design est transformé en "scan flip-flop" :

```
Mode fonctionnel (scan_en=0) :   D_ff = D_functional (chemin normal)
Mode scan        (scan_en=1) :   D_ff = scan_in_i     (décalage en chaîne)
```

Tous les FFs sont connectés en registre à décalage de N bits :
```
scan_in → FF[0] → FF[1] → ... → FF[N-1] → scan_out
```

En mode scan (scan_en=1) :
- Chaque front montant de `clk` décale la chaîne d'un bit
- On peut **injecter** des vecteurs de test (contrôlabilité)
- On peut **lire** l'état interne de tous les FFs (observabilité)

---

## Profondeur de la chaîne

**Total : 373 bits** (répartis en 3 sous-chaînes)

| Sous-chaîne | Module | Bits |
|---|---|---|
| 1 | `rtmc_spi` (inclut `rtmc_spi_rxtx`) | 89 |
| 2 | `rtmc_ctrl` ctrl_1 | 142 |
| 3 | `rtmc_ctrl` ctrl_2 | 142 |

**Exclusions volontaires :**
- `step_table[0:15]` (mémoire RAM, 16×8 bits) — testée fonctionnellement par SPI
- `meta_rst_n` / `sync_rst_n` (synchroniseur de reset dans `rtmc_core`) — les inclure dans la chaîne corromprait `sync_rst_n` pendant le décalage, ce qui déclencherait un reset de tous les modules en aval

**Ordre de la chaîne :**
```
scan_in (ui_in[6]) → rtmc_spi (89 bits) → rtmc_ctrl #1 (142 bits) → rtmc_ctrl #2 (142 bits) → scan_out (uo_out[4])
```

---

## Détail par bloc dans `rtmc_spi_rxtx` (24 bits)

| Position | Signal | Bits |
|---|---|---|
| 0–1   | `sck_r1`, `sck_r0` | 2 |
| 2–4   | `bit_count[2:0]` | 3 |
| 5     | `din_valid` | 1 |
| 6     | `sdi_r` | 1 |
| 7–14  | `din[7:0]` | 8 |
| 15–22 | `dout_r[7:0]` | 8 |
| 23    | `dout_ack` | 1 |

## Détail par bloc dans `rtmc_spi` (65 bits propres)

| Position | Signal | Bits |
|---|---|---|
| 0–2   | `state[2:0]` | 3 |
| 3–10  | `op[7:0]` | 8 |
| 11–13 | `byte_count[2:0]` | 3 |
| 14    | `reg_rd` | 1 |
| 15    | `reg_wr` | 1 |
| 16    | `dout_valid` | 1 |
| 17–24 | `reg_addr[7:0]` | 8 |
| 25–40 | `reg_wdat[15:0]` | 16 |
| 41–56 | `rdat[15:0]` | 16 |
| 57–64 | `dout[7:0]` | 8 |

## Détail par bloc dans `rtmc_ctrl` (142 bits, ×2)

| Bloc | Signaux | Bits |
|---|---|---|
| Block 1 | `reg_ack, gpo[3:0], step_delay[31:0], table_last[3:0], step_size[4:0], do_step, do_run, step_count_clr, delay_count_clr, mc_oe[3:0], reg_rdat[15:0]` | 70 |
| Block 2 | `state[3:0]` | 4 |
| Block 3 | `delay_count[31:0], step_count[31:0], table_idx[3:0]` | 68 |

---

## Mapping des pins TinyTapeout

| Signal scan | Broche TT | Fonction originale |
|---|---|---|
| `scan_en`  | `ui_in[7]`  | Miroir inutile vers `uo_out[5]` |
| `scan_in`  | `ui_in[6]`  | SPI MOSI (mux : actif SPI si cs_n=0, actif scan si scan_en=1 et cs_n=1) |
| `scan_out` | `uo_out[4]` | XOR de uio_in (tie-off sans utilité) |

Règle de non-conflit : scan_en=1 UNIQUEMENT quand cs_n=1 (SPI inactif).

---

## Protocole d'utilisation de la chaîne de scan

```
1. Maintenir cs_n = 1 (ui_in[4] = 1) pour désactiver le SPI
2. Asserter scan_en = 1 (ui_in[7] = 1)
3. Pour chaque bit à décaler (373 cycles) :
   - Front descendant de clk : placer le bit sur scan_in (ui_in[6])
   - Front montant de clk    : la chaîne avance d'un bit
   - Front descendant suivant : lire scan_out (uo_out[4]) — valeur committée
4. Désasserter scan_en = 0 pour revenir en mode fonctionnel
```

**Important (spécificité Icarus Verilog / cocotb) :** Les assignations non-bloquantes SystemVerilog ne sont pas visibles via VPI immédiatement après le front montant. Lire `scan_out` au **front descendant** (après commit des NBA) garantit une valeur correcte.

---

## Fichiers modifiés

| Fichier | Modification |
|---|---|
| [src/rtmc_spi_rxtx.sv](src/rtmc_spi_rxtx.sv) | Ajout ports `scan_en/scan_in/scan_out` ; `else if(scan_en)` dans chaque bloc `always_ff` ; `sdi_r` et `din` ajoutés au reset |
| [src/rtmc_spi.sv](src/rtmc_spi.sv) | Ajout ports scan ; `else if(scan_en)` dans blocs state et registres ; connexion explicite de `spi_rxtx` (suppression `.*`) ; `reg_addr/reg_wdat/rdat/dout` ajoutés au reset |
| [src/rtmc_ctrl.sv](src/rtmc_ctrl.sv) | Ajout ports scan ; `else if(scan_en)` dans les 3 blocs ; `reg_rdat` ajouté au reset |
| [src/rtmc_core.sv](src/rtmc_core.sv) | Ajout ports scan ; câblage de la chaîne spi→ctrl_1→ctrl_2 ; connexions `spi` et `ctrl_1/2` rendues explicites |
| [src/tt_um_rtmc_top_jrpetrus.sv](src/tt_um_rtmc_top_jrpetrus.sv) | Mapping pins scan sur `ui_in[7:6]` et `uo_out[4]` ; connexions explicites (suppression `.*`) |
| [test/rtmc_tb.sv](test/rtmc_tb.sv) | Ajout signaux `scan_en`, `scan_in_sig`, `scan_out` ; `wire mosi_mux` pour le mux SPI/scan ; initialisation par défaut à 0 |
| [test/Makefile](test/Makefile) | Ajout cible `SCAN=yes` (module `rtmc_scan_test`, build dans `sim_build/scan/`) |
| [test/rtmc_scan_test.py](test/rtmc_scan_test.py) | 3 tests cocotb : passthrough, état post-reset, intégrité fonctionnelle |

---

## Résultats des tests

### Tests scan (`make -B SCAN=yes`)

| Test | Résultat | Description |
|---|---|---|
| `test_scan_shift_passthrough` | **PASS** | Le bit '1' traverse les 373 FFs et ressort au bon moment |
| `test_scan_capture_reset_state` | **PASS** | 3 bits non-nuls après reset (bit_count[2:0]=111 dans spi_rxtx) |
| `test_scan_functional_unaffected` | **PASS** | Le mode fonctionnel est intact après un scan |

### Tests fonctionnels existants (`make -B`)

**9/9 PASS** — aucune régression.

---

## Commandes de simulation

```bash
# Depuis le dossier test/, dans le nix-shell LibreLane :
nix-shell ~/librelane/shell.nix

# Tests fonctionnels normaux
PYTHONPATH=.venv/lib/python3.11/site-packages:$PYTHONPATH make -B

# Tests de la chaîne de scan
PYTHONPATH=.venv/lib/python3.11/site-packages:$PYTHONPATH make -B SCAN=yes

# Visualiser les formes d'onde
gtkwave rtmc_tb.vcd
```

---

## Note technique : comportement de `bit_count` à l'état de reset

Dans `rtmc_spi_rxtx`, `bit_count[2:0]` est initialisé à `'1` (= 3'b111) après reset (comportement normal : indique "pas de transaction SPI en cours"). Cela se traduit par **3 bits à 1** dans la capture post-reset de la chaîne de scan, ce qui est attendu et vérifié par le test `test_scan_capture_reset_state`.
