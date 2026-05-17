# README_BASE — Documentation technique du projet tt_rtmc

## 1. Vue d'ensemble

**tt_rtmc** (Real Time Motor Controller) est un design TinyTapeout destiné à contrôler un ou deux moteurs pas-à-pas via une interface SPI. Le cas d'usage original est un suiveur d'étoiles (*barn door star tracker*) en astrophotographie.

Le chip expose :
- une interface SPI pour la configuration et le contrôle
- 4 broches GPIO générales en entrée (GPI) et 4 en sortie (GPO)
- 8 broches de commande moteur (MC[7:0]) avec activation de sortie individuelle (OE)

Le design contient **deux instances indépendantes** de contrôleur moteur (`rtmc_ctrl`), chacune pilotant 4 fils de moteur.

---

## 2. Hiérarchie des modules

```
tt_um_rtmc_top_jrpetrus   (top-level TinyTapeout)
└── rtmc_core              (synchronisation reset + multiplexage adresses)
    ├── rtmc_spi           (protocole SPI → bus registres)
    │   └── rtmc_spi_rxtx  (transceiver bit-level SPI)
    ├── rtmc_ctrl #1       (contrôleur moteur 1 + banc de registres)
    └── rtmc_ctrl #2       (contrôleur moteur 2 + banc de registres)
```

Fichiers de support simulation (non synthétisés) :
- `rtmc_pkg.sv` — paramètres globaux (largeurs de bus)
- `rtmc_interfaces.sv` — interfaces SystemVerilog pour le testbench

---

## 3. Description détaillée des modules RTL (`src/`)

### 3.1 `tt_um_rtmc_top_jrpetrus.sv` — Top-level TinyTapeout

Point d'entrée du design. Mappe les broches TinyTapeout standard vers les signaux internes de `rtmc_core`.

**Pinout :**

| Broche TT        | Signal interne | Description                        |
|------------------|----------------|------------------------------------|
| `ui_in[3:0]`     | `gpi[3:0]`     | Entrées GPIO générales              |
| `ui_in[4]`       | `cs_n`         | SPI Chip Select (actif bas)         |
| `ui_in[5]`       | `sck`          | SPI Clock                           |
| `ui_in[6]`       | `sdi`          | SPI MOSI (données vers le chip)     |
| `uo_out[7]`      | `sdo`          | SPI MISO (données vers le maître)   |
| `uo_out[3:0]`    | `gpo[3:0]`     | Sorties GPIO générales              |
| `uio_out[7:0]`   | `mc[7:0]`      | Commande moteur (bobines)           |
| `uio_oe[7:0]`    | `mc_oe[7:0]`   | Output Enable par broche moteur     |

Trois broches supplémentaires sont tie-off : `uo_out[6] = ena`, `uo_out[5] = ui_in[7]`, `uo_out[4] = XOR(uio_in)`.

---

### 3.2 `rtmc_core.sv` — Cœur d'intégration

Rôles :
1. **Synchronisation du reset** : le signal `rst_n` (asynchrone depuis les pins) passe par deux bascules D en série (`meta_rst_n` → `sync_rst_n`) pour éviter les problèmes de métastabilité. Le `sync_rst_n` ainsi produit est distribué à tous les modules en aval.

2. **Multiplexage d'adresses** : les bits `[7:5]` de l'adresse SPI sélectionnent à quel contrôleur s'adresse la transaction :
   - `reg_addr[7:5] == 3'h0` → `ctrl_1` (MC[3:0])
   - `reg_addr[7:5] == 3'h1` → `ctrl_2` (MC[7:4])

3. **Combinaison des sorties** : les sorties des deux contrôleurs sont concaténées : `mc = {mc_1, mc_0}`, `mc_oe = {mc_oe_1, mc_oe_0}`, `gpo = {gpo_1, gpo_0}`.

---

### 3.3 `rtmc_spi_rxtx.sv` — Transceiver SPI bas niveau

Gère le décalage bit par bit d'un octet SPI (mode CPOL=0, CPHA=0, MSB en premier).

