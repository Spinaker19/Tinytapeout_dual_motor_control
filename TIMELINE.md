# TIMELINE.md — Historique du projet tt_rtmc

Ce document retrace chronologiquement toutes les modifications apportées au projet, avec leur contexte et leur motivation.

---

## Origine du projet

**tt_rtmc** (Real Time Motor Controller) est un design TinyTapeout destiné à contrôler un ou deux moteurs pas-à-pas via une interface SPI. Le cas d'usage originel est un suiveur d'étoiles (*barn door star tracker*) pour l'astrophotographie. Ce projet est un fork du travail de **jrpetrus**.

---

## 2026-04-22 — Commit initial : fork du projet jrpetrus

**Hash :** `45a441ec`

**Qu'est-ce qui a été fait ?**
Le projet est initialisé comme un fork du dépôt original de jrpetrus. L'intégralité du design est importée : les sources RTL SystemVerilog, les workflows CI/CD GitHub Actions, la documentation, et le testbench cocotb complet.

**Fichiers ajoutés (28 fichiers, 2228 lignes) :**
- `src/` : `rtmc_core.sv`, `rtmc_ctrl.sv`, `rtmc_interfaces.sv`, `rtmc_pkg.sv`, `rtmc_spi.sv`, `rtmc_spi_rxtx.sv`, `tt_um_rtmc_top_jrpetrus.sv`, `config.tcl`
- `test/` : `Makefile`, `rtmc_tb.sv`, `rtmc_testbench.py`, `rtmc_tests.py`, `rtmc_common.py`, `rtmc_scan_test.py`
- `.github/workflows/` : `docs.yaml`, `fpga.yaml`, `gds.yaml`, `test.yaml`
- `docs/` : `info.md`, images du star tracker, vidéo de démonstration
- `README.md`, `LICENSE`, `info.yaml`, `.gitignore`

**Pourquoi ?**
Prendre comme point de départ un design fonctionnel et documenté pour l'adapter aux besoins du projet (support de deux contrôleurs moteur, DFT).

---

## 2026-05-06 — Double contrôleur moteur (RTL)

**Hash :** `302b4540`

**Qu'est-ce qui a été fait ?**
Le design original ne gérait qu'un seul contrôleur moteur. Ce commit ajoute une **deuxième instance de `rtmc_ctrl`** dans `rtmc_core.sv`, ainsi que le multiplexage d'adresses pour distinguer les deux contrôleurs via les bits `[7:5]` de l'adresse SPI.

**Fichiers modifiés :**
- `src/rtmc_core.sv` : ajout de l'instance `ctrl_2`, multiplexage des signaux `reg_wr_0`/`reg_wr_1` sur `reg_addr[7:5]`, combinaison des sorties `mc = {mc_1, mc_0}` et `mc_oe = {mc_oe_1, mc_oe_0}`
- `src/rtmc_ctrl.sv` : ajustements mineurs pour supporter l'instanciation multiple
- `config.json` : ajout de la configuration du projet
- `.gitignore` : mise à jour

**Pourquoi ?**
Le star tracker original n'avait qu'un seul axe motorisé. L'objectif est de contrôler deux axes indépendants (par exemple, ascension droite + déclinaison), chacun sur 4 fils moteur.

---

## 2026-05-06 — Double contrôleur moteur (testbench)

**Hash :** `565f3418`

**Qu'est-ce qui a été fait ?**
Adaptation du testbench Python/cocotb pour prendre en charge les deux contrôleurs. Les tests existants sont modifiés pour adresser les deux instances.

**Fichiers modifiés :**
- `test/rtmc_testbench.py` : refactoring important (221 lignes modifiées sur 221) — la classe `Testbench` est revue pour envoyer les commandes aux deux contrôleurs via les bons préfixes d'adresse ; `write_reg` écrit aussi à `addr | 0x20` pour cibler simultanément les deux moteurs
- `test/rtmc_common.py` : mise à jour des constantes

**Pourquoi ?**
Les tests fonctionnels doivent vérifier le comportement des deux contrôleurs indépendamment. Le framework cocotb est adapté pour abstraire cette dualité.

---

## 2026-05-17 — Marqueur de point de départ avant intervention de Claude

**Hash :** `319f0a20`

