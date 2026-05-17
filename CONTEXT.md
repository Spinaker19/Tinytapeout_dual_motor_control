# CONTEXT.md — Guide d'implémentation DFT sur un design TinyTapeout

Ce document explique comment implémenter une **chaîne de scan DFT** (*Design for Test*) dans un design TinyTapeout synthétisé avec LibreLane. Il est écrit pour permettre à quelqu'un de reproduire la démarche sur son propre projet, indépendamment du framework de simulation utilisé.

---

## 1. Qu'est-ce que la chaîne de scan et pourquoi l'ajouter ?

Quand un chip revient de fabrication, certains transistors peuvent être défectueux (court-circuit ou circuit ouvert — les fautes dites *stuck-at-0* et *stuck-at-1*). La **chaîne de scan** permet de tester ces fautes sans accès aux nœuds internes du chip.

**Principe — scan flip-flop MUX-D :**

```
                ┌─────────┐
scan_en=0 ──┐  │         │
            ├─►│  MUX  D─►  FF  Q ──► logique combinatoire
D_fonct ────┘  │         │        └──► scan_out (vers FF suivant)
               └─────────┘
scan_in  ─────────► (entrée MUX quand scan_en=1)
```

En **mode fonctionnel** (`scan_en=0`) : le FF se comporte normalement.  
En **mode scan** (`scan_en=1`) : tous les FFs forment un long registre à décalage.

```
scan_in ──► FF[0] ──► FF[1] ──► ... ──► FF[N-1] ──► scan_out
                    (N fronts montants de clk pour traverser toute la chaîne)
```

On peut ainsi :
- **Charger** n'importe quel état dans tous les FFs (contrôlabilité)
- **Lire** l'état interne de tous les FFs (observabilité)
- **Détecter** les fautes de fabrication sans couper le chip

---

## 2. Contraintes spécifiques à TinyTapeout

TinyTapeout impose une interface fixe : `ui_in[7:0]`, `uo_out[7:0]`, `uio_in/out/oe[7:0]`. La chaîne de scan a besoin de **3 signaux supplémentaires** :

| Signal | Direction | Usage |
|--------|-----------|-------|
| `scan_en` | Entrée | Active le mode scan |
| `scan_in` | Entrée | Données en entrée de la chaîne |
| `scan_out` | Sortie | Données en sortie de la chaîne |

**Stratégie :** repurposer les pins tie-off (broches sans utilité fonctionnelle dans votre design). Dans ce projet :

| Signal scan | Broche TT | Ancienne fonction |
|------------|-----------|-------------------|
| `scan_en`  | `ui_in[7]` | Echo inutile vers uo_out |
| `scan_in`  | `ui_in[6]` | SPI MOSI — partagé (sans conflit quand cs_n=1) |
| `scan_out` | `uo_out[4]` | XOR de uio_in — inutile |

**Règle de non-conflit pour les pins partagés :** `scan_en=1` uniquement quand `cs_n=1` (SPI inactif). Si votre design n'a pas de SPI, n'importe quelle broche libre convient.

---

## 3. Comment identifier vos pins disponibles

Cherchez dans votre top-level les assignations tie-off :

```systemverilog
assign uo_out[X] = 1'b0;       // ← pin disponible
assign uo_out[X] = ena;         // ← pas critique
assign uo_out[X] = ui_in[Y];   // ← rebouclage inutile, disponible
```

Et dans votre testbench, repérez les `ui_in[X] = 1'b0` hardcodés — ce sont des entrées libres.

---

## 4. Implémentation RTL — le pattern à appliquer

### 4.1 Principe général

Dans **chaque module** contenant des `always_ff`, vous ajoutez :
1. Trois ports : `input scan_en`, `input scan_in`, `output scan_out`
2. Dans chaque bloc `always_ff`, une branche `else if(scan_en)` qui décale les registres

**Pattern de base** pour un registre N bits :

```systemverilog
// Avant (fonctionnel pur) :
always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) reg_a <= '0;
    else       reg_a <= next_reg_a;
end

// Après (avec scan MUX-D) :
always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n)        reg_a <= '0;
    else if(scan_en)  reg_a <= {carry_in, reg_a[N-1:1]};  // décalage droite
    else              reg_a <= next_reg_a;
end
// carry_out = reg_a[0]  (alimente le bloc suivant)
```

