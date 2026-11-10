<img src="assets/icon.svg" width="64" height="64" alt="">

# nonplanar – Überhänge ohne Stützen drucken (OrcaSlicer-Plugin für den AD5M)

Dieses Plugin für **OrcaSlicer 2.5 oder neuer** druckt Teile in
**kegelförmigen statt flachen Schichten**. Dadurch halten Überhänge, die nach
außen zeigen, **ohne Stützen**. Es ist auf den **Flashforge Adventurer 5M**
abgestimmt.

**Faustregel:** Mit dem Standardwinkel 15° druckt ein 60°-Überhang so, als
wäre er nur 45° steil.

| Dafür ist es gut | Dafür ist es nichts |
|---|---|
| Pilzformen, Schalen, Becher mit ausladendem Rand | Waagrechte Decken und Brücken |
| Lampenschirme, Kragen, Trichter | Überhänge, die **zur Mitte** zeigen (werden schlechter!) |
| Angefaste Unterseiten | Mehrere Teile auf einer Platte |

> **Achtung, bitte lesen:** Bei schrägen Schichten kann der Druckkopf an schon
> gedrucktes Material stoßen. Bleib beim ersten Druck **am Drucker stehen**,
> nimm ein kleines Teil und lass den Winkel auf 15°. Mehr dazu unter
> [Kegelwinkel und Kollision](#kegelwinkel-und-kollision). Benutzung auf
> eigene Gefahr.

---

## Schritt 1: Einmalig einrichten (ca. 5 Minuten)

### 1.1 Plugin herunterladen

Klick oben in der Dateiliste auf **`nonplanar_conical.py`** und dann rechts
auf das Download-Symbol (**Download raw file**). Mehr als diese eine Datei
brauchst du nicht.

### 1.2 Plugin in OrcaSlicer installieren

1. OrcaSlicer öffnen (Version **2.5 oder neuer**, sonst gibt es kein
   Plugin-Menü).
2. **Plugins** öffnen → **Install local plugin** → die heruntergeladene
   `nonplanar_conical.py` auswählen.
3. Beim ersten Mal lädt Orca das Paket `numpy` nach. Dafür brauchst du
   **Internet**. Kurz warten.
4. In der Plugin-Liste steht jetzt **Nonplanar Conical** mit zwei Funktionen:
   **Konisch vorbereiten** und **Konische Schichten**.

### 1.3 Ein eigenes Druckprofil anlegen

Du brauchst ein eigenes Prozessprofil, damit deine normalen Drucke unberührt
bleiben.

1. Drucker **Flashforge Adventurer 5M** wählen, als Prozess z. B.
   **0.20mm Standard @Flashforge AD5M 0.4 Nozzle**.
2. Diese Einstellungen ändern:

   | Einstellung | Wert | Warum |
   |---|---|---|
   | Others → **Slicing Pipeline Plugin** | **Konische Schichten** | Schaltet das Plugin ein |
   | **Arc fitting** | **aus** | Bögen kann das Plugin nicht umrechnen |
   | **Z-Hop-Typ** | **Normal** oder **Slope** | *Spiral* geht nicht, *Auto* benutzt manchmal Spiral |
   | **Make overhangs printable** | **aus** | Würde das Modell verfälschen |
   | **Spiral vase** (Vasenmodus) | **aus** | Wird nicht unterstützt |
   | **Support** | **aus** | Die Stützen sollen ja wegfallen |

3. Profil unter einem neuen Namen speichern, z. B. **AD5M Konisch 15°**.

Stellst du etwas davon falsch ein, passiert nichts Schlimmes: Das Plugin
bricht das Slicen mit einer Meldung ab, die sagt, was zu ändern ist.

---

## Schritt 2: Ein Teil drucken (jedes Mal)

1. **Modell laden** und fertig **ausrichten und skalieren**. Das geht später
   nicht mehr.
2. Oben das Profil **AD5M Konisch 15°** wählen. (Das Plugin liest daraus die
   Höhe der ersten Schicht.)
3. **Plugins → Konisch vorbereiten** ausführen. Ein Fenster zeigt, wo die neue
   Datei liegt. Sie heißt z. B. `pilz_konisch_a15_z0.2.stl` und liegt
   normalerweise neben deinem Original.
4. **Diese neue STL importieren** und **das Original von der Platte löschen**.
   Das neue Modell sieht verzogen aus (die Ränder sind hochgebogen). **Das ist
   richtig so.** Nicht drehen, nicht skalieren, nur verschieben ist erlaubt.
5. **Slicen.**
6. **Exportieren** oder an den Drucker senden. Erst in diesem Moment rechnet
   das Plugin den G-Code in Kegelschichten um.
7. **Drucken und beim ersten Mal zuschauen.**

### Das sieht komisch aus, ist aber normal

- **Die Vorschau in Orca zeigt das verzogene Modell.** Den echten Druck
  siehst du, wenn du die exportierte `.gcode`-Datei wieder in Orca öffnest.
- **Der Druck dauert länger als angezeigt.** Das Bett fährt ständig auf und
  ab, und der Drucker bremst dafür von selbst ab.
- **Die Oberseite hat feine Ringe**, und die untersten Schichten über der
  ersten sind dünner. Die erste Schicht selbst bleibt ganz normal flach.

---

## Wenn etwas nicht klappt

| Meldung oder Problem | Lösung |
|---|---|
| „… ist nicht konisch vorbereitet“ | Du slicst das Original. Erst *Konisch vorbereiten* ausführen, die neue STL importieren, das Original löschen. Oder: Du willst normal drucken, dann ein anderes Prozessprofil wählen. |
| „… wurde für 15° / erste Schicht 0.2 mm vorbereitet, eingestellt sind …“ | Winkel oder erste Schichthöhe wurden danach geändert. Vom Original aus neu vorbereiten. |
| „… wurde nach dem Vorbereiten gedreht oder skaliert“ | Das Original drehen/skalieren und neu vorbereiten. |
| „… nur mit genau einem Objekt pro Platte“ | Nur ein Teil und nur eine Kopie auf die Platte. |
| „Bitte 'Arc fitting' ausschalten“ / „Spiral“ / „Bögen (G2/G3)“ | Im Profil Arc fitting aus und Z-Hop-Typ auf *Normal* oder *Slope* stellen. |
| „Make overhangs printable“ / „Vasenmodus“ | Die genannte Einstellung im Profil ausschalten. |
| Die exportierte G-Code-Datei ist fast leer und enthält „FEHLER“ | Absicht: Beim Umrechnen ging etwas schief, und ein falscher Druck soll nie starten. Die Meldung in der Datei sagt, warum. |
| Kein Menü **Plugins** | OrcaSlicer ist älter als 2.5. Aktualisieren. |
| Düse oder Lüfterkanal streift das Teil | Sofort abbrechen und einen kleineren Winkel nehmen (siehe unten). |

---

## Kegelwinkel und Kollision

Bei schrägen Schichten liegt Richtung Teilemitte schon gedrucktes Material
**höher** als die Düsenspitze. Der Druckkopf darf dort nicht anstoßen. Wie
steil du gehen darfst, hängt von deinem Druckkopf ab:

    größter erlaubter Winkel = arctan(h / d)

- **h** = wie viel höher als die Düsenspitze das tiefste Teil am Kopf sitzt
  (Silikonsocke, Lüfterkanal)
- **d** = wie weit dieses Teil waagrecht von der Düsenmitte weg ist

Beispiel: Der Lüfterkanal sitzt 3 mm höher und 10 mm neben der Düse →
arctan(3/10) ≈ 16°. Miss das an deinem eigenen Drucker nach und lass Reserve.

- **15°** ist der Standard und bewusst vorsichtig. Für den AD5M wurde er
  nicht ausgemessen, daher: erster Druck unter Aufsicht.
- Mehr als **30°** lässt das Plugin nicht zu.
- Den Winkel änderst du unter **Plugins → Konische Schichten → Config**:
  `{"cone_angle_deg": 15}`. Danach jedes Teil **neu vorbereiten**.

Die Kegelachse liegt immer in der **Mitte des Modells**. Überhänge müssen
also von der Mitte weg zeigen, damit sie profitieren.

---

## Wie es funktioniert (für Neugierige)

Orca kann nicht auf Kegelflächen slicen. Das Plugin nutzt deshalb einen
bekannten Trick (Wüthrich et al., *A Novel Slicing Strategy to Print Overhangs
without Support Material*, Applied Sciences 2021):

1. **Konisch vorbereiten** verbiegt das Modell: `z' = z + min(r·tan α, z − z₀)`
   (r = Abstand zur Kegelachse, z₀ = Höhe der ersten Schicht). Orca slict das
   verbogene Modell ganz normal, mit seinen eigenen Wänden, Füllungen und
   Nähten.
2. **Konische Schichten** biegt beim Export jede Bewegung im G-Code wieder
   zurück. Aus den flachen Schichten werden so Kegel. Lange Bewegungen werden
   unterteilt (Abweichung höchstens 0,01 mm), auch Leerfahrten, und die
   Extrusionsmenge wird an die echte Schichtdicke angepasst.

Die erste Schicht bleibt flach. Darüber wächst der Kegel aus einer Rampe mit
halb so dicken Schichten heraus.

## Für Fortgeschrittene: Kommandozeile

Dieselbe Datei läuft auch ohne Orca-Plugin-System (Python ≥ 3.12):

```
python nonplanar_conical.py prepare modell.stl -a 15 --z0 0.2
python nonplanar_conical.py gcode druck.gcode -a 15        # ändert die Datei direkt
```

Auf älteren Orca-Versionen lässt sich der zweite Befehl als
*Post-processing script* eintragen:

```
"C:\Pfad\zu\python.exe" "C:\Pfad\zu\nonplanar_conical.py" gcode -a 15;
```

Tests:

```
python -m unittest discover -s tests
```