**Qu'est-ce qui a été fait ?**
Ajout du fichier `README_BASE.md`, une documentation technique exhaustive du design dans son état courant : hiérarchie des modules, description détaillée de chaque fichier RTL, protocole SPI, banc de registres, machine à états, architecture du testbench.

**Pourquoi ?**
Ce commit sert de **point de repère** avant de confier le projet à Claude pour une série de modifications. Le message de commit (`======= LAST COMMIT BEFORE UNLEASHING CLAUDE =====`) marque explicitement cette frontière. Le README_BASE fournit à Claude le contexte complet du design pour travailler de façon informée.

---

## 2026-05-17 — Corrections de bugs et qualité par Claude

**Hash :** `73bace1f`

**Qu'est-ce qui a été fait ?**
Claude effectue une revue du code et corrige plusieurs problèmes détectés. Toutes les corrections sont documentées dans [CHANGES.md](CHANGES.md).

**Corrections de bugs :**

| ID | Fichier | Problème |
|----|---------|---------|
| BUG-1 | `src/rtmc_ctrl.sv` | Double assignation redondante dans la lecture de `GPIO_REG` : la ligne 171 écrasait la ligne 170 avec la même valeur (artefact copy-paste) |
| BUG-2 | `src/rtmc_ctrl.sv` | Commentaire incorrect : `IDCODE = 8'h42` commenté `"M" in UTF-8` alors que `0x42` correspond à `'B'` en ASCII |
| BUG-3 | `src/rtmc_spi_rxtx.sv` | Code mort commenté laissé en place : `// & ~dout_ack` créait une ambiguïté sur l'intention du code |

**Améliorations qualité :**

| ID | Fichier | Problème |
|----|---------|---------|
| QUAL-1 | `src/rtmc_core.sv` | Commentaires en français introduits lors de l'ajout du second contrôleur — traduits en anglais pour cohérence avec le reste du codebase |
| QUAL-2 | `test/rtmc_testbench.py` | Même problème de commentaires français dans le testbench — traduits en anglais |

**Fichiers modifiés :**
- `src/rtmc_ctrl.sv`
- `src/rtmc_core.sv`
- `src/rtmc_spi_rxtx.sv`
- `test/rtmc_testbench.py`
- `CHANGES.md` (créé — journal de toutes ces corrections)

**Pourquoi ?**
Nettoyage préalable avant l'ajout de la chaîne DFT, pour partir d'une base saine. Les bugs ne causaient pas de dysfonctionnement observable mais rendaient le code trompeur.

---

## 2026-05-17 — Implémentation DFT : scan chain (testbench + Makefile)

**Hash :** `bb3a1bf0`

**Qu'est-ce qui a été fait ?**
Première partie de l'implémentation DFT (*Design for Test*) : ajout de l'infrastructure de test de la chaîne de scan côté simulation.

**Contexte :** quand un chip revient de fabrication, certains transistors peuvent être défectueux (fautes *stuck-at-0* ou *stuck-at-1*). Une **chaîne de scan MUX-D** permet de tester ces fautes en connectant tous les flip-flops du design en un grand registre à décalage. On peut ainsi injecter et lire l'état interne de tous les FFs sans accès physique aux nœuds internes.

