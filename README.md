<img src="assets/icon.svg" width="64" height="64" alt="">

# nonplanar – konische Schichten für OrcaSlicer

OrcaSlicer-Plugin (ab Orca 2.5), das Teile in **kegelförmigen statt flachen
Schichten** druckt, abgestimmt auf den **Flashforge Adventurer 5M**. Jeder nach
außen zeigende Überhang wird dadurch um den Kegelwinkel „entschärft“: Mit 15°
druckt ein 60°-Überhang wie ein 45°-Überhang, also **ohne Stützen**.

Typische Kandidaten sind Pilzformen, nach außen ausladende Becher, Schalen und
Lampenschirme, Kragen, Ränder und angefaste Unterseiten.

Keine Wunder erwarten: Waagrechte Decken, Brücken und Überhänge, die *zur
Mitte* zeigen, werden nicht besser. Nach innen zeigende Überhänge werden sogar
um den Kegelwinkel schlechter.

## So funktioniert es

Orca kann nicht auf Kegelflächen slicen, deshalb nutzt das Plugin den bekannten
Transformations-Trick (Wüthrich et al., *A Novel Slicing Strategy to Print
Overhangs without Support Material*, Applied Sciences 2021):

1. **Konisch vorbereiten**: Das Modell wird verformt, mit
   `z' = z + min(r·tan α, z − z₀)` (r = Abstand zur Kegelachse,
   z₀ = erste Schichthöhe). Orca slict dieses verzerrte Modell ganz normal,
   mit allen eigenen Wänden, Füllungen, Nähten und Flussberechnungen.
2. **Konische Schichten**: Beim Export rechnet das Plugin jede Bewegung im
   G-Code zurück auf die Kegelfläche. Lange Bewegungen werden dabei
   unterteilt, damit sie der Fläche folgen (Toleranz 0,01 mm). Das gilt auch
   für Leerfahrten, damit die Düse nicht durch die Kegelspitze fährt. Die
   Extrusion wird an die tatsächliche Schichtdicke angepasst.

Die erste Schicht bleibt flach. Darüber wächst der Kegel aus einer Rampe mit
halb so dicken Schichten heraus, statt in der Luft zu beginnen oder ins Bett zu
fahren.

## Installation

1. OrcaSlicer ≥ 2.5 → **Plugins** → *Install local plugin* →
   `nonplanar_conical.py` auswählen. Alternativ die Datei nach
   `%APPDATA%\OrcaSlicer\orca_plugins\nonplanar_conical\` kopieren und Orca
   neu starten. `numpy` installiert Orca beim ersten Laden selbst, dafür ist
   Internet nötig.
2. Ein Prozessprofil für den konischen Druck anlegen, z. B. *0.20mm Standard
   @Flashforge AD5M 0.4 Nozzle* kopieren und „AD5M Konisch 15°“ nennen:
   - **Others → Slicing Pipeline Plugin:** *Konische Schichten*
   - **Support:** aus. Die Stützen sollen ja wegfallen. Eingeschaltete Stützen
     funktionieren aber auch, sie werden dann ebenfalls konisch.
   - **Arc fitting:** aus (Standard beim AD5M). **Z-Hop:** *Auto*, *Normal*
     oder *Slope*, aber nicht *Spiral*.
3. Den Kegelwinkel stellst du unter Plugins → *Konische Schichten* → Config
   ein: `{"cone_angle_deg": 15}`.

## Benutzung

1. Modell laden, ausrichten und skalieren. Nach dem Vorbereiten ist das
   nicht mehr erlaubt.
2. Plugins → **Konisch vorbereiten** ausführen. Das Plugin schreibt
   `<name>_konisch_a15_z0.2.stl` neben die Originaldatei. Darf es dort nicht
   schreiben, landet die Datei im Plugin-Ordner. Den Pfad zeigt ein Dialog an.
3. Diese STL importieren, das Original von der Platte löschen und das
   Konisch-Profil wählen.
4. Slicen und exportieren oder an den Drucker senden.

Gut zu wissen:

- **Die Vorschau in Orca zeigt das verzerrte Modell.** Das ist normal. Den
  echten konischen Druck siehst du, wenn du den exportierten `.gcode` wieder
  in Orca öffnest.
- Pro Platte nur **ein Objekt mit einer Kopie**, denn jedes Objekt braucht
  eine eigene Kegelachse.
- Beim Slicen prüft das Plugin, ob das Objekt vorbereitet ist, ob Winkel und
  erste Schicht noch zum Profil passen und ob nach dem Vorbereiten gedreht oder
  skaliert wurde. Falls nicht, bricht es mit einer Meldung ab. Schlägt die
  Rücktransformation fehl, wird der G-Code geleert, damit nie ein falscher
  Druck startet.
- Die Kegelachse liegt in der Mitte des Modells (Mitte der Bounding Box).
  Überhänge sollten also von der Mitte weg zeigen.
- Die Oberseite des Teils zeigt feine, ringförmige Stufen. Die Zeitschätzung
  ist leicht ungenau.

## Kegelwinkel und Kollision

Bei geneigten Schichten liegt bergauf (Richtung Achse) schon gedrucktes
Material höher als die Düsenspitze. Der Druckkopf muss deshalb überall
oberhalb eines Kegels mit Winkel α um die Düsenspitze bleiben:

    max. Winkel = arctan(h / d)

Dabei ist **h** die Höhe des tiefsten Kopfteils (Heizblock-Socke, Lüfterkanal)
über der Düsenspitze und **d** sein waagrechter Abstand zur Düsenmitte. Miss
das an deinem AD5M nach und lass Reserve. Der Standardwert **15°** ist bewusst
vorsichtig. Mehr als 30° lässt das Plugin nicht zu. Fang mit einem kleinen
Teil an und beobachte die ersten Zentimeter.

## Kommandozeile

Dieselbe Datei funktioniert auch ohne Plugin-System:

```
python nonplanar_conical.py prepare modell.stl -a 15 --z0 0.2
python nonplanar_conical.py gcode druck.gcode -a 15        # ändert die Datei direkt
```

Auf älteren Orca-Versionen kannst du den zweiten Befehl als klassisches
*Post-processing script* eintragen:

```
"C:\Pfad\zu\python.exe" "C:\Pfad\zu\nonplanar_conical.py" gcode -a 15;
```

## Tests

```
python -m unittest discover -s tests
```

Geprüft werden die Transformation (Hin- und Rückweg), dass das Mesh nach dem
Unterteilen geschlossen bleibt, die G-Code-Rücktransformation (Kegelfläche,
Extrusionsmengen, relatives und absolutes E, Achsenerkennung ohne
Skirt/Brim) und die Plugin-Logik gegen ein nachgebautes `orca`-Modul.
