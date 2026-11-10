# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
#
# [tool.orcaslicer.plugin]
# name = "Nonplanar Conical"
# description = "Conical (non-planar) layers: print overhangs up to about 45° + cone angle without supports. Tuned for the Flashforge Adventurer 5M."
# author = "nonplanar"
# version = "0.2.0"
# ///
"""Conical (non-planar) slicing for OrcaSlicer.

Idea (conical slicing, Wüthrich et al., ZHAW 2021): instead of flat layers the
part is printed in cone-shaped layers that slope downwards to the outside by
the cone angle. Every outward-facing overhang is therefore printed as if it
were `angle` degrees steeper, so a 60° overhang needs no support at 15°.

Orca cannot slice on cones, so the classic transform trick is used:

  1. "prepare": the mesh is deformed  z' = z + min(r*tan(a), z - z0)  (r =
     distance from the cone axis, z0 = first layer height). Orca slices the
     deformed mesh with its normal planar slicer - all walls, infill, seams
     and flow are Orca's own.
  2. "gcode": every move of the result is mapped back  z = T^-1(r, z')  and
     subdivided so it follows the cone; extrusion is scaled by the change in
     layer thickness, so the deposited volume stays correct.

The `min(.., z - z0)` term is a planar base: the first layer stays flat and
the cone grows out of it with layers of half thickness instead of starting
in mid-air or ploughing into the bed.

The same file is an OrcaSlicer plugin (two capabilities) and a CLI:

  python nonplanar_conical.py prepare model.stl [-a 15]
  python nonplanar_conical.py gcode print.gcode [-a 15]     (in place)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import struct
import sys

DEFAULT_ANGLE_DEG = 15.0
MAX_ANGLE_DEG = 30.0
# Slope of the planar-base ramp: in the base region real layers are 1/(1+RAMP)
# of the sliced thickness. 1.0 -> half-thick layers, ramp height r*tan(a).
RAMP = 1.0
MESH_MAX_EDGE_MM = 1.0       # subdivision before deforming (curvature of cones)
GCODE_TOLERANCE_MM = 0.01    # max Z deviation of a subdivided move from the cone
GCODE_MAX_SEGMENT_MM = 2.0   # hard cap on subdivided move length
GCODE_TAG = "; nonplanar-conical"
NAME_RE = re.compile(r"_(?:conical|konisch)_a(\d+(?:\.\d+)?)_z(\d+(?:\.\d+)?)")
AXIS_IGNORED_FEATURES = ("custom", "skirt", "brim", "support", "prime tower", "wipe tower")


class ConicalError(Exception):
    """A problem the user has to fix; the message is shown to them."""


# --------------------------------------------------------------------------
# The transformation
# --------------------------------------------------------------------------
class Cone:
    def __init__(self, angle_deg: float, z0: float):
        if not 0.0 < angle_deg <= MAX_ANGLE_DEG:
            raise ConicalError(f"Cone angle must be between 0 and {MAX_ANGLE_DEG:g}° (is {angle_deg:g}°).")
        if not z0 > 0.0:
            raise ConicalError(f"First layer height must be > 0 (is {z0:g}).")
        self.angle_deg = float(angle_deg)
        self.z0 = float(z0)
        self.t = math.tan(math.radians(angle_deg))

    def forward(self, r: float, z: float) -> float:
        """Real height -> sliced height."""
        return z + min(r * self.t, RAMP * max(0.0, z - self.z0))

    def inverse(self, r: float, zs: float) -> tuple[float, float]:
        """Sliced height -> (real height, flow factor = real / sliced layer thickness)."""
        if zs <= self.z0:
            return zs, 1.0
        z = zs - r * self.t
        if z >= self.z0 + r * self.t / RAMP:
            return z, 1.0
        return self.z0 + (zs - self.z0) / (1.0 + RAMP), 1.0 / (1.0 + RAMP)

    def name_suffix(self) -> str:
        return f"_conical_a{self.angle_deg:g}_z{self.z0:g}"


def parse_name(name: str) -> tuple[float, float] | None:
    """(angle, z0) encoded in a prepared object's name, or None."""
    m = NAME_RE.search(name or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


# --------------------------------------------------------------------------
# Mesh: subdivide + deform
# --------------------------------------------------------------------------
def subdivide(verts: list, tris: list, max_edge: float) -> tuple[list, list]:
    """Split every edge longer than max_edge (red-green refinement).

    Midpoints are shared per edge, so a watertight mesh stays watertight and
    triangle orientation is preserved.
    """
    verts = [tuple(map(float, v)) for v in verts]
    lim2 = max_edge * max_edge
    done, todo = [], [tuple(t) for t in tris]

    def long_edge(a, b):
        va, vb = verts[a], verts[b]
        return (va[0] - vb[0]) ** 2 + (va[1] - vb[1]) ** 2 + (va[2] - vb[2]) ** 2 > lim2

    while todo:
        mids: dict = {}
        active = []
        for t in todo:
            a, b, c = t
            hit = False
            for u, v in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                if key in mids or long_edge(u, v):
                    if key not in mids:
                        pu, pv = verts[u], verts[v]
                        mids[key] = len(verts)
                        verts.append(((pu[0] + pv[0]) / 2, (pu[1] + pv[1]) / 2, (pu[2] + pv[2]) / 2))
                    hit = True
            (active if hit else done).append(t)

        def mid(u, v):
            return mids.get((u, v) if u < v else (v, u))

        todo = []
        for a, b, c in active:
            mab, mbc, mca = mid(a, b), mid(b, c), mid(c, a)
            n = (mab is not None) + (mbc is not None) + (mca is not None)
            if n == 3:
                todo += [(a, mab, mca), (mab, b, mbc), (mca, mbc, c), (mab, mbc, mca)]
            elif n == 1:
                if mbc is not None:
                    a, b, c, mab = b, c, a, mbc
                elif mca is not None:
                    a, b, c, mab = c, a, b, mca
                todo += [(a, mab, c), (mab, b, c)]
            else:  # two split edges: rotate so the unsplit one is c-a
                if mab is None:
                    a, b, c, mab, mbc = b, c, a, mbc, mca
                elif mbc is None:
                    a, b, c, mab, mbc = c, a, b, mca, mab
                todo.append((mab, b, mbc))
                pa, pc, p1, p2 = verts[a], verts[c], verts[mab], verts[mbc]
                if math.dist(pa, p2) <= math.dist(p1, pc):
                    todo += [(a, mab, mbc), (a, mbc, c)]
                else:
                    todo += [(a, mab, c), (mab, mbc, c)]
    return verts, done


def conical_mesh(verts: list, tris: list, cone: Cone, max_edge: float = MESH_MAX_EDGE_MM):
    """Deform a mesh (world orientation) for slicing.

    The cone axis is the centre of the XY bounding box; the result has the
    axis at X=Y=0 and its lowest point at Z=0. Returns (verts, tris).
    """
    if not tris:
        raise ConicalError("The model has no triangles.")
    xs, ys, zs = zip(*verts)
    cx, cy, z_min = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)
    centred = [(x - cx, y - cy, z - z_min) for x, y, z in verts]
    sub_v, sub_t = subdivide(centred, tris, max_edge)
    out = [(x, y, cone.forward(math.hypot(x, y), z)) for x, y, z in sub_v]
    return out, sub_t