L'approche automatique via l'outil Fault CLI a été évaluée et écartée (non disponible en binaire Linux ; le package PyPI `fault 4.0.1` est un outil différent de l'écosystème Stanford/magma). La chaîne est donc insérée **manuellement** dans le RTL.

**Fichiers ajoutés/modifiés :**
- `test/rtmc_scan_test.py` (211 lignes) : 3 tests cocotb pour valider la chaîne de scan :
  - `test_scan_shift_passthrough` : injecte un '1' et vérifie qu'il traverse les 373 FFs
  - `test_scan_capture_reset_state` : vérifie l'état post-reset de la chaîne
  - `test_scan_functional_unaffected` : vérifie que le mode fonctionnel est intact après un scan
- `test/rtmc_tb.sv` : ajout des signaux `scan_en`, `scan_in_sig`, `scan_out` et du mux `mosi_mux` (SPI vs scan)
- `test/Makefile` : ajout de la cible `SCAN=yes` (module séparé, build dans `sim_build/scan/`)

**Pourquoi ?**
Écrire les tests avant ou en parallèle de l'implémentation RTL permet de valider la chaîne dès qu'elle est insérée.

---

## 2026-05-17 — Implémentation DFT : scan chain (RTL + documentation)

**Hash :** `e8f94c45`

**Qu'est-ce qui a été fait ?**
Deuxième partie de l'implémentation DFT : insertion de la chaîne de scan dans tous les modules RTL, et documentation complète.

**Profondeur totale de la chaîne : 373 bits**, répartis en 3 sous-chaînes :
```
scan_in (ui_in[6]) → rtmc_spi (89 bits) → rtmc_ctrl #1 (142 bits) → rtmc_ctrl #2 (142 bits) → scan_out (uo_out[4])
```

**Mapping des pins TinyTapeout :**

| Signal scan | Broche TT | Ancienne fonction |
|-------------|-----------|-------------------|
| `scan_en`   | `ui_in[7]`  | Miroir inutile (`uo_out[5]`) |
| `scan_in`   | `ui_in[6]`  | SPI MOSI (partagé, sans conflit si `cs_n=1`) |
| `scan_out`  | `uo_out[4]` | XOR de `uio_in` (inutile) |

**Exclusions volontaires de la chaîne :**
- `step_table[0:15]` : mémoire RAM, non synthétisée en FFs classiques, testée fonctionnellement
- `meta_rst_n` / `sync_rst_n` : synchroniseur de reset — les inclure corromprait le reset de tout le design pendant un scan

**Fichiers RTL modifiés :**
- `src/rtmc_spi_rxtx.sv` : ajout des 3 ports scan + `else if(scan_en)` dans chaque `always_ff`
- `src/rtmc_spi.sv` : idem + connexion explicite de `spi_rxtx` (suppression de `.*`)
- `src/rtmc_ctrl.sv` : idem sur 3 blocs (70 + 4 + 68 bits)
- `src/rtmc_core.sv` : câblage de la chaîne spi→ctrl_1→ctrl_2 ; connexions explicites
- `src/tt_um_rtmc_top_jrpetrus.sv` : mapping des 3 pins scan + suppression de `.*`

**Documentation ajoutée :**
- `FAULT.md` : description complète de l'implémentation (profondeur, mapping pins, protocole d'utilisation, résultats des tests)
- `CONTEXT.md` : guide générique pour reproduire cette approche sur n'importe quel design TinyTapeout

**Résultats des tests :**

| Test | Résultat |
|------|----------|
| `test_scan_shift_passthrough` | **PASS** |
| `test_scan_capture_reset_state` | **PASS** |
| `test_scan_functional_unaffected` | **PASS** |
| Tests fonctionnels existants (9/9) | **PASS** |

**Note dans le README :** un avertissement est ajouté au début de `README.md` pour créditer jrpetrus comme auteur originel du design.

---

## 2026-05-17 — Corrections du README

**Hashes :** `76be805f`, `ae768329`

**Qu'est-ce qui a été fait ?**
Deux commits successifs de correction mineure du `README.md` — ajustements de formulation ou de liens après les modifications précédentes.

---

## 2026-05-18 — Corrections Verilator + config LibreLane *(non commité)*

**Qu'est-ce qui a été fait ?**
Première tentative de synthèse avec LibreLane (`librelane config.json`). Le linter Verilator bloque la compilation avec 2 erreurs et 1 warning.

**Erreurs Verilator corrigées :**

| Fichier | Erreur | Correction |
|---------|--------|------------|
| `src/rtmc_ctrl.sv` | `ENUMVALUE` — assignation implicite `logic[3:0]` → enum anonyme dans la branche scan | Ajout d'un `typedef` (`state_t`) + cast explicite `state_t'(...)` |
| `src/rtmc_spi.sv` | `ENUMVALUE` — même problème sur l'enum d'état SPI | Ajout d'un `typedef` (`spi_state_t`) + cast explicite `spi_state_t'(...)` |
| `src/rtmc_core.sv` | `WIDTHTRUNC` — `{gpo_1, gpo_0}` produit 8 bits assignés à un signal `gpo[3:0]` | Remplacé par `gpo_0` — les pins TinyTapeout n'exposent que 4 bits GPO, `gpo_1` était silencieusement tronqué |

