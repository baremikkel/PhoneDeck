#!/usr/bin/env bash
# Installerer den lille GNOME-udvidelse, der fortæller PhoneDeck hvilke programmer
# der har et åbent vindue (bruges til "Aktiv" på Stream Deck'et).
#
# Efter installationen skal du logge ud og ind igen (Wayland indlæser først nye
# udvidelser ved næste login). Fjern den igen med:
#   gnome-extensions disable phonedeck-helper@phonedeck
#   rm -r ~/.local/share/gnome-shell/extensions/phonedeck-helper@phonedeck
set -euo pipefail
UUID="phonedeck-helper@phonedeck"
SRC="$(cd "$(dirname "$0")/.." && pwd)/gnome-extension/$UUID"
DEST="$HOME/.local/share/gnome-shell/extensions/$UUID"

mkdir -p "$DEST"
cp "$SRC/metadata.json" "$SRC/extension.js" "$DEST/"
gnome-extensions enable "$UUID" 2>/dev/null || true

# GNOME only knows the extension after the next login, so put it on the enabled list now
python3 - "$UUID" <<'EOF'
import ast, subprocess, sys
uuid = sys.argv[1]
cur = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                     capture_output=True, text=True).stdout.strip()
lst = [] if cur in ("", "@as []") else ast.literal_eval(cur.replace("@as ", ""))
if uuid not in lst:
    subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(lst + [uuid])], check=True)
EOF

echo "Installeret i $DEST"
if [ "$(gsettings get org.gnome.shell disable-user-extensions)" = "true" ]; then
  echo "OBS: Brugerudvidelser er slået fra i GNOME. Slå 'Brug udvidelser' til i programmet"
  echo "     Udvidelser (gnome-extensions-app), ellers indlæses PhoneDeck-hjælperen ikke."
fi
echo "Log ud og ind igen, så GNOME indlæser udvidelsen."
