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

echo "Installeret i $DEST"
echo "Log ud og ind igen, så GNOME indlæser udvidelsen."