# --------------------------------------------------------------------------
# STL I/O
# --------------------------------------------------------------------------
def read_stl(path: str) -> tuple[list, list]:
    with open(path, "rb") as f:
        data = f.read()
    soup = []
    if len(data) >= 84 and 84 + 50 * struct.unpack_from("<I", data, 80)[0] == len(data):
        for i in range(struct.unpack_from("<I", data, 80)[0]):
            v = struct.unpack_from("<12f", data, 84 + 50 * i)
            soup.append((v[3:6], v[6:9], v[9:12]))
    else:
        pts = [tuple(map(float, m)) for m in
               re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)]
        soup = [tuple(pts[i:i + 3]) for i in range(0, len(pts) - 2, 3)]
    index: dict = {}
    verts, tris = [], []
    for tri in soup:
        ids = []
        for p in tri:
            i = index.get(p)
            if i is None:
                i = index[p] = len(verts)
                verts.append(p)
            ids.append(i)
        if len(set(ids)) == 3:
            tris.append(tuple(ids))
    return verts, tris


def write_stl(path: str, verts: list, tris: list) -> None:
    with open(path, "wb") as f:
        f.write(b"nonplanar-conical".ljust(80, b"\0") + struct.pack("<I", len(tris)))
        for a, b, c in tris:
            pa, pb, pc = verts[a], verts[b], verts[c]
            ux, uy, uz = (pb[i] - pa[i] for i in range(3))
            vx, vy, vz = (pc[i] - pa[i] for i in range(3))
            n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
            f.write(struct.pack("<12fH", n[0] / ln, n[1] / ln, n[2] / ln, *pa, *pb, *pc, 0))