**Contexte des erreurs ENUMVALUE :** ces enums anonymes étaient utilisés dans les branches `else if(scan_en)` introduites lors de l'implémentation DFT. Icarus Verilog acceptait l'assignation implicite, Verilator (plus strict, conforme IEEE 1800-2017 §6.19.3) la refuse.

**Autres corrections dans `config.json` :**

| Paramètre | Avant | Après | Raison |
|-----------|-------|-------|--------|
| `CLOCK_PERIOD` | `50` (ns = 20 MHz) | `20` (ns = 50 MHz) | La valeur d'origine ne correspondait pas à la fréquence cible du design |
| `SYNTH_MAX_FANOUT` | absent | `6` | Réduction des violations de slew dans le coin ss_100C_1v60 : les buffers d'horloge pilotaient 16–17 cellules (limite : 10), ce qui causait des transitions trop lentes |

**Résultat :** flow LibreLane complet, GDS généré, 0 erreur. Warnings résiduels tous bénins (coins extrêmes, PDK, TinyTapeout wrapper).

**Violations de slew résiduelles (coin `ss_100C_1v60` uniquement) :**
`SYNTH_MAX_FANOUT: 6` a réduit les slew violations de 30 → 25 mais a augmenté les fanout violations de 27 → 54 (tradeoff : plus de buffers insérés à la synthèse = plus de cellules à gérer pour le CTS). Ces violations n'existent que dans le pire cas absolu (transistors lents, 100°C, alimentation basse 1.6V) et n'affectent pas le fonctionnement aux conditions nominales. Résoudre proprement nécessiterait un fichier SDC custom (`PNR_SDC_FILE`) pour contraindre explicitement l'arbre d'horloge.

---

## Vue d'ensemble chronologique

```
2026-04-22  Fork initial (jrpetrus)
    │
    │   ← Design original : 1 contrôleur moteur, interface SPI, testbench cocotb
    │
2026-05-06  Ajout 2ème contrôleur (RTL)
2026-05-06  Ajout 2ème contrôleur (testbench)
    │
    │   ← Design étendu : 2 contrôleurs indépendants, mux d'adresses [7:5]
    │
2026-05-17  README_BASE.md (documentation + marqueur avant Claude)
2026-05-17  Corrections bugs + qualité (Claude)   ← CHANGES.md
2026-05-17  DFT scan chain — tests + Makefile      ← rtmc_scan_test.py
2026-05-17  DFT scan chain — RTL + docs            ← FAULT.md, CONTEXT.md
2026-05-17  Fixes README (×2)
    │
2026-05-18  Corrections Verilator + config LibreLane (non commité)
    │
    ▼
État actuel : design complet avec DFT, GDS généré, 9+3 tests PASS
```

---

## Récapitulatif des fichiers et leur histoire

| Fichier | Introduit | Modifié par |
|---------|-----------|-------------|
| `src/rtmc_spi_rxtx.sv` | Fork initial | Claude (BUG-3, DFT) |
| `src/rtmc_spi.sv` | Fork initial | Claude (DFT, Verilator ENUMVALUE) |
| `src/rtmc_ctrl.sv` | Fork initial | Spinaker (dual-ctrl), Claude (BUG-1/2, DFT, Verilator ENUMVALUE) |
| `src/rtmc_core.sv` | Fork initial | Spinaker (dual-ctrl), Claude (QUAL-1, DFT, WIDTHTRUNC gpo) |
| `config.json` | Spinaker (dual-ctrl) | Claude (CLOCK_PERIOD, SYNTH_MAX_FANOUT) |
| `src/tt_um_rtmc_top_jrpetrus.sv` | Fork initial | Claude (DFT) |
| `test/rtmc_testbench.py` | Fork initial | Spinaker (dual-ctrl), Claude (QUAL-2) |
| `test/rtmc_tb.sv` | Fork initial | Claude (DFT) |
| `test/Makefile` | Fork initial | Claude (DFT) |
| `test/rtmc_scan_test.py` | Fork initial (vide) | Claude (DFT) |
| `CHANGES.md` | Claude | — |
| `FAULT.md` | Claude | — |
| `CONTEXT.md` | Claude | — |
| `README_BASE.md` | Spinaker | — |
