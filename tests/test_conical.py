import importlib
import math
import os
import sys
import tempfile
import types
import unittest
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import models  # noqa: E402
import nonplanar_conical as nc  # noqa: E402


def edges_balanced(tris):
    """Watertight + consistently oriented: every directed edge has its reverse."""
    directed = Counter()
    for a, b, c in tris:
        directed.update([(a, b), (b, c), (c, a)])
    return all(directed[(v, u)] == n for (u, v), n in directed.items())


def signed_volume(verts, tris):
    v = 0.0
    for a, b, c in tris:
        (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = verts[a], verts[b], verts[c]
        v += (x1 * (y2 * z3 - y3 * z2) - x2 * (y1 * z3 - y3 * z1) + x3 * (y1 * z2 - y2 * z1)) / 6
    return v


def moves(lines):
    """(x, y, z, e) after every G1 in absolute XYZ / relative E G-code."""
    x = y = z = 0.0
    out = []
    for line in lines:
        code = line.split(";")[0].split()
        if code and code[0] in ("G0", "G1"):
            w = {t[0]: float(t[1:]) for t in code[1:]}
            x, y, z = w.get("X", x), w.get("Y", y), w.get("Z", z)
            out.append((x, y, z, w.get("E")))
    return out


GCODE = """; header
;TYPE:Custom
G90
M83
G1 X100 Y100 Z5 F6000
G1 X90 E5
;LAYER_CHANGE
;Z:0.2
G1 X-10 Y0 F30000
G1 Z.2
;TYPE:Outer wall
G1 X10 Y0 E1.0
;LAYER_CHANGE
;Z:5
G1 Z5
G1 X-10 Y0 E2.0
G1 E-.8
;TYPE:Custom
G1 Z10
"""


class ConeTest(unittest.TestCase):
    def test_roundtrip_and_flow(self):
        cone = nc.Cone(15, 0.2)
        for r in (0, 0.5, 3, 20, 80):
            for z in (0, 0.1, 0.2, 0.3, 1, 5, 20, 60):
                zs = cone.forward(r, z)
                back, flow = cone.inverse(r, zs)
                self.assertAlmostEqual(back, z, places=9)
                self.assertIn(flow, (1.0, 0.5))
                self.assertLessEqual(back, zs + 1e-12)  # never above sliced height
        # far above the base the layers are true cones with unchanged flow
        self.assertAlmostEqual(cone.inverse(10, 30)[0], 30 - 10 * math.tan(math.radians(15)))
        self.assertEqual(cone.inverse(10, 30)[1], 1.0)
        # first layer stays planar
        self.assertEqual(cone.inverse(50, 0.2), (0.2, 1.0))

    def test_rejects_bad_parameters(self):
        with self.assertRaises(nc.ConicalError):
            nc.Cone(45, 0.2)
        with self.assertRaises(nc.ConicalError):
            nc.Cone(15, 0)

    def test_name_roundtrip(self):
        self.assertEqual(nc.parse_name("mushroom" + nc.Cone(12.5, 0.25).name_suffix() + ".stl"), (12.5, 0.25))
        self.assertIsNone(nc.parse_name("mushroom.stl"))


class MeshTest(unittest.TestCase):
    def test_subdivide_keeps_mesh_closed_and_volume(self):
        verts, tris = models.mushroom()
        v2, t2 = nc.subdivide(verts, tris, 2.0)
        self.assertTrue(edges_balanced(tris))
        self.assertTrue(edges_balanced(t2))
        self.assertAlmostEqual(signed_volume(v2, t2), signed_volume(verts, tris), places=3)
        longest = max(math.dist(v2[a], v2[b]) for t in t2 for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))
        self.assertLessEqual(longest, 2.0 + 1e-9)

    def test_conical_mesh_is_centred_and_deformed(self):
        verts, tris = models.mushroom()
        verts = [(x + 40, y - 7, z + 3) for x, y, z in verts]  # off-centre, lifted
        cone = nc.Cone(15, 0.2)
        v2, t2 = nc.conical_mesh(verts, tris, cone, max_edge=2.0)
        self.assertTrue(edges_balanced(t2))
        xs, ys, zs = zip(*v2)
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, 0, places=6)
        self.assertAlmostEqual((min(ys) + max(ys)) / 2, 0, places=6)
        self.assertAlmostEqual(min(zs), 0, places=6)
        self.assertAlmostEqual(max(zs), 33 + 25 * math.tan(math.radians(15)), places=3)
        for x, y, z in v2:  # every vertex maps back onto the original solid's height range
            self.assertLessEqual(cone.inverse(math.hypot(x, y), z)[0], 33 + 1e-6)

    def test_stl_roundtrip(self):
        verts, tris = models.mushroom()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mushroom.stl")
            models.write_stl(path, verts, tris)
            out = nc.prepare_stl(path, 15, 0.2)
            self.assertTrue(out.endswith("mushroom_conical_a15_z0.2.stl"))
            v2, t2 = nc.read_stl(out)
            self.assertTrue(edges_balanced(t2))