**Réception (RX) :**
- `sck` est synchronisé sur l'horloge système via deux bascules (`sck_r0`, `sck_r1`).
- Un front montant de `sck` est détecté par `sck_edge = sck_r0 & ~sck_r1`.
- À chaque `sck_edge`, `sdi` est décalé dans le registre `din` (8 bits).
- Quand `bit_count` atteint 0 (8 bits reçus), `din_valid` est pulsé pendant 1 cycle.

**Émission (TX) :**
- Le MSB de `dout_r` est envoyé en permanence sur `sdo`.
- Quand `bit_count == all-1s` et qu'un nouveau mot est disponible (`dout_valid`), `dout_r` est chargé.
- À chaque `sck_edge`, `dout_r` est décalé vers la gauche.
- `dout_ack` est pulsé quand l'octet vient d'être chargé et commence à être envoyé.

**Contrainte importante :** la période de `sck` doit être au moins 2× la période de l'horloge système pour que la détection de front soit correcte.

---

### 3.4 `rtmc_spi.sv` — Contrôleur protocole SPI

Traduit les octets SPI reçus de `rtmc_spi_rxtx` en transactions sur le bus de registres.

**Codes d'opération (envoyés par le maître SPI) :**

| Valeur | Nom | Description                 |
|--------|-----|-----------------------------|
| `0x00` | NOP | Pas d'opération              |
| `0x01` | RD  | Lecture d'un registre        |
| `0x02` | WR  | Écriture dans un registre    |

**Codes de résultat (renvoyés par le chip) :**

| Valeur | Nom      | Description                        |
|--------|----------|------------------------------------|
| `0x00` | BUSY     | Résultat pas encore disponible     |
| `0x01` | ACK      | Écriture confirmée                 |
| `0x02` | ACK_DATA | Lecture confirmée, données suivent |

**Machine à états (5 états) :**

```
         din_valid & op != NOP
IDLE ──────────────────────────► ADDR
                                   │ din_valid
                          ┌────────┴────────┐
                    op=WR │                 │ op=RD
                          ▼                 ▼
                        WRITE             ACK ◄─── attend reg_ack
                          │                 │
               byte_count=0                 │
                          └────────┬────────┘
                                   ▼
                                RESULT ──► IDLE (après envoi résultat)
```

**Format d'une transaction d'écriture (maître → chip) :**
```
[0x02: WR] [ADDR: 1 octet] [DATA_HIGH: 1 octet] [DATA_LOW: 1 octet] [NOP: 1 octet]
```
Réponse sur le dernier octet : `[0x01: ACK]`

**Format d'une transaction de lecture :**
```
[0x01: RD] [ADDR: 1 octet]
→ [0x02: ACK_DATA] [DATA_HIGH: 1 octet] [DATA_LOW: 1 octet]
```

Le bus de registres utilise un acknowledge par **inversion de toggle** : `reg_ack` bascule à chaque transaction read/write acceptée.

---

### 3.5 `rtmc_ctrl.sv` — Contrôleur moteur + banc de registres

C'est le module principal de contrôle. Il gère :
- Le banc de registres accessible par SPI
- La machine à états du moteur
- Le compteur de délai (minuterie entre pas)
- Le compteur de pas (position)
- L'index dans la table de séquençage moteur

#### Banc de registres (adresses sur 5 bits)

| Adresse | Nom               | R/W | Description                                      |
|---------|-------------------|-----|--------------------------------------------------|
| `0x00`  | ID_REG            | R   | `{VERSION=0x01, IDCODE=0x42}` — identification   |
| `0x01`  | GPIO_REG          | RW  | `{mc_oe[3:0], gpo[3:0], gpi[3:0]}`              |
| `0x02`  | STEP_CTRL_REG     | RW  | `{run[15], step[14], table_last[9:5], step_size[4:0]}` |
| `0x03`  | STEP_STAT_REG     | R   | `{state[7:4], table_idx[3:0]}` — état courant    |
| `0x04`  | STEP_DELAY_0_REG  | RW  | Bits [31:16] du délai entre pas (cycles − 1)     |
| `0x05`  | STEP_DELAY_1_REG  | RW  | Bits [15:0] du délai entre pas                   |
| `0x06`  | STEP_COUNT_0_REG  | R/WC| Bits [31:16] du compteur de pas (signé 32 bits)  |
| `0x07`  | STEP_COUNT_1_REG  | R/WC| Bits [15:0] du compteur de pas                   |
| `0x08`  | DELAY_COUNT_0_REG | R/WC| Bits [31:16] du compteur de délai courant        |
| `0x09`  | DELAY_COUNT_1_REG | R/WC| Bits [15:0] du compteur de délai courant         |
| `0x10`–`0x1F` | step_table[0:15] | RW | Table de séquençage (8 bits par entrée) |