`carry_in` est le LSB du bloc précédent dans la chaîne. `carry_out` = `reg_a[0]` alimente le bloc suivant.

### 4.2 Enchaîner plusieurs blocs dans le même module

Si un module a plusieurs `always_ff`, ils sont enchaînés en série :

```
scan_in → [bloc 1: reg_a[N:0]] → reg_a[0] → [bloc 2: reg_b[M:0]] → reg_b[0] → scan_out
```

Chaque LSB sortant devient l'entrée du bloc suivant. Les lectures du LSB dans les RHS non-bloquants utilisent l'**ancienne** valeur (avant le front), ce qui est la bonne sémantique SystemVerilog.

### 4.3 Enchaîner plusieurs modules

Dans le module parent (ex. `rtmc_core`) :

```systemverilog
logic sc_mod1_out, sc_mod2_out;

module_1 m1(
    ...
    .scan_en(scan_en),
    .scan_in(scan_in),      // entrée globale
    .scan_out(sc_mod1_out)
);

module_2 m2(
    ...
    .scan_en(scan_en),
    .scan_in(sc_mod1_out),  // chaîné depuis m1
    .scan_out(sc_mod2_out)
);

assign scan_out = sc_mod2_out;  // sortie globale
```

### 4.4 Ce qu'il ne faut PAS mettre dans la chaîne

| Élément | Raison |
|---------|--------|
| Synchroniseur de reset (`meta_rst_n`, `sync_rst_n`) | Corrompre ces FFs pendant le scan réinitialiserait tout le design |
| Mémoires RAM/ROM (tableaux `logic [N-1:0] mem[0:M-1]`) | Non synthétisées en FFs classiques, testées par voie fonctionnelle |
| FFs d'horloge asynchrone dans des domaines non testables | Risque de métastabilité |

### 4.5 Exemple complet — bloc avec plusieurs registres

```systemverilog
// Module avec scan_en/scan_in/scan_out
// Chaîne interne : {reg_a[7:0], reg_b[3:0], reg_c} = 13 bits

always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin
        reg_a <= '0;  reg_b <= '0;  reg_c <= '0;
    end
    else if(scan_en) begin
        // scan_in entre dans reg_a[7] (MSB), sort par reg_c (LSB)
        reg_a <= {scan_in, reg_a[7:1]};      // carry_in = scan_in
        reg_b <= {reg_a[0], reg_b[3:1]};     // carry_in = old reg_a[0]
        reg_c <= reg_b[0];                    // carry_in = old reg_b[0]
    end
    else begin
        // logique fonctionnelle normale
        reg_a <= next_a;  reg_b <= next_b;  reg_c <= next_c;
    end
end

assign scan_out = reg_c;  // dernier bit de la chaîne
```

---

## 5. Mapping dans le top-level TinyTapeout

```systemverilog
module tt_um_votre_design (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    ...
);
    wire scan_out_w;

    // scan_en et scan_in repurposent des pins tie-off
    assign uo_out[4] = scan_out_w;   // scan_out sur une sortie libre

    votre_core core (
        ...
        .scan_en(ui_in[7]),   // pin libre en entrée
        .scan_in(ui_in[6]),   // pin libre en entrée (ou partagé avec SPI si compatible)
        .scan_out(scan_out_w)
    );
endmodule
```

---

## 6. Vérifier que la chaîne fonctionne

### 6.1 Test minimal avec n'importe quel simulateur

Le test fondamental est le **passthrough** : décaler un pattern connu dans la chaîne et vérifier qu'il en ressort intact après N fronts montants.

**Protocole en pseudo-code :**