class GcodeTest(unittest.TestCase):
    def setUp(self):
        self.cone = nc.Cone(15, 0.2)
        self.lines = GCODE.splitlines(keepends=True)

    def test_layers_follow_the_cone(self):
        out = nc.transform_gcode(self.lines, self.cone)
        self.assertTrue(out[1].startswith(nc.GCODE_TAG))
        self.assertIn("axis=(0.000, 0.000)", out[1])  # purge line (Custom) is ignored
        start = next(i for i, l in enumerate(out) if l.startswith(";LAYER_CHANGE"))
        end = max(i for i, l in enumerate(out) if l.startswith(";TYPE:Custom"))
        self.assertEqual(out[2:start], self.lines[1:start - 1])  # start G-code untouched
        self.assertEqual(out[end:], self.lines[-2:])  # end G-code untouched
        pts = moves(out[start:end])
        self.assertGreater(len(pts), 20)  # long moves were subdivided
        for x, y, z, _ in pts:
            r = math.hypot(x, y)
            if z > 0.25:  # layer 2 (sliced Z=5) lies on its cone
                self.assertAlmostEqual(z, self.cone.inverse(r, 5)[0], delta=nc.GCODE_TOLERANCE_MM)
        # the top layer passes over the axis: its peak must be the highest point
        self.assertAlmostEqual(max(p[2] for p in pts), self.cone.inverse(0, 5)[0],
                               delta=nc.GCODE_TOLERANCE_MM)

    def test_extrusion_is_conserved_with_flow_factor(self):
        out = nc.transform_gcode(self.lines, self.cone)
        start = next(i for i, l in enumerate(out) if l.startswith(";LAYER_CHANGE"))
        e = [p[3] for p in moves(out[start:]) if p[3] is not None]
        # layer 1 is planar (flow 1): 1.0; layer 2 mixes base (0.5) and cone (1.0)
        total_layer2 = sum(v for v in e if v > 0) - 1.0
        expected = 0.0
        n = 20000
        for k in range(n):
            x = 10 - 20 * (k + 0.5) / n
            expected += 2.0 / n * self.cone.inverse(abs(x), 5)[1]
        self.assertAlmostEqual(total_layer2, expected, delta=0.02)
        self.assertIn(-0.8, e)  # retraction untouched

    def test_absolute_extrusion_matches_relative(self):
        rel = nc.transform_gcode(self.lines, self.cone)
        absolute = [l.replace("M83", "M82") for l in self.lines]
        absolute = [l.replace("G1 X10 Y0 E1.0", "G1 X10 Y0 E6.0")
                     .replace("G1 X-10 Y0 E2.0", "G1 X-10 Y0 E8.0")
                     .replace("G1 E-.8", "G1 E7.2") for l in absolute]
        out = nc.transform_gcode(absolute, self.cone)
        e_rel = [p[3] for p in moves(rel) if p[3] is not None]
        e_abs = [p[3] for p in moves(out) if p[3] is not None]
        cum, prev = [], 0.0
        for v in e_abs:
            cum.append(v - prev)
            prev = v
        self.assertEqual(len(cum), len(e_rel))
        for a, b in zip(cum, e_rel):
            self.assertAlmostEqual(a, b, places=4)

    def test_axis_ignores_skirt_and_follows_part(self):
        lines = [l.replace("X-10 Y0", "X20 Y30").replace("X10 Y0", "X40 Y30") for l in self.lines]
        lines.insert(lines.index(";TYPE:Outer wall\n"), ";TYPE:Skirt\nG1 X-80 Y-80 E3\nG1 X20 Y30\n")
        lines = "".join(lines).splitlines(keepends=True)
        self.assertEqual(nc.detect_axis(lines), (30.0, 30.0))
        lines.remove(";TYPE:Custom\n")  # purge line in an untagged start G-code
        self.assertEqual(nc.detect_axis(lines), (30.0, 30.0))

    def test_refuses_arcs_and_double_transform(self):
        arcs = [l.replace("G1 X10 Y0 E1.0", "G2 X10 Y0 I10 J0 E1.0") for l in self.lines]
        with self.assertRaises(nc.ConicalError):
            nc.transform_gcode(arcs, self.cone)
        once = nc.transform_gcode(self.lines, self.cone)
        with self.assertRaises(nc.ConicalError):
            nc.transform_gcode(once, self.cone)

    def test_cli_reads_first_layer_from_config_block(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.gcode")
            with open(path, "w") as f:
                f.write(GCODE + "; initial_layer_print_height = 0.25\n")
            self.assertEqual(nc.main(["gcode", path, "-a", "10"]), 0)
            with open(path) as f:
                self.assertIn("angle=10 z0=0.25", f.read())


# --------------------------------------------------------------------------
# Plugin glue against a stand-in for OrcaSlicer's embedded `orca` module
# --------------------------------------------------------------------------
class Result:
    def __init__(self, status, message=""):
        self.status, self.message = status, message


def fake_orca(model=None, z0="0.2"):
    orca = types.ModuleType("orca")
    orca.PluginResult = types.SimpleNamespace(FatalError="fatal")
    orca.ExecutionResult = types.SimpleNamespace(
        success=lambda message="", data="": Result("ok", message),
        skipped=lambda message="": Result("skipped", message),
        failure=lambda status, message, data="": Result(status, message))

    class Base:
        def get_config(self):
            return getattr(self, "_config", "{}")

    orca.slicing = types.SimpleNamespace(
        SlicingPipelineCapabilityBase=Base,
        Step=types.SimpleNamespace(posSlice="posSlice", psGCodePostProcess="post"))
    orca.script = types.SimpleNamespace(ScriptPluginCapabilityBase=Base)
    orca.base = object
    orca.plugin = lambda cls: cls
    orca.registered = []
    orca.register_capability = orca.registered.append
    orca.messages = []
    orca.host = types.SimpleNamespace(
        ui=types.SimpleNamespace(message=lambda text, **kw: orca.messages.append(text)),
        model=lambda: model,
        preset_bundle=lambda: types.SimpleNamespace(full_config_value=lambda k: z0),
        plugin=types.SimpleNamespace(storage=lambda: tempfile.gettempdir()))
    return orca


class Part:
    def __init__(self, rotation=(0, 0, 0), scale=(1, 1, 1)):
        self._r, self._s = rotation, scale

    def rotation(self):
        return self._r

    def scaling_factor(self):
        return self._s


def slice_ctx(name, part=None, objects=1, config=None):
    cfg = {"initial_layer_print_height": "0.2", "enable_arc_fitting": "disabled",
           "z_hop_types": "Auto Lift", "spiral_mode": "0", **(config or {})}
    mo = types.SimpleNamespace(name=name, instances=lambda: [part or Part()], volumes=lambda: [Part()])
    obj = types.SimpleNamespace(model_object=lambda: mo)
    return types.SimpleNamespace(step="posSlice", object=obj, gcode_path="",
                                 print=types.SimpleNamespace(objects=lambda: [obj] * objects),
                                 config_value=cfg.get)


class PluginTest(unittest.TestCase):
    def load(self, **kw):
        sys.modules["orca"] = self.orca = fake_orca(**kw)
        self.addCleanup(importlib.reload, nc)        # runs last: back to the CLI module
        self.addCleanup(sys.modules.pop, "orca", None)
        return importlib.reload(nc)

    def test_registers_both_capabilities(self):
        mod = self.load()
        mod.NonplanarConical().register_capabilities()
        self.assertEqual([c.__name__ for c in self.orca.registered], ["ConicalLayers", "PrepareConical"])

    def test_slice_validation(self):
        mod = self.load()
        cap = mod.ConicalLayers()
        good = "mushroom_conical_a15_z0.2.stl"
        self.assertEqual(cap.execute(slice_ctx(good)).status, "ok")
        for ctx, why in [
            (slice_ctx("mushroom.stl"), "not prepared for conical printing"),
            (slice_ctx("mushroom_conical_a10_z0.2.stl"), "Please prepare it again"),
            (slice_ctx(good, config={"initial_layer_print_height": "0.3"}), "Please prepare it again"),
            (slice_ctx(good, objects=2), "exactly one object"),
            (slice_ctx(good, part=Part(rotation=(0, 0, 0.5))), "rotated or scaled"),
            (slice_ctx(good, part=Part(scale=(1.2, 1.2, 1.2))), "rotated or scaled"),
            (slice_ctx(good, config={"enable_arc_fitting": "1"}), "Arc fitting"),
            (slice_ctx(good, config={"z_hop_types": "Spiral Lift"}), "Spiral"),
            (slice_ctx(good, config={"make_overhang_printable": "1"}), "Make overhangs printable"),
        ]:
            res = cap.execute(ctx)
            self.assertEqual(res.status, "fatal", why)
            self.assertIn(why, res.message)

    def test_angle_comes_from_capability_config(self):
        mod = self.load()
        cap = mod.ConicalLayers()
        cap._config = '{"cone_angle_deg": 10}'
        self.assertEqual(cap.execute(slice_ctx("mushroom_conical_a10_z0.2.stl")).status, "ok")

    def test_post_process_transforms_or_blanks_file(self):
        mod = self.load()
        cap = mod.ConicalLayers()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.gcode")
            with open(path, "w") as f:
                f.write(GCODE)
            ctx = types.SimpleNamespace(step="post", object=None, print=None, gcode_path=path,
                                        config_value={"initial_layer_print_height": "0.2"}.get)
            self.assertEqual(cap.execute(ctx).status, "ok")
            with open(path) as f:
                self.assertIn(mod.GCODE_TAG, f.read())
            # second run (already transformed) must fail and leave nothing printable
            self.assertEqual(cap.execute(ctx).status, "fatal")
            with open(path) as f:
                self.assertEqual([l for l in f if not l.startswith(";")], [])

    def test_prepare_writes_stl_next_to_source(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")
        verts, tris = models.mushroom()
        mesh = types.SimpleNamespace(vertices=lambda: np.array(verts, dtype=np.float32),
                                     triangles=lambda: np.array(tris, dtype=np.int32))
        with tempfile.TemporaryDirectory() as d:
            vol = types.SimpleNamespace(is_model_part=lambda: True, mesh=lambda: mesh,
                                        matrix=lambda: np.eye(4))
            inst = types.SimpleNamespace(matrix=lambda: np.diag([1.0, 1.0, 1.0, 1.0]))
            mo = types.SimpleNamespace(name="Mushroom.stl", input_file=os.path.join(d, "Mushroom.stl"),
                                       instance_count=lambda: 1, instance=lambda i: inst,
                                       volumes=lambda: [vol])
            mod = self.load(model=types.SimpleNamespace(objects=lambda: [mo]))
            res = mod.PrepareConical().execute()
            self.assertEqual(res.status, "ok", self.orca.messages)
            out = os.path.join(d, "Mushroom_conical_a15_z0.2.stl")
            self.assertEqual(res.message, out)
            v2, t2 = nc.read_stl(out)
            self.assertTrue(edges_balanced(t2))


if __name__ == "__main__":
    unittest.main()
