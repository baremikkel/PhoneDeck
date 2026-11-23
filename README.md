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

Udviklet til og testet på en OnePlus 8 Pro + Ubuntu (også testet på en Galaxy S23). Alle Android-telefoner og Linux-PC'er
burde virke.

## Funktioner

Swipe til venstre og højre mellem seks sider. Prikkerne nederst viser, hvor du er, og den side, du sidst så, huskes. Hvilke sider der vises, og i hvilken rækkefølge, vælger du under *Indstillinger → Sider*.

| Side | Indhold |
|---|---|
| **Forside** | Byg den selv på et fast gitter (4×2 til 8×4) med CPU, GPU, RAM, net, disk, musik, Claude, donut, ur, GitHub-heatmap og **genvejsknapper** fra dit Stream Deck. Standard: CPU, GPU, musik, Claude og en systemlinje. Nederst til højre sidder en **låst Menu-knap**, der åbner indstillinger og editor på computeren |
| **System** | CPU med belastning pr. kerne, GPU (hotspot/kant, strøm, clock, blæser, VRAM), RAM, net og disk. CPU/GPU-graferne viser både belastning og temperatur. Knappen i CPU-kortets hjørne stiller CPU og GPU ved siden af eller over hinanden (også på Oversigt) |
| **Musik** | Stort cover, titel/kunstner/album, afspilning, lydstyrke, en **visualizer**, der kan slås til/fra, og **næste sang** nederst. Tryk for at se hele køen (kræver Spotify-forbindelse, se nedenfor) |
| **Claude** | **Donut** med hvad der er tilbage af dine grænser (5 timer + uge), tokens i 5-timers vinduet (input/output/cache), tid til nulstilling, i dag, 7 dage, fordeling pr. model, graf over 24 timer |
| **Aktivitet** | Heatmaps i GitHub-stil for dine GitHub-bidrag og dit Claude Code-forbrug det seneste år |
| **Knapper** | Et **Stream Deck**: standardknapper (lyd, mikrofon, afspilning, fuld skærm, lås skærm, skærmbillede) plus dine egne, med valgfri farve. Programmer med et åbent vindue markeres som **Aktiv**, og et tryk viser blot en kort besked om, at programmet allerede er åbent (se *Aktiv-markering* nedenfor). Redigeres i browseren på PC'en |

Medier bruger MPRIS (Spotify, browsere, VLC …), så der skal ingen API-nøgler til.
Skærmen holdes tændt, mens dashboardet er åbent (Wake Lock API).

Beskyttelse mod indbrænding på AMOLED: helt sort baggrund, hele layoutet flyttes et par
pixels hvert minut, og skærmen dæmpes automatisk kl. 23–07.

### Visualizer

Visualizeren viser de rigtige frekvenser fra den lyd, PC'en afspiller. Lyden opfanges
med `pw-record` fra PipeWire og analyseres med numpy. Det hele foregår lokalt, og kun
søjlehøjderne sendes til telefonen, aldrig selve lyden. Søjlerne vises kun, mens musikken spiller, så andre lyde (Discord, systemlyde …) ikke får den til at bevæge sig, når musikken er sat på pause. Optagelsen kører kun, mens
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

## Indstillinger

Åbn **<http://localhost:8765/settings>** på PC'en.

- **Sider:** slå sider til og fra, og bestem rækkefølgen.
- **Visning:** nattedæmpning (selvvalgte timer), pixel-flytning mod indbrænding og antal knapper pr. række.

- **Spotify-kø:** MPRIS viser ikke køen, så den hentes fra Spotifys Web API. Opret en gratis
  app på [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) med Redirect URI
  `http://127.0.0.1:8765/spotify/callback`, indsæt Client ID'et, og tryk *Forbind Spotify*.
  Der bruges PKCE (ingen client secret) og kun læseadgang til afspilleren. Login-tokenet
  gemmes i `~/.config/phonedeck/spotify_token.json` (kun læsbart for dig).
- **Claude-grænser:** Donutten på Claude-siden viser, hvor meget der er tilbage af 5-timers
  vinduet og ugen. To muligheder:
  - **Brug mit Claude Code-login (præcist):** henter din plans rigtige forbrug, de samme
    procenter som `/usage` i Claude Code. Tokenet læses lokalt fra `~/.claude/.credentials.json`,
    sendes kun til `api.anthropic.com` og bliver aldrig gemt, fornyet eller vist af PhoneDeck.
    Endpointet er ikke officielt dokumenteret og kan holde op med at virke.
  - **Eget estimat:** sæt selv en grænse i tokens pr. 5-timers vindue og evt. pr. uge. Siden
    viser din største blok de sidste 30 dage som hjælp.

## Forside og Stream Deck-knapper