```
// Paramètres
N = profondeur de la chaîne (compter vos FFs)

// 1. Reset du design
rst_n = 0 → attendre 10 cycles → rst_n = 1

// 2. Flush : mettre toute la chaîne à 0
scan_en = 1, scan_in = 0
répéter 2*N fois : front montant de clk

// 3. Décaler un '1' suivi de (N-1) zéros
// Le '1' entre en premier (position MSB du vecteur de test)
pour i de 0 à N-1 :
    scan_in = (i == 0) ? 1 : 0
    front descendant de clk   // stable avant le front montant
    front montant de clk       // le FF capture scan_in

// 4. Lire les bits sortants
// IMPORTANT : lire scan_out au front DESCENDANT suivant le front montant
//             (les assignations non-bloquantes sont committées à ce moment)
pour i de 0 à N-1 :
    front descendant de clk
    bit_sortant[i] = scan_out

// 5. Vérifier
// Le '1' injecté à i=0 doit sortir à bit_sortant[N-1]
assert bit_sortant[N-1] == 1
assert bit_sortant[0..N-2] == 0
```

### 6.2 Timing critique : lire après le front DESCENDANT

```
        ┌───┐   ┌───┐   ┌───┐
clk  ───┘   └───┘   └───┘   └──
         ↑       ↑       ↑
         │       │       └── FF capte scan_in → NB assignments committées
         │       │           → lire scan_out ICI (front descendant)
         │       └────────── scan_in est stable depuis le front descendant précédent
         └────────────────── mettre scan_in sur front descendant
```

