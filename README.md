# PhoneDeck

Giv en gammel telefon nyt liv som **touch-dashboard til din PC**: live hardware-stats,
hvad der spiller på Spotify, Claude Code-tokenforbrug og knapper, der styrer PC'en
(lyd, mikrofon, egne genveje).

Telefonen er bare en skærm: PC'en kører en lille Python-server, og telefonen viser
den i en browser i fuld skærm, forbundet med **USB-kablet** (`adb reverse`). Det kræver
intet wifi, forsinkelsen er lav, og telefonen lader samtidig.

```
PC: python3 -m phonedeck ──(SSE over USB / adb reverse)──► Telefon: http://localhost:8765
     ├─ CPU, GPU, RAM, net, disk (psutil + sysfs)
     ├─ Medier (MPRIS: Spotify, browser, VLC …)
     ├─ Claude Code-forbrug (~/.claude/projects/*.jsonl)
     └─ Handlinger: lydstyrke, mute, mikrofon, egne knapper
```

Udviklet til en OnePlus 8 Pro + Ubuntu og testet på en Galaxy S23. Alle Android-telefoner og Linux-PC'er
burde virke.

## Funktioner

Swipe til venstre og højre mellem seks sider. Prikkerne nederst viser, hvor du er, og den side, du sidst så, huskes.

| Side | Indhold |
|---|---|
| **Oversigt** | CPU, GPU, det der spiller, Claude-forbrug og en linje med RAM, net, disk og ur |
| **System** | CPU med belastning pr. kerne, GPU (hotspot/kant, strøm, clock, blæser, VRAM), RAM, net og disk. Tryk på en CPU/GPU-graf for at skifte mellem linje og lodrette søjler, og på kernerne for lodret/vandret |
| **Musik** | Stort cover, titel/kunstner/album, afspilning, lydstyrke og en **visualizer**, der kan slås til/fra |
| **Claude** | Tokens i 5-timers vinduet (input/output/cache), tid til nulstilling, i dag, 7 dage, fordeling pr. model, graf over 24 timer |
| **Aktivitet** | Heatmaps i GitHub-stil for dine GitHub-bidrag og dit Claude Code-forbrug det seneste år |
| **Knapper** | Lydstyrke, mute, mikrofon, afspilning, fuld skærm og dine egne genveje fra `config.toml` |

Medier bruger MPRIS (Spotify, browsere, VLC …), så der skal ingen API-nøgler til.
Skærmen holdes tændt, mens dashboardet er åbent (Wake Lock API).

Beskyttelse mod indbrænding på AMOLED: helt sort baggrund, hele layoutet flyttes et par
pixels hvert minut, og skærmen dæmpes automatisk kl. 23–07.

### Visualizer

Visualizeren viser de rigtige frekvenser fra den lyd, PC'en afspiller. Lyden opfanges
med `pw-record` fra PipeWire og analyseres med numpy. Det hele foregår lokalt, og kun
søjlehøjderne sendes til telefonen, aldrig selve lyden. Optagelsen kører kun, mens
visualizeren er slået til **og** musiksiden er åben. Telefonen sender løbende et
"jeg kigger stadig"-signal, og uden det stopper PC'en optagelsen inden for 4 sekunder.

### GitHub og Claude-heatmaps

- **GitHub** læses fra din offentlige bidragsside, så der skal intet token til. Private
  bidrag tælles kun med, hvis *Private contributions* er slået til på din profil.
- **Claude Code** tælles ud fra de lokale logs. Claude Code sletter gamle logs (som
  standard efter 30 dage), så PhoneDeck gemmer de daglige totaler i
  `~/.cache/phonedeck/claude_daily.json`. Heatmappet fyldes derfor op over tid.

## Kom i gang (PC)

Kræver Python 3.11+, `psutil` og PyGObject. Visualizeren kræver desuden `numpy` og
PipeWire (`pw-record`). Det hele følger typisk med Ubuntu:

```bash
sudo apt install python3-psutil python3-gi python3-numpy pipewire-bin adb
```

```bash
git clone <dit-repo> PhoneDeck && cd PhoneDeck
python3 -m phonedeck
```

Åbn <http://localhost:8765> på PC'en for at se dashboardet.

### Autostart

```bash
mkdir -p ~/.config/systemd/user && cp scripts/phonedeck.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now phonedeck
```

## Telefonen

1. **Slå udviklerindstillinger til:** Indstillinger → Om telefonen → tryk 7 gange på *Build-nummer*.
2. **Slå USB-fejlfinding til:** Indstillinger → System → Udviklerindstillinger.
3. Sæt telefonen i PC'en med USB, og kør:

   ```bash
   ./scripts/phone-connect.sh
   ```

   Godkend "Tillad USB-fejlfinding" på telefonen første gang. Scriptet sætter
   `adb reverse` op, holder skærmen tændt under opladning og åbner dashboardet.
4. Tryk på **uret** (eller *Fuld skærm* på Knapper-siden) for fuld skærm.
   I Chrome kan du også vælge *Føj til startskærm*, så den åbner som en app i fuld skærm.

> `adb reverse` nulstilles, når kablet tages ud. Kør scriptet igen, eller se idéerne nedenfor.

## Konfiguration

```bash
mkdir -p ~/.config/phonedeck
cp config.example.toml ~/.config/phonedeck/config.toml
```

Her kan du ændre port og GPU-navn, sætte dit GitHub-brugernavn og tilføje egne
genvejsknapper. Nye knapper dukker op på telefonen inden for ca. 15 sekunder uden
genstart:

```toml
[github]
user = "dit-brugernavn"

# Åbn en hjemmeside i standardbrowseren
[[buttons]]
label = "Messenger"
icon = "💬"
command = ["xdg-open", "https://www.messenger.com"]

# Start et program
[[buttons]]
label = "Lås"
icon = "🔒"
command = ["loginctl", "lock-session"]
```

## Sikkerhed

Serveren lytter som standard kun på `127.0.0.1`, så den kan kun nås fra PC'en selv og
fra telefonen via USB. Handlinger er en fast liste plus de knapper, du selv definerer.
Sæt kun `host = "0.0.0.0"`, hvis du stoler på dit netværk, for så kan alle på det styre
knapperne.

## Kendte begrænsninger

- **Spotify som snap:** Snap-sandkassen (AppArmor) tillader kun D-Bus-kald fra
  "almindelige" processer. Kører du PhoneDeck fra en almindelig terminal eller som
  systemd-service, virker det. Startes den fra en anden sandkasse, afvises kaldet.
- **Claude-tallene** er Claude Code's lokale logs, altså forbrug fra *denne* PC. claude.ai's
  abonnementsgrænser er der ikke noget officielt API til, så 5-timers-vinduet er et estimat.

## Idéer / roadmap

- [ ] Auto-`adb reverse` når telefonen sættes i (udev-regel)
- [ ] Sluk/dæmp skærmen når PC'en er låst eller i dvale
- [ ] Batteri-beskyttelse (opladning stoppes ved ~60 % med ACC/Magisk)
- [ ] Flere sider ved at swipe (kalender, vejr, Home Assistant …)
- [ ] Windows-understøttelse (LibreHardwareMonitor)
- [ ] Minimal Android-ROM (LineageOS uden Google) i kiosk-tilstand

## Licens

MIT