> **R/WC** : lecture libre, écriture = remise à zéro (write-to-clear).  
> La table est sélectionnée quand le bit 4 de l'adresse est à 1 (`reg_addr[4] = 1`).

#### Registre STEP_CTRL_REG (0x02) — détail des champs

| Bit(s) | Champ       | Description                                              |
|--------|-------------|----------------------------------------------------------|
| 15     | `run`       | 1 = démarre le mode automatique, 0 = arrête              |
| 14     | `step`      | Pulse 1 pour effectuer un seul pas (ignoré si `run=1`)   |
| [9:5]  | `table_last`| Index maximum dans la table (borne haute, inclusive)     |
| [4:0]  | `step_size` | Taille du pas, signé 5 bits (négatif = sens inverse)     |

#### Machine à états du moteur (2 états)

```
    run=0        run=1
IDLE ◄────────── RUN
  │                ▲
  └── run=1 ───────┘
```

- **IDLE** : aucune activité moteur. Un pas manuel (`do_step`) est possible.
- **RUN** : le compteur de délai (`delay_count`) décompte chaque cycle. Quand il atteint 0 (`step_delay_hit`), un pas est effectué et le compteur est rechargé à `step_delay`.

#### Compteur de délai (`delay_count`)

- Actif uniquement en état RUN.
- Décompte de `step_delay` jusqu'à 0 (comparaison à 0 = moins de logique).
- À 0 : un pas est effectué, rechargement automatique à `step_delay`.
- Remise à zéro par écriture uniquement possible en état IDLE.
- **Programmer la valeur** : écrire `délai_souhaité_en_cycles − 1`.

#### Compteur de pas (`step_count`, signé 32 bits)

- Incrémenté de `step_size` à chaque pas (mode RUN ou pas manuel).
- Sert de retour de position pour un système de contrôle en boucle ouverte.
- Remise à zéro par write-to-clear sur `STEP_COUNT_0` ou `STEP_COUNT_1`.

#### Séquençage de la table moteur (`table_idx`)

- `table_idx` parcourt circulairement les entrées [0 … `table_last`].
- **Sens positif** (`step_size ≥ 0`) : si `table_idx == table_last` → retour à 0.
- **Sens négatif** (`step_size < 0`) : si `table_idx + step_size < 0` → saut à `table_last`.
- La sortie moteur `mc` est directement : `mc = step_table[table_idx]` (combinatoire).

#### Exemple de séquence pour un moteur 28BYJ-48 (8 positions de bobines)

```
table[0] = 0b1001
table[1] = 0b1000
table[2] = 0b1100
table[3] = 0b0100
table[4] = 0b0110
table[5] = 0b0010
table[6] = 0b0011
table[7] = 0b0001
table_last = 7, step_size = 1 (ou -1 pour inverser)
```

---

### 3.6 `rtmc_pkg.sv` — Paramètres globaux

Package SystemVerilog définissant les constantes partagées :

```systemverilog
ADDR_W = 8   // Largeur de l'adresse du bus registres
DATA_W = 16  // Largeur des données du bus registres
MC_W   = 8   // Largeur totale de la commande moteur (2 × 4 bits)
```

> Note : ce package n'est pas compatible avec le synthétiseur Yosys (utilisé par TinyTapeout). Les paramètres sont donc aussi définis localement dans chaque module.

---

### 3.7 `rtmc_interfaces.sv` — Interfaces simulation

Définit des interfaces SystemVerilog utilisées **uniquement pour la simulation** (non synthétisées). Elles simplifient le câblage dans le testbench :