La raison : dans Icarus Verilog (et d'autres simulateurs), les assignations non-bloquantes (`<=`) ne sont pas visibles immédiatement après le front montant — elles sont committées à la fin de la région active de simulation. Lire au front descendant garantit que les valeurs sont stables.

En **simulation RTL Icarus + cocotb**, `await RisingEdge` retourne avant que les NBA soient visibles ; `await FallingEdge` retourne après. Pour d'autres outils :
- **ModelSim/Questa** : utiliser un `#1` après le front montant (ou lire en `$strobe`)
- **Verilator** : lire après `eval()` dans la zone `_final`
- **Hardware réel** : pas de problème, le registre est stable bien avant le prochain front

### 6.3 Valeurs post-reset attendues

Certains FFs se réinitialisent à une valeur non-nulle. Dans ce design :

| Signal | Valeur après reset | Raison |
|--------|-------------------|--------|
| `bit_count[2:0]` dans `rtmc_spi_rxtx` | `3'b111` | Indique "pas de transaction SPI active" |
| Tous les autres FFs | `0` | Reset actif bas standard |

Lors d'un scan post-reset sans flush préalable, attendez-vous à voir ces valeurs non-nulles sortir de la chaîne.

---

## 7. Environnement LibreLane / nix-shell

### 7.1 Outils disponibles dans le nix-shell

```bash
nix-shell ~/librelane/shell.nix

# Vérilog vers simulation
which yosys        # synthèse
which iverilog     # simulation Icarus
which verilator    # simulation Verilator (si disponible)
which cocotb-config  # framework de test Python (si disponible)
```

### 7.2 Lancer une simulation Icarus sans cocotb

```bash
# Compiler
iverilog -g2012 -o sim.vvp \
    -I ../src \
    ../src/rtmc_pkg.sv \
    ../src/rtmc_interfaces.sv \
    ../src/rtmc_spi_rxtx.sv \
    ../src/rtmc_spi.sv \
    ../src/rtmc_ctrl.sv \
    ../src/rtmc_core.sv \
    ../src/tt_um_rtmc_top_jrpetrus.sv \
    votre_testbench.sv

# Simuler
vvp sim.vvp

# Visualiser (si $dumpfile/$dumpvars présents dans le testbench)
gtkwave rtmc_tb.vcd &
```

### 7.3 Template de testbench SystemVerilog minimal pour le scan

```systemverilog
`timescale 1ns/1ps

module scan_tb;
    // Paramètre : profondeur de la chaîne
    localparam N = 373;

    // Horloge et reset
    logic clk = 0;
    always #10 clk = ~clk;  // 50 MHz

    logic rst_n;
    logic scan_en;
    logic scan_in;
    logic scan_out;

    // Instanciation du DUT (adapter les connexions à votre pinout)
    tt_um_rtmc_top_jrpetrus dut(
        .ui_in ({scan_en, scan_in, 1'b0, 1'b1, 4'b0}),
        //        [7]      [6]    sclk  cs   gpi
        .uo_out({/* miso */ , /* dont_care[2:0] */, scan_out, /* gpo[3:0] */}),
        .uio_in (8'd0),
        .uio_out(),
        .uio_oe (),
        .ena    (1'b1),
        .clk    (clk),
        .rst_n  (rst_n)
    );

    // Tâche : décaler un bit dans la chaîne et lire la sortie
    task automatic shift_bit(input logic bit_in, output logic bit_out);
        @(negedge clk);       // front descendant : stable avant le montant
        scan_in = bit_in;
        @(posedge clk);       // front montant : FF capture
        @(negedge clk);       // front descendant suivant : NBA committées
        bit_out = scan_out;
    endtask

    // Test principal
    logic bit_out;
    logic [N-1:0] captured;

    initial begin
        $dumpfile("scan_tb.vcd");
        $dumpvars(0, scan_tb);

        // Reset
        rst_n = 0; scan_en = 0; scan_in = 0;
        repeat(10) @(posedge clk);
        rst_n = 1;
        repeat(10) @(posedge clk);

        // Flush : mettre toute la chaîne à 0
        scan_en = 1;
        repeat(2*N) begin
            @(negedge clk); scan_in = 0;
            @(posedge clk);
        end

        // Décaler un '1' suivi de (N-1) zéros, lire les N bits sortants
        for (int i = 0; i < N; i++) begin
            shift_bit((i == 0) ? 1'b1 : 1'b0, bit_out);
            captured[N-1-i] = bit_out;
        end

        // Vérification : le '1' doit être au LSB de captured
        if (captured == {{N-1{1'b0}}, 1'b1})
            $display("PASS : le '1' a traversé les %0d FFs correctement.", N);
        else
            $display("FAIL : captured = %b", captured);

        // Retour en mode fonctionnel
        scan_en = 0;
        repeat(5) @(posedge clk);
        $finish;
    end
endmodule
```

> **Note sur le mapping des ports** : dans l'exemple ci-dessus, `uo_out` est décomposé en signaux séparés. Adaptez selon votre pinout exact. L'essentiel est que `ui_in[7]` → `scan_en`, `ui_in[6]` → `scan_in`, `uo_out[4]` → `scan_out`.

---

## 8. Reproduire sur votre propre design — checklist

```
□ 1. Identifier les FFs à inclure (tous les always_ff, hors reset sync et RAM)
□ 2. Compter la profondeur totale N
□ 3. Choisir 3 pins TT libres pour scan_en / scan_in / scan_out
□ 4. Modifier chaque module : ajouter ports + else if(scan_en) dans chaque always_ff
□ 5. Câbler la chaîne dans le module parent (chaque .scan_out → .scan_in suivant)
□ 6. Adapter le top-level TT pour mapper les pins
□ 7. Écrire un testbench de passthrough (vérifier N shifts)
□ 8. Vérifier que les tests fonctionnels existants passent toujours (scan_en=0)
```

**Pièges courants :**
- Oublier d'ajouter un signal au reset (laisser un FF non-initialisé crée des X)
- Inclure les synchroniseurs de reset dans la chaîne (reset parasite pendant le scan)
- Lire scan_out immédiatement après posedge clk (valeur instable, lire au negedge suivant)
- Oublier un module dans la chaîne (la profondeur réelle diffère de N)

---

## 9. Fichiers de référence dans ce projet

| Fichier | Rôle |
|---------|------|
| [src/rtmc_spi_rxtx.sv](src/rtmc_spi_rxtx.sv) | Exemple de scan dans un module bas niveau (4 blocs always_ff, 24 bits) |
| [src/rtmc_ctrl.sv](src/rtmc_ctrl.sv) | Exemple de scan dans un module complexe (3 blocs, 142 bits, registres de contrôle) |
| [src/rtmc_core.sv](src/rtmc_core.sv) | Exemple de chaînage entre modules + exclusion du synchroniseur reset |
| [src/tt_um_rtmc_top_jrpetrus.sv](src/tt_um_rtmc_top_jrpetrus.sv) | Mapping des pins TT |
| [FAULT.md](FAULT.md) | Documentation détaillée de l'implémentation dans ce projet |
| [test/rtmc_scan_test.py](test/rtmc_scan_test.py) | Tests cocotb (si vous utilisez cocotb) |