# --------------------------------------------------------------------------
# G-code: map back onto cones
# --------------------------------------------------------------------------
def _num(v: float, digits: int) -> str:
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _words(code: str) -> dict:
    out = {}
    for w in code.split()[1:]:
        try:
            out[w[0].upper()] = float(w[1:])
        except (ValueError, IndexError):
            raise ConicalError(f"Unknown G-code parameter '{w}' in '{code.strip()}'.")
    return out


def _region(lines: list) -> tuple[int, int]:
    """[start, end) of the layer section: first ;LAYER_CHANGE up to the custom
    end G-code that follows the last layer."""
    starts = [i for i, l in enumerate(lines) if l.startswith(";LAYER_CHANGE")]
    if not starts:
        raise ConicalError("No ';LAYER_CHANGE' found in the G-code - is this OrcaSlicer G-code?")
    end = len(lines)
    for i in range(starts[-1], len(lines)):
        if lines[i].startswith(";TYPE:Custom") or lines[i].startswith("; EXECUTABLE_BLOCK_END"):
            end = i
            break
    return starts[0], end


def detect_axis(lines: list) -> tuple[float, float]:
    """Cone axis = centre of the XY bounding box of the part's extrusions
    (the prepare step put the axis at the bounding box centre of the mesh)."""
    start, end = _region(lines)
    x = y = e = 0.0
    relative = False
    rel_e = False
    feature = ""
    bx0 = by0 = math.inf
    bx1 = by1 = -math.inf
    for i, line in enumerate(lines[:end]):
        if line.startswith(";TYPE:"):
            feature = line[6:].strip().lower()
            continue
        code = line.split(";", 1)[0].strip()
        if not code:
            continue
        cmd = code.split(None, 1)[0].upper()
        if cmd in ("G90", "G91"):
            relative = cmd == "G91"
        elif cmd in ("M82", "M83"):
            rel_e = cmd == "M83"
        elif cmd == "G92":
            e = _words(code).get("E", e)
        elif cmd in ("G0", "G1"):
            w = _words(code)
            nx = (x + w["X"] if relative else w["X"]) if "X" in w else x
            ny = (y + w["Y"] if relative else w["Y"]) if "Y" in w else y
            de = 0.0
            if "E" in w:
                de = w["E"] if rel_e else w["E"] - e
                e += de
            # i >= start: a purge line in the start G-code is not the part.
            if (i >= start and de > 0 and (nx, ny) != (x, y)
                    and not feature.startswith(AXIS_IGNORED_FEATURES)):
                bx0, bx1 = min(bx0, x, nx), max(bx1, x, nx)
                by0, by1 = min(by0, y, ny), max(by1, y, ny)
            x, y = nx, ny
    if bx0 == math.inf:
        raise ConicalError("No extrusions of the part found in the G-code.")
    return (bx0 + bx1) / 2, (by0 + by1) / 2


