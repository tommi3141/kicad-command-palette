# KiCad Command Palette

Strg+P öffnet in jedem KiCad-Fenster eine Befehlspalette mit Fuzzy-Suche (wie Obsidian). Rechts steht der Shortcut.

## Installation (KiCad 9/10, Windows)

1. `install.bat` doppelklicken. Es kopiert `kicad-command-palette` nach
   `Dokumente\KiCad\<Version>\plugins\`.
2. In KiCad: Einstellungen › Plugins › **KiCad-API aktivieren**. KiCad neu starten.
3. Es wird kein zusätzliches Python gebraucht: die Oberfläche nutzt wxPython aus KiCads eigenem Python.
   Fehler und Diagnose stehen in `%TEMP%\kicad_palette.log`.
4. Pro KiCad-Sitzung einmal den Button **Command Palette** in der Werkzeugleiste des Schaltplan- oder
   PCB-Editors klicken (ggf. unter „Rechtsklick auf Werkzeugleiste › Anpassen“ einblenden).
   Danach funktioniert Strg+P in allen KiCad-Fenstern. Der Helfer beendet sich, wenn KiCad geschlossen wird.

KiCad startet Plugin-Aktionen nur per Klick, einen Autostart gibt es nicht.

## Bedienung

Tippen, ↑/↓ (oder Strg+J/K/N/P) wählen, Enter führt aus, Esc schließt. Mehrere Wörter in beliebiger
Reihenfolge, Buchstaben müssen nur in Reihenfolge vorkommen (`rt via` findet „Route › Via setzen“).
Zuletzt benutzte Befehle stehen bei leerer Suche oben (`~/.kicad_palette_recent.json`).

## Funktionsweise

- Ein Low-Level-Tastaturhook fängt Strg+P nur ab, wenn ein KiCad-Prozess im Vordergrund ist
  (KiCads Strg+P = Drucken geht dadurch nur noch über die Palette).
- Die Befehle werden bei jedem Öffnen aus der Menüleiste des aktiven Fensters gelesen, inklusive
  deiner Hotkeys. Ausführen = Menübefehl auslösen (`WM_COMMAND`).
- Das Plugin selbst (`start_palette.py`) startet nur den Helfer `kicad_palette.py` (einzelne Instanz).

## Ohne Plugin starten

`start_palette.pyw` mit KiCads `pythonw.exe` öffnen (`C:\Program Files\KiCad\10.0\bin\pythonw.exe start_palette.pyw`), denn nur dort ist wxPython enthalten.

## Grenzen

Nur Windows. Nur Menübefehle (reine Toolbar-Buttons ohne Menüeintrag fehlen).

## Repository-Struktur

```
kicad-command-palette/   das eigentliche KiCad-Plugin (plugin.json, Helfer, Icons)
install.bat                  kopiert das Plugin nach Dokumente\KiCad\<Version>\plugins
start_palette.pyw            Helfer ohne Plugin-Button starten
```

## Lizenz

MIT, siehe `LICENSE`.