| Interface  | Signaux                          | Description              |
|------------|----------------------------------|--------------------------|
| `spi_if`   | `sclk, cs, mosi, miso`           | Bus SPI 4 fils           |
| `gpio_if`  | `gpi[3:0], gpo[3:0]`             | GPIO générale            |
| `motor_if` | `mc[7:0], mc_oe[7:0]`            | Sorties moteur           |
| `reg_if`   | `addr, wdat, wr, rd, rdat, ack`  | Bus de registres interne |

---

## 4. Domaines d'horloge et reset

| Domaine      | Source       | Synchronisation                          |
|--------------|--------------|------------------------------------------|
| Horloge principale | `clk` (50 MHz) | Unique domaine synchrone            |
| SPI clock    | `sck` (async) | 2 bascules de synchronisation dans `rtmc_spi_rxtx` |
| Reset        | `rst_n` (async, actif bas) | 2 bascules dans `rtmc_core` → `sync_rst_n` |

Il n'y a **pas de FIFO CDC** : la synchronisation du SPI se fait par détection de front sur l'horloge principale.

---

## 5. Partie test (`test/`)

### 5.1 Architecture du testbench

Le testbench utilise **cocotb** (simulation Python + simulateur HDL). La structure est :

```
test/
├── rtmc_tb.sv          Wrapper SystemVerilog : instancie le DUT + interfaces
├── rtmc_tests.py       Tests cocotb (le MODULE appelé par le Makefile)
├── rtmc_testbench.py   Classe Testbench Python avec helpers SPI/registres
├── rtmc_common.py      Constantes partagées, carte des registres, utilitaires
└── Makefile            Configuration de simulation (Icarus / Verilator / GL)
```

### 5.2 `rtmc_tb.sv` — Wrapper SystemVerilog

Instancie le DUT (`tt_um_rtmc_top_jrpetrus`) et connecte les interfaces `spi_if`, `gpio_if`, `motor_if` aux bonnes broches `ui_in / uo_out / uio_out / uio_oe`.

Génère aussi un fichier VCD (`rtmc_tb.vcd`) pour visualisation avec GTKWave.

Supporte la simulation au niveau porte (`GL_TEST`) en ajoutant les ports d'alimentation (`VPWR`, `VGND`).

### 5.3 `rtmc_common.py` — Constantes et utilitaires

Définit le miroir Python du design RTL :

```python
ADDR_W = 8
DATA_W = 16
SYS_CLK_PERIOD_NS = 20   # 50 MHz
STEP_TABLE_OFFSET = 16   # 0x10
TABLE_DEPTH = 16
MC_OUT_WIDTH = 4          # par contrôleur

class Op(IntEnum):   NOP=0, RD=1, WR=2
class Result(IntEnum): BUSY=0, ACK=1, ACK_DATA=2

REG_MAP = { "id": 0, "gpio": 1, "step_ctrl": 2, ... }
BIT_MAP = { "gpio": {"gpi":(0,4), "gpo":(4,4), "mc_oe":(8,4)}, ... }
```

La fonction `get_next_step_idx()` modélise en Python la même logique de wrap circulaire que le RTL, utilisée pour prédire l'état attendu dans les tests.

### 5.4 `rtmc_testbench.py` — Classe Testbench

Fournit une API haut niveau au-dessus de cocotbext-spi :

#### Initialisation

```python
tb = await rtmc_tb.make_tb(dut, spi_mult=4, spi_frame_spacing=None)
```

- `spi_mult` : multiplicateur de période SPI par rapport à l'horloge système (4 → SCK = 80 ns = 12.5 MHz).
- `spi_frame_spacing` : nombre de cycles d'horloge entre les octets SPI (`None` = continu).
- Reset automatique : 10 cycles reset bas, 10 cycles montée.

#### Méthodes principales

| Méthode | Description |
|---------|-------------|
| `await tb.write(addr, val)` | Écriture SPI brute (opcode WR + addr + data) |
| `await tb.read(addr)` | Lecture SPI brute (opcode RD + addr), retourne la valeur 16 bits |
| `await tb.write_reg(name, field, val)` | Écriture d'un champ de registre (read-modify-write) |
| `await tb.read_reg(name, field)` | Lecture d'un champ de registre |
| `await tb.write_counter(name, val)` | Écriture d'un compteur 32 bits en 2 transactions |
| `await tb.read_counter(name, signed)` | Lecture d'un compteur 32 bits (optionnellement signé) |
| `await tb.write_step_table(list)` | Chargement de la table de séquençage moteur |
| `tb.get_mc_out()` | Lecture directe des sorties moteur (`mc & mc_oe`) |
| `tb.set_gpi(val)` | Forçage des entrées GPI |
| `tb.get_gpo()` | Lecture des sorties GPO |
| `await tb.step(n)` | Attente de n fronts montants d'horloge |
| `await tb.finish()` | Attend 100 cycles, lève une erreur si des erreurs ont été loguées |

