"""Test geometry: solids of revolution written as STL (no dependencies)."""
import math
import struct


def revolve(profile, segments=96):
    """Revolve a (r, z) profile that starts and ends on the axis (r == 0).

    Returns (vertices, triangles) of a closed, outward-oriented mesh.
    """
    verts, ring_index = [], []
    for r, z in profile:
        if r == 0:
            ring_index.append([len(verts)] * segments)
            verts.append((0.0, 0.0, float(z)))
        else:
            ring_index.append(list(range(len(verts), len(verts) + segments)))
            for k in range(segments):
                a = 2 * math.pi * k / segments
                verts.append((r * math.cos(a), r * math.sin(a), float(z)))
    tris = []
    for lo, hi in zip(ring_index, ring_index[1:]):
        for k in range(segments):
            k2 = (k + 1) % segments
            a, b, c, d = lo[k], lo[k2], hi[k2], hi[k]
            if a != b:
                tris.append((a, b, c))
            if c != d:
                tris.append((a, c, d))
    return verts, tris


def mushroom():
    """Stem r=8, cap r=25 whose underside overhangs 60 degrees from vertical."""
    rise = 17 / math.tan(math.radians(60))
    return revolve([(0, 0), (8, 0), (8, 20), (25, 20 + rise), (25, 33), (0, 33)])


def write_stl(path, verts, tris):
    with open(path, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<3f", 0, 0, 0))
            for i in t:
                f.write(struct.pack("<3f", *verts[i]))
            f.write(b"\0\0")


if __name__ == "__main__":
    import sys
    write_stl(sys.argv[1], *mushroom())