def _gcode_setting(lines: list, key: str) -> str | None:
    prefix = f"; {key} = "
    for line in reversed(lines):
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def transform_gcode(lines: list, cone: Cone, axis: tuple[float, float] | None = None) -> list:
    """Return the G-code with every layer move mapped onto the cones.

    `lines` keep their line endings. Only the layer section is changed; start
    and end G-code pass through untouched.
    """
    if any(l.startswith(GCODE_TAG) for l in lines[:50]):
        raise ConicalError("This G-code has already been conically transformed.")
    start, end = _region(lines)
    ax, ay = axis if axis is not None else detect_axis(lines)

    # Input state is in sliced space, output state in real space.
    x = y = z = e = 0.0
    out_x = out_y = out_z = out_e = 0.0
    rel_xyz = False
    rel_e = False
    result = [lines[0], f"{GCODE_TAG}: angle={cone.angle_deg:g} z0={cone.z0:g} "
                        f"axis=({ax:.3f}, {ay:.3f})\n"] if lines else []

    def real(px, py, pz):
        return cone.inverse(math.hypot(px - ax, py - ay), pz)

    def emit(px, py, pz, de, feed, comment):
        nonlocal out_x, out_y, out_z, out_e
        parts = ["G1"]
        if rel_xyz:
            dx, dy, dz = px - out_x, py - out_y, pz - out_z
            if abs(dx) > 5e-4: parts.append("X" + _num(dx, 3))
            if abs(dy) > 5e-4: parts.append("Y" + _num(dy, 3))
            if abs(dz) > 5e-4: parts.append("Z" + _num(dz, 3))
        else:
            if abs(px - out_x) > 5e-4: parts.append("X" + _num(px, 3))
            if abs(py - out_y) > 5e-4: parts.append("Y" + _num(py, 3))
            if abs(pz - out_z) > 5e-4: parts.append("Z" + _num(pz, 3))
        if de is not None:
            out_e += de
            parts.append("E" + _num(de if rel_e else out_e, 5))
        if feed is not None:
            parts.append("F" + _num(feed, 3))
        out_x, out_y, out_z = px, py, pz
        if len(parts) > 1:
            result.append(" ".join(parts) + comment + "\n")

    for idx, line in enumerate(lines[1:], start=1):
        code, sep, rest = line.partition(";")
        code = code.strip()
        if not code or idx < start or idx >= end:
            # Outside the layer section we only track the machine state.
            if code:
                cmd = code.split(None, 1)[0].upper()
                if cmd in ("G0", "G1", "G92"):
                    w = _words(code)
                    add = rel_xyz and cmd != "G92"
                    x = x + w["X"] if add and "X" in w else w.get("X", x)
                    y = y + w["Y"] if add and "Y" in w else w.get("Y", y)
                    z = z + w["Z"] if add and "Z" in w else w.get("Z", z)
                    if "E" in w:
                        e = w["E"] if cmd == "G92" or not rel_e else e + w["E"]
                    out_x, out_y, out_z, out_e = x, y, z, e
                elif cmd == "G90": rel_xyz = False
                elif cmd == "G91": rel_xyz = True
                elif cmd == "M82": rel_e = False
                elif cmd == "M83": rel_e = True
            result.append(line)
            continue

        comment = (" ;" + rest.rstrip("\r\n")) if sep else ""
        cmd = code.split(None, 1)[0].upper()
        if cmd in ("G2", "G3"):
            raise ConicalError("Arcs (G2/G3) are not supported: please turn off 'Arc fitting' "
                               "and do not use the 'Spiral' Z-hop.")
        if cmd in ("G28", "G29") or (cmd == "G92" and any(k in code.upper() for k in "XYZ")):
            raise ConicalError(f"'{code}' inside the layers is not supported.")
        if cmd == "G92":
            w = _words(code)
            if "E" in w:
                e = out_e = w["E"]
            result.append(line)
            continue
        if cmd in ("G90", "G91", "M82", "M83"):
            rel_xyz = {"G90": False, "G91": True}.get(cmd, rel_xyz)
            rel_e = {"M82": False, "M83": True}.get(cmd, rel_e)
            result.append(line)
            continue
        if cmd not in ("G0", "G1"):
            result.append(line)
            continue

        w = _words(code)
        nx = (x + w["X"] if rel_xyz else w["X"]) if "X" in w else x
        ny = (y + w["Y"] if rel_xyz else w["Y"]) if "Y" in w else y
        nz = (z + w["Z"] if rel_xyz else w["Z"]) if "Z" in w else z
        de = None
        if "E" in w:
            de = w["E"] if rel_e else w["E"] - e
            e = e + de
        feed = w.get("F")

        if not any(k in w for k in "XYZ"):
            # Retraction / feed-rate only: physical filament length, not scaled.
            if de is not None:
                out_e += de
                if not rel_e:  # absolute E drifted from the input by the flow scaling
                    feed_s = "" if feed is None else " F" + _num(feed, 3)
                    result.append(f"G1 E{_num(out_e, 5)}{feed_s}{comment}\n")
                    continue
            result.append(line)
            continue

        length = math.hypot(nx - x, ny - y)
        if length < 1e-9:
            rz, flow = real(nx, ny, nz)
            emit(nx, ny, rz, None if de is None else (de * flow if de > 0 else de), feed, comment)
        else:
            ts = _split(lambda s: real(x + (nx - x) * s, y + (ny - y) * s, z + (nz - z) * s)[0],
                        length)
            prev = 0.0
            for i, s in enumerate(ts):
                px, py, pz = x + (nx - x) * s, y + (ny - y) * s, z + (nz - z) * s
                piece = None
                if de is not None:
                    piece = de * (s - prev)
                    if piece > 0:
                        m = (s + prev) / 2
                        piece *= real(x + (nx - x) * m, y + (ny - y) * m, z + (nz - z) * m)[1]
                first = i == 0
                emit(px, py, real(px, py, pz)[0], piece, feed if first else None, comment if first else "")
                prev = s
        x, y, z = nx, ny, nz
    return result