I editoren (**<http://localhost:8765/editor>**) er der to faner:

- **Forside:** vælg et gitter, klik på et tomt felt og derefter på et andet for at markere et område, og vælg hvad der skal stå der, enten en widget eller en knap fra dit Stream Deck. Felter kan flyttes, gøres større eller mindre og fjernes.
- **Egne sider:** vælg *+ Ny side …* i sidevælgeren for at lave flere sider med dit eget gitter.
  De kan omdøbes, slettes og sorteres under Indstillinger → Sider.
- **Elementer fra udvidelser:** alle kort på en udvidelses side (fx musikafspilleren, Claude-donutten,
  24-timers grafen og GitHub-heatmappet) kan sættes på Forsiden og dine egne sider. Tilføjer du en
  udvidelse, kommer dens elementer automatisk med. En udvidelse markerer et kort med
  `data-widget="navn"` og `data-widget-name="Visningsnavn"` i sin `page.html`.
  I editoren er elementerne grupperet efter kategori (System, AI, Musik, Udvikling, Andet),
  og Stream Deck-knapperne efter den mappe, de ligger i.
- **Knapper (Stream Deck):** se nedenfor.


Åbn **<http://localhost:8765/editor>** i browseren på PC'en, eller tryk *Redigér knapper*
på telefonen, så åbner editoren på computeren. Her kan du:

- **Åbne et program**: vælg blandt dine installerede programmer (også Steam-spil og snaps). Ikon og navn hentes automatisk. Kører programmet allerede, starter knappen ikke en ekstra kopi, men viser en kort besked på telefonen.
- **Åbne en hjemmeside** i standardbrowseren, fx Messenger.
- **Sende en tastaturgenvej**, fx Ctrl+Shift+T. Kræver [`ydotool`](https://github.com/ReimuNotMoe/ydotool) med `ydotoold` kørende, fordi Wayland ikke tillader andre måder.
- **Køre en kommando eller et script**, fx `~/shortcut_scripts/mit-script.sh`.
- **Indbyggede handlinger**: lydstyrke, mute, mikrofon, afspilning og fuld skærm.

- **Mapper**: vælg *Mappe* som handling. På telefonen åbner mappen med en **Tilbage**-knap.
  I editoren dobbeltklikker du på en mappe for at åbne den. Træk en knap ind på mappen for at
  flytte den derind, eller på *Tilbage* for at flytte den ud. Mapper kan ligge op til 3 niveauer
  inde i hinanden, og en mappe kan også lægges på forsiden.
- **Gå til side**: en knap, der skifter telefonen til en bestemt side – fx Musik, Claude
  eller en af dine egne sider. Den kører ikke noget på PC'en og er smart på Forsiden.

Træk knapperne for at ændre rækkefølgen, vælg emoji, standardikon eller programikon, og
brug *Test på computeren*. Når du trykker **Gem**, opdateres telefonen med det samme.
Knapperne gemmes i `~/.config/phonedeck/buttons.json`.

### Aktiv-markering

Et program er **Aktiv**, når det har et åbent vindue, ikke bare når det kører i baggrunden:

- **Programmer under XWayland** (Discord, Spotify, VS Code, Steam-spil …) tjekker PhoneDeck selv med `xdotool`.
- **Rene Wayland-programmer** (fx Spotifast og Firefox) kan GNOME ikke vise for andre programmer. Installér den lille
  udvidelse i `gnome-extension/`, så får PhoneDeck svaret fra GNOME selv:

  ```bash
  ./scripts/install-gnome-helper.sh
  ```

  Log derefter ud og ind igen. Udvidelsen gør kun én ting: den svarer på D-Bus med hvilke programmer, der har et vindue.
  Uden den regnes Wayland-programmer som aktive, så længe de kører.

## Udvidelser

Alt ud over kernen (system, Stream Deck, forside, indstillinger) er **udvidelser**, og hver
ligger i sin egen mappe:

```
extensions/
  music/         Musik      – afspiller, egen lydstyrke, visualizer
  spotify/       Musik      – næste sang + kø (Spotify Web API)
  claude-code/   AI         – forbrug, plan-donut, heatmap
  github/        Udvikling  – bidrags-heatmap
```

- **Tilføj** en udvidelse ved at lægge en mappe i `extensions/` eller i
  `~/.config/phonedeck/extensions/`. Den dukker op på telefonen og i indstillingerne
  inden for få sekunder, uden genstart.
- **Fjern** mappen, så forsvinder udvidelsen igen: dens side, widgets og indstillinger.
- **Kategori:** `"category"` i `extension.json` grupperer udvidelser, så fx Claude Code og en
  ChatGPT-udvidelse begge ligger under *AI*. Uden kategori havner den under *Andet*.
  Indstillingerne vises under samme kategorier.

En udvidelse består af:

| Fil | Indhold |
|---|---|
| `extension.json` | navn, kategori, beskrivelse, side-titel, widgets og indstillinger (tekst, tal, til/fra, valg, info, status, knapper) |
| `backend.py` | valgfri: `class Extension` med `state()`, `action()`, `http_get()`, `info()`, `stop()` |
| `page.html` | valgfri: en side på telefonen |
| `page.js` | valgfri: `PhoneDeck.register("<id>", {render, tick, page, widgets})` |
| `page.css` | valgfri: styling |

Se `examples/hello-extension/` for et lille, kommenteret eksempel. Formatet er beskrevet i
toppen af `phonedeck/extensions.py`.

## Konfiguration

```bash
mkdir -p ~/.config/phonedeck
cp config.example.toml ~/.config/phonedeck/config.toml
```

Her kan du ændre port og GPU-navn og sætte dit GitHub-brugernavn:

```toml
[github]
user = "dit-brugernavn"
```

Knapper sat op med `[[buttons]]` i `config.toml` (det gamle format) flyttes automatisk
over i editoren første gang.

## Sikkerhed

Serveren lytter som standard kun på `127.0.0.1`, så den kan kun nås fra PC'en selv og
fra telefonen via USB. Handlinger er en fast liste plus de knapper, du selv definerer.
API'et afviser forespørgsler fra andre hjemmesider i din browser (alle kald kræver en
særlig header og den rigtige `Host`), så en ondsindet side kan hverken trykke på knapper
eller oprette nye.
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
