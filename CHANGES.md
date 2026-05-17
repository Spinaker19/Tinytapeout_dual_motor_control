# CHANGES.md — Journal des corrections et améliorations

## Corrections de bugs

### [BUG-1] `rtmc_ctrl.sv` — Double assignation redondante dans GPIO_REG (lecture)

**Fichier :** [src/rtmc_ctrl.sv](src/rtmc_ctrl.sv)

**Problème :** Lors d'une lecture du registre `GPIO_REG`, deux assignations successives ciblaient les bits `[3:0]` de `reg_rdat`. Dans un bloc `always_ff`, la dernière assignation du cycle gagne — la ligne 171 écrasait donc le champ `gpi` déjà correctement positionné par la ligne 170, en y réécrivant exactement la même valeur. Le résultat final était identique, mais le code était trompeur et constituait un artefact copy-paste évident.

**Avant :**
```systemverilog
GPIO_REG: begin
    reg_rdat[$bits(mc_oe)+$bits(gpo)+$bits(gpi)-1:0] <= {mc_oe, gpo, gpi};
    reg_rdat[$left(gpi):0] <= gpi;  // redondant, écrase les bits [3:0]
end
```

**Après :**
```systemverilog
GPIO_REG: begin
    reg_rdat[$bits(mc_oe)+$bits(gpo)+$bits(gpi)-1:0] <= {mc_oe, gpo, gpi};
end
```

---

### [BUG-2] `rtmc_ctrl.sv` — Commentaire IDCODE incorrect

**Fichier :** [src/rtmc_ctrl.sv](src/rtmc_ctrl.sv)

**Problème :** Le commentaire indiquait `// "M" in UTF-8` pour la constante `IDCODE = 8'h42`. Or, `0x42` correspond à `'B'` en ASCII (et UTF-8), pas à `'M'` (qui est `0x4D`).

**Avant :**
```systemverilog
localparam logic [7:0] IDCODE = 'h42;  // "M" in UTF-8
```

**Après :**
```systemverilog
localparam logic [7:0] IDCODE = 'h42;  // "B" in ASCII
```

---

### [BUG-3] `rtmc_spi_rxtx.sv` — Code mort commenté laissé en place

**Fichier :** [src/rtmc_spi_rxtx.sv](src/rtmc_spi_rxtx.sv)

**Problème :** La condition `& ~dout_ack` était commentée dans la logique d'assertion de `dout_ack`. Ce code mort créait une ambiguïté : est-ce un bug intentionnellement désactivé ou une optimisation volontaire ? En pratique, cette condition était inutile car `dout_ack` est systématiquement remis à `0` chaque cycle clock sans `sck_edge` (ligne précédente du même bloc), et `bit_count` ne repasse à `all-1s` qu'après 8 nouveaux fronts SCK — rendant toute ré-assertion parasite impossible. Le commentaire a été supprimé pour lever toute ambiguïté.

**Avant :**
```systemverilog
dout_ack <= &bit_count & dout_valid; // & ~dout_ack;
```

**Après :**
```systemverilog
dout_ack <= &bit_count & dout_valid;
```

---

## Améliorations qualité

### [QUAL-1] `rtmc_core.sv` — Traduction des commentaires français en anglais

**Fichier :** [src/rtmc_core.sv](src/rtmc_core.sv)

**Problème :** Les commentaires ajoutés lors de l'introduction du second contrôleur moteur étaient en français, alors que le reste du codebase est en anglais. Cette incohérence nuisait à la lisibilité pour tout contributeur extérieur.

Commentaires traduits :
- `// Signaux de chip select` → `// Per-controller register bus signals.`
- `// Multiplexage sur bits [7:5] de l'adresse` → `// Address bits [7:5] select which controller handles the transaction.`
- `// Multiplexage des réponses` + inline `// Ajoute un : '0 à la fin` → `// Mux read data and ack back to the SPI controller.`
- `// Combinaison des sorties` → `// Concatenate outputs from both controllers.`
- Commentaires inline sur les ports (`// Bits bas seulement`, `// Actif seulement si bits[7:5]==0/1`) → supprimés (information déjà portée par les noms des signaux `reg_wr_0`, `reg_wr_1`).

---

### [QUAL-2] `rtmc_testbench.py` — Traduction des commentaires français en anglais

**Fichier :** [test/rtmc_testbench.py](test/rtmc_testbench.py)

**Problème :** Même incohérence que dans `rtmc_core.sv` — plusieurs commentaires et docstrings en français introduits lors des modifications récentes.

Commentaires traduits ou nettoyés :
- `# Identification de l'entité SPI` → `# Locate the SPI interface on the DUT.`
- `# Mapping Bus pour version 0.5.0` → `# Bus signal mapping for cocotbext-spi 0.5.0.`
- `# Initialisation sécurisée des signaux` → `# Safe initialization: not all simulators expose all signals.`
- `# --- Accès SPI de base ---` → `# --- Raw SPI access ---`
- `# --- Manipulation des registres et champs ---` → `# --- Register and field access ---`
- `# --- Gestion des compteurs 32 bits ---` → `# --- 32-bit counter access ---`
- `# --- Step Table ---` → `# --- Step table ---`
- `# --- Utilitaires de simulation ---` → `# --- Simulation utilities ---`
- Docstrings `set_gpi` / `get_gpo` en français → supprimées (noms de méthodes auto-documentants)

---

## Récapitulatif des fichiers modifiés

| Fichier | Type | Description |
|---------|------|-------------|
| [src/rtmc_ctrl.sv](src/rtmc_ctrl.sv) | Bug + commentaire | Suppression ligne redondante GPIO_REG ; correction commentaire IDCODE |
| [src/rtmc_spi_rxtx.sv](src/rtmc_spi_rxtx.sv) | Code mort | Suppression du `// & ~dout_ack` commenté |
| [src/rtmc_core.sv](src/rtmc_core.sv) | Qualité | Traduction commentaires FR → EN |
| [test/rtmc_testbench.py](test/rtmc_testbench.py) | Qualité | Traduction commentaires FR → EN |

## Ce qui n'a pas été modifié (et pourquoi)

| Problème identifié | Raison de non-modification |
|--------------------|---------------------------|
| Bloc `initial` pour `step_table` | Fonctionnel pour la cible (OpenLane/Yosys supporte les `initial` sur les mémoires distribuées dans ce contexte) ; un changement vers une initialisation par reset ajouterait de la logique sans bénéfice clair |
| Absence de timeout watchdog sur le bus registres | Changement architectural non trivial, hors scope d'un correctif |
| Écriture 32 bits non atomique | Limitation de conception inhérente au protocole SPI 16 bits ; résoudre proprement nécessiterait un double-buffer ou un registre de validation |