> Note : `write_reg` écrit aussi à l'adresse `addr | 0x20` pour cibler simultanément les deux contrôleurs quand l'adresse < 0x20 (utile pour initialiser les deux moteurs de façon identique).

### 5.5 `rtmc_tests.py` — Tests cocotb

#### test_registers (×6 variantes)

Générées automatiquement par `cocotb.regression.TestFactory` avec :
- `spi_mult` ∈ {4, 8} — teste deux vitesses SPI
- `spi_frame_spacing` ∈ {None, 3, 7} — teste avec ou sans gap entre octets

**Ce que le test vérifie :**
1. Initialise toute la step_table à 0.
2. Écrit des valeurs aléatoires dans les 16 entrées dans un ordre aléatoire.
3. Relit les 16 entrées dans un ordre aléatoire et compare avec ce qui a été écrit.
4. Affiche le contenu de tous les registres de contrôle.

#### test_single_step

**Ce que le test vérifie :**
- Charge une table de séquençage (valeurs 1 à 16).
- Pour chaque combinaison de `step_size` ∈ {1, 2, 4, -1, -2, -4} et `table_last` correspondant :
  - Effectue 20 à 30 pas manuels (via bit `step` du `STEP_CTRL_REG`).
  - Après chaque pas, compare la sortie moteur réelle (`mc & mc_oe`) avec la valeur attendue calculée par `get_next_step_idx()`.
  - Vérifie le `step_count` accumulé (sens positif et négatif).

#### test_delay_stepping

**Ce que le test vérifie :**
- Charge la séquence réelle du moteur 28BYJ-48 (8 positions, encodée pour 2 moteurs en sens opposés).
- Pour `step_size` ∈ {-2, 1} avec des délais courts (15 et 31 cycles) :
  - Lance le mode RUN pendant 200 cycles d'horloge.
  - Après arrêt, vérifie que :
    - `state == IDLE`
    - `table_idx ≤ table_last`
    - `step_count ≥ min_steps` (pas assez lents pour être ignorés)
    - `delay_count ≤ step_delay`

#### test_gpio

**Ce que le test vérifie :**
- Toutes les 16 valeurs possibles (0000 à 1111) sur GPI : force le signal et vérifie la lecture par SPI.
- Toutes les 16 valeurs possibles sur GPO : écrit par SPI et vérifie la valeur sur les pins.

### 5.6 Lancer les simulations

Depuis le dossier `test/` :

```bash
# Simulation RTL (simulateur Icarus, par défaut)
make -B

# Simulation RTL avec Verilator
make -B SIM=verilator

# Simulation au niveau porte (nécessite gate_level_netlist.v et PDK_ROOT)
make -B GATES=yes

# Visualiser les formes d'onde
gtkwave rtmc_tb.vcd
```

**Dépendances Python :**
```
cocotb >= 1.8
cocotbext-spi >= 0.4
cocotb-bus
```

---

## 6. Résumé des points clés

| Aspect | Valeur |
|--------|--------|
| Fréquence système | 50 MHz (période 20 ns) |
| Protocole SPI | CPOL=0, CPHA=0, MSB first, 8 bits/octet |
| Vitesse SPI max | CLK_sys / 2 (25 MHz théorique) |
| Nombre de contrôleurs moteur | 2 (adresses [7:5] == 0 et 1) |
| Broches moteur par contrôleur | 4 |
| Profondeur table de séquençage | 16 entrées × 8 bits |
| Compteur de délai | 32 bits non signé |
| Compteur de pas | 32 bits signé |
| Adresse bus registres | 8 bits (5 bits effectifs par contrôleur) |
| Largeur données bus registres | 16 bits |
