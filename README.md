<img src="assets/icon.svg" width="64" height="64" alt="">

# nonplanar – print overhangs without supports (OrcaSlicer plugin for the AD5M)

This plugin for **OrcaSlicer 2.5 or newer** prints parts in **cone-shaped
layers instead of flat ones**. That makes overhangs that point outwards hold
up **without supports**. It is tuned for the **Flashforge Adventurer 5M**.

**Rule of thumb:** with the default angle of 15°, a 60° overhang prints as if
it were only 45° steep.

| Good for | Not good for |
|---|---|
| Mushroom shapes, bowls, cups with a flared rim | Flat ceilings and bridges |
| Lamp shades, collars, funnels | Overhangs that point **towards the centre** (they get worse!) |
| Chamfered undersides | Several parts on one plate |

> **Warning, please read:** with sloped layers the print head can hit material
> that is already printed. **Stay at the printer** for your first print, use a
> small part and leave the angle at 15°. More under
> [Cone angle and collisions](#cone-angle-and-collisions). Use at your own
> risk.

---

## Step 1: Set up once (about 5 minutes)

### 1.1 Download the plugin

Click **`nonplanar_conical.py`** in the file list above, then click the
download icon on the right (**Download raw file**). That one file is all you
need.

### 1.2 Install the plugin in OrcaSlicer

1. Open OrcaSlicer (version **2.5 or newer**, older versions have no plugin
   menu).
2. Open **Plugins** → **Install local plugin** → pick the downloaded
   `nonplanar_conical.py`.
3. The first time, Orca downloads the `numpy` package. You need **internet**
   for that. Wait a moment.
4. The plugin list now shows **Nonplanar Conical** with two functions:
   **Prepare Conical** and **Conical Layers**.

### 1.3 Create a separate print profile

You need a separate process profile so your normal prints are not affected.

1. Pick the printer **Flashforge Adventurer 5M** and a process such as
   **0.20mm Standard @Flashforge AD5M 0.4 Nozzle**.
2. Change these settings:

   | Setting | Value | Why |
   |---|---|---|
   | Others → **Slicing Pipeline Plugin** | **Conical Layers** | Turns the plugin on |
   | **Arc fitting** | **off** | The plugin cannot convert arcs |
   | **Z-hop type** | **Normal** or **Slope** | *Spiral* does not work, *Auto* sometimes uses Spiral |
   | **Make overhangs printable** | **off** | Would distort the model |
   | **Spiral vase** | **off** | Not supported |
   | **Support** | **off** | Getting rid of supports is the whole point |

3. Save the profile under a new name, for example **AD5M Conical 15°**.

If you get one of these wrong, nothing bad happens: the plugin stops the
slicing with a message that tells you what to change.

---

## Step 2: Print a part (every time)

1. **Load your model** and finish **rotating and scaling** it. You cannot do
   that later.
2. Select the **AD5M Conical 15°** profile at the top. (The plugin reads the
   first layer height from it.)
3. Run **Plugins → Prepare Conical**. A window shows where the new file is.
   It is called something like `mushroom_conical_a15_z0.2.stl` and normally
   sits next to your original file.
4. **Import this new STL** and **delete the original from the plate**. The
   new model looks warped (the edges are bent upwards). **That is correct.**
   Do not rotate or scale it. Moving it is fine.
5. **Slice.**
6. **Export** or send to the printer. Only at this moment does the plugin
   convert the G-code into cone layers.
7. **Print, and watch the first time.**

### Things that look wrong but are normal

- **The preview in Orca shows the warped model.** To see the real print, open
  the exported `.gcode` file in Orca again.
- **The print takes longer than shown.** The bed moves up and down all the
  time, and the printer slows itself down for that.
- **The top surface has fine rings**, and the lowest layers above the first
  one are thinner. The first layer itself stays flat as usual.

---

## If something does not work

| Message or problem | Fix |
|---|---|
| "… is not prepared for conical printing" | You are slicing the original. Run *Prepare Conical* first, import the new STL, delete the original. Or, if you want a normal print, pick a different process profile. |
| "… was prepared for 15° / first layer 0.2 mm, but the settings are …" | The angle or first layer height was changed afterwards. Prepare again from the original. |
| "… was rotated or scaled after preparing" | Rotate/scale the original and prepare it again. |
| "… only work with exactly one object per plate" | Put only one part and only one copy on the plate. |
| "Please turn off 'Arc fitting'" / "Spiral" / "Arcs (G2/G3)" | In the profile, turn off Arc fitting and set the Z-hop type to *Normal* or *Slope*. |
| "Make overhangs printable" / "Spiral vase mode" | Turn off the named setting in the profile. |
| The exported G-code file is almost empty and contains "ERROR" | On purpose: the conversion failed, and a wrong print must never start. The message in the file says why. |
| No **Plugins** menu | Your OrcaSlicer is older than 2.5. Update it. |
| Nozzle or fan duct touches the part | Cancel right away and use a smaller angle (see below). |

---

## Cone angle and collisions

With sloped layers, material that is already printed sits **higher** than the
nozzle tip towards the centre of the part. The print head must not hit it.
How steep you can go depends on your print head:

    largest allowed angle = arctan(h / d)

- **h** = how much higher than the nozzle tip the lowest part of the head
  sits (silicone sock, fan duct)
- **d** = how far that part is from the centre of the nozzle, measured
  sideways

Example: the fan duct sits 3 mm higher and 10 mm beside the nozzle →
arctan(3/10) ≈ 16°. Measure this on your own printer and leave a margin.

- **15°** is the default and deliberately cautious. It was not measured on an
  AD5M, so watch your first print.
- The plugin does not allow more than **30°**.
- Change the angle under **Plugins → Conical Layers → Config**:
  `{"cone_angle_deg": 15}`. After that, **prepare every part again**.

The cone axis is always in the **centre of the model**. Overhangs must point
away from the centre to benefit.

---

## How it works (for the curious)

Orca cannot slice on cone surfaces. So the plugin uses a known trick (Wüthrich
et al., *A Novel Slicing Strategy to Print Overhangs without Support
Material*, Applied Sciences 2021):

1. **Prepare Conical** bends the model: `z' = z + min(r·tan α, z − z₀)`
   (r = distance from the cone axis, z₀ = first layer height). Orca slices the
   bent model as usual, with its own walls, infill and seams.
2. **Conical Layers** bends every move in the G-code back on export. The flat
   layers become cones. Long moves are split up (at most 0.01 mm deviation),
   travel moves too, and the amount of extruded plastic is adjusted to the
   real layer thickness.

The first layer stays flat. Above it the cone grows out of a ramp of layers
that are half as thick.

## For advanced users: command line

The same file also runs without Orca's plugin system (Python ≥ 3.12):

```
python nonplanar_conical.py prepare model.stl -a 15 --z0 0.2
python nonplanar_conical.py gcode print.gcode -a 15        # changes the file in place
```

On older Orca versions you can enter the second command as a
*Post-processing script*:

```
"C:\path\to\python.exe" "C:\path\to\nonplanar_conical.py" gcode -a 15;
```

Tests:

```
python -m unittest discover -s tests
```