def _split(height, length: float) -> list:
    """Parameters 0 < s <= 1 at which to cut a move so that the real Z between
    cuts deviates less than GCODE_TOLERANCE_MM from a straight line."""
    n = max(1, math.ceil(length / GCODE_MAX_SEGMENT_MM))
    cuts = []

    def refine(a, za, b, zb, depth):
        m = (a + b) / 2
        zm = height(m)
        if depth < 12 and (b - a) * length > 0.05 and abs(zm - (za + zb) / 2) > GCODE_TOLERANCE_MM:
            refine(a, za, m, zm, depth + 1)
            refine(m, zm, b, zb, depth + 1)
        else:
            cuts.append(b)

    za = height(0.0)
    for k in range(n):
        a, b = k / n, (k + 1) / n
        zb = height(b)
        refine(a, za, b, zb, 0)
        za = zb
    return cuts


def transform_gcode_file(path: str, cone: Cone, out_path: str | None = None) -> str:
    with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        lines = f.readlines()
    result = transform_gcode(lines, cone)
    with open(out_path or path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.writelines(result)
    return result[1].strip()


def prepare_stl(path: str, angle_deg: float, z0: float, out_path: str | None = None) -> str:
    cone = Cone(angle_deg, z0)
    verts, tris = read_stl(path)
    v, t = conical_mesh(verts, tris, cone)
    base = os.path.splitext(path)[0]
    out = out_path or base + cone.name_suffix() + ".stl"
    write_stl(out, v, t)
    return out


# --------------------------------------------------------------------------
# OrcaSlicer plugin
# --------------------------------------------------------------------------
try:
    import orca  # only exists inside OrcaSlicer
except ImportError:
    orca = None

_PIPELINE = None  # the loaded pipeline capability; owns the cone angle setting


def _angle_from(capability) -> float:
    try:
        return float(json.loads(capability.get_config()).get("cone_angle_deg", DEFAULT_ANGLE_DEG))
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_ANGLE_DEG


def _first_float(value) -> float:
    return float(str(value).split(",")[0].strip())


if orca is not None:

    def _fail(message: str):
        return orca.ExecutionResult.failure(orca.PluginResult.FatalError, message)

    class ConicalLayers(orca.slicing.SlicingPipelineCapabilityBase):
        """Validates the plate while slicing and maps the exported G-code onto cones."""

        def get_name(self):
            return "Conical Layers"

        def get_default_config(self):
            return {"cone_angle_deg": DEFAULT_ANGLE_DEG}

        def on_load(self):
            global _PIPELINE
            _PIPELINE = self

        def execute(self, ctx):
            try:
                if ctx.step == orca.slicing.Step.posSlice and ctx.object is not None:
                    self._check(ctx)
                elif ctx.step == orca.slicing.Step.psGCodePostProcess and ctx.gcode_path:
                    return self._post_process(ctx)
            except ConicalError as exc:
                return _fail(str(exc))
            return orca.ExecutionResult.success()

        def _check(self, ctx):
            angle = _angle_from(self)
            z0 = _first_float(ctx.config_value("initial_layer_print_height"))
            mo = ctx.object.model_object()
            params = parse_name(mo.name)
            if params is None:
                raise ConicalError(
                    f"'{mo.name}' is not prepared for conical printing. Run Plugins > 'Prepare Conical' "
                    "first and import the STL it creates - or turn off the Slicing Pipeline "
                    "Plugin in the process profile.")
            if abs(params[0] - angle) > 1e-6 or abs(params[1] - z0) > 1e-6:
                raise ConicalError(
                    f"'{mo.name}' was prepared for {params[0]:g}° / first layer {params[1]:g} mm, "
                    f"but the settings are {angle:g}° / {z0:g} mm. Please prepare it again.")
            if len(ctx.print.objects()) != 1:
                raise ConicalError("Conical layers only work with exactly one object per plate.")
            for part in [*mo.instances(), *mo.volumes()]:
                if any(abs(a) > 1e-4 for a in part.rotation()) or \
                        any(abs(s - 1) > 1e-4 for s in part.scaling_factor()):
                    raise ConicalError(
                        f"'{mo.name}' was rotated or scaled after preparing. Please rotate/scale "
                        "the original and prepare it again.")
            if str(ctx.config_value("enable_arc_fitting")).lower() not in ("0", "false", "disabled", "none"):
                raise ConicalError("Please turn off 'Arc fitting'.")
            if "spiral" in str(ctx.config_value("z_hop_types")).lower():
                raise ConicalError("Please do not use the 'Spiral' Z-hop (use Normal or Slope).")
            if str(ctx.config_value("make_overhang_printable")).lower() in ("1", "true"):
                # It adds material to the deformed mesh, which would come out distorted.
                raise ConicalError("Please turn off 'Make overhangs printable'.")
            if str(ctx.config_value("spiral_mode")).lower() in ("1", "true"):
                raise ConicalError("Spiral vase mode is not supported with conical layers.")

        def _post_process(self, ctx):
            try:
                cone = Cone(_angle_from(self), _first_float(ctx.config_value("initial_layer_print_height")))
                info = transform_gcode_file(ctx.gcode_path, cone)
            except Exception as exc:
                # Never leave a planar G-code of a deformed part behind.
                with open(ctx.gcode_path, "w", encoding="utf-8") as f:
                    f.write(f"; nonplanar-conical ERROR: {exc}\n")
                raise
            return orca.ExecutionResult.success(info)

    class PrepareConical(orca.script.ScriptPluginCapabilityBase):
        """Writes a deformed STL of every object on the plate for import."""

        def get_name(self):
            return "Prepare Conical"

        def execute(self):
            try:
                return self._run()
            except ConicalError as exc:
                orca.host.ui.message(str(exc), title="Prepare Conical", icon="error")
                return _fail(str(exc))

        def _run(self):
            import numpy as np

            angle = _angle_from(_PIPELINE) if _PIPELINE is not None else DEFAULT_ANGLE_DEG
            bundle = orca.host.preset_bundle()
            cone = Cone(angle, _first_float(bundle.full_config_value("initial_layer_print_height")))
            written = []
            for mo in orca.host.model().objects():
                if parse_name(mo.name) is not None or mo.instance_count() == 0:
                    continue
                inst = mo.instance(0).matrix()
                verts, tris = [], []
                for vol in mo.volumes():
                    if not vol.is_model_part():
                        continue
                    mat = inst @ vol.matrix()
                    v = np.asarray(vol.mesh().vertices(), dtype=np.float64)
                    t = np.asarray(vol.mesh().triangles(), dtype=np.int64)
                    world = v @ mat[:3, :3].T + mat[:3, 3]
                    if np.linalg.det(mat[:3, :3]) < 0:
                        t = t[:, ::-1]
                    tris += (t + len(verts)).tolist()
                    verts += world.tolist()
                v2, t2 = conical_mesh(verts, tris, cone)
                name = re.sub(r"[^\w.-]+", "_", os.path.splitext(mo.name)[0]) or "object"
                name += cone.name_suffix() + ".stl"
                # Next to the source file if allowed (Orca asks once), else plugin storage.
                dirs = [os.path.dirname(mo.input_file)] if mo.input_file else []
                for d in dirs + [orca.host.plugin.storage()]:
                    try:
                        write_stl(os.path.join(d, name), v2, t2)
                    except Exception:
                        continue
                    written.append(os.path.join(d, name))
                    break
                else:
                    raise ConicalError(f"Could not save '{name}'.")
            if not written:
                orca.host.ui.message("No object (that is not already prepared) found on the plate.",
                                     title="Prepare Conical")
                return orca.ExecutionResult.skipped("nothing to prepare")
            orca.host.ui.message(
                f"Cone angle {angle:g}°, first layer {cone.z0:g} mm.\n\n"
                + "\n".join(written)
                + "\n\nNext: File > Import > STL, load this file, delete the original, pick a "
                  "process profile with the Slicing Pipeline Plugin 'Conical Layers' and "
                  "slice. The G-code preview shows the warped model - the exported G-code "
                  "is conical.",
                title="Prepare Conical")
            return orca.ExecutionResult.success("\n".join(written))

    @orca.plugin
    class NonplanarConical(orca.base):
        def register_capabilities(self):
            orca.register_capability(ConicalLayers)
            orca.register_capability(PrepareConical)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Conical layers for OrcaSlicer (CLI).")
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prepare", help="deform an STL for slicing")
    pp.add_argument("stl")
    pp.add_argument("-a", "--angle", type=float, default=DEFAULT_ANGLE_DEG)
    pp.add_argument("--z0", type=float, default=0.2, help="first layer height in mm (as set in Orca)")
    pp.add_argument("-o", "--output")
    pg = sub.add_parser("gcode", help="map G-code back onto cones (without -o: in place)")
    pg.add_argument("gcode")
    pg.add_argument("-a", "--angle", type=float, default=DEFAULT_ANGLE_DEG)
    pg.add_argument("--z0", type=float, help="default: read from the G-code config block")
    pg.add_argument("-o", "--output")
    args = p.parse_args(argv)
    try:
        if args.cmd == "prepare":
            print(prepare_stl(args.stl, args.angle, args.z0, args.output))
        else:
            z0 = args.z0
            if z0 is None:
                with open(args.gcode, encoding="utf-8", errors="replace") as f:
                    value = _gcode_setting(f.readlines(), "initial_layer_print_height")
                if value is None:
                    raise ConicalError("First layer height not found in the G-code, please pass --z0.")
                z0 = _first_float(value)
            print(transform_gcode_file(args.gcode, Cone(args.angle, z0), args.output))
    except ConicalError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
