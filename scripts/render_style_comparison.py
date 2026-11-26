"""Render same-camera style comparisons with our own controls and bundled 1HPV.

Uses actual PyMOL Ray output, then Qt to arrange labelled panels. No downloaded
reference images or third-party style implementation is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymol
import pymol2
from pymol.Qt import QtCore, QtGui, QtWidgets
from pymol_ai_assistant.graphics import GraphicsControls, PRESETS


def font(pixels, bold=False):
    value = QtGui.QFont("Arial")
    value.setPixelSize(pixels)
    value.setBold(bold)
    return value


def sheet(path, title, subtitle, panels, columns, footer):
    margin, gap, tile_w, tile_h = 24, 16, 420, 382
    rows = (len(panels) + columns - 1) // columns
    width = margin * 2 + columns * tile_w + (columns - 1) * gap
    height = 118 + rows * tile_h + (rows - 1) * gap + 60
    canvas = QtGui.QImage(width, height, QtGui.QImage.Format_RGB32)
    canvas.fill(QtGui.QColor("#edf1f4"))
    painter = QtGui.QPainter(canvas)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    painter.setPen(QtGui.QColor("#152b39")); painter.setFont(font(28, True))
    painter.drawText(QtCore.QRect(24, 20, width - 48, 38), QtCore.Qt.AlignLeft, title)
    painter.setFont(font(16)); painter.setPen(QtGui.QColor("#526673"))
    painter.drawText(QtCore.QRect(24, 65, width - 48, 38), QtCore.Qt.AlignLeft, subtitle)
    for index, (image_path, label, caption, added) in enumerate(panels):
        x, y = margin + index % columns * (tile_w + gap), 118 + index // columns * (tile_h + gap)
        painter.setPen(QtCore.Qt.NoPen); painter.setBrush(QtGui.QColor("white"))
        painter.drawRoundedRect(QtCore.QRectF(x, y, tile_w, tile_h), 12, 12)
        painter.setPen(QtGui.QColor("#152b39")); painter.setFont(font(21, True))
        painter.drawText(QtCore.QRect(x + 16, y + 12, tile_w - 96, 29), QtCore.Qt.AlignLeft, label)
        painter.setFont(font(11, True)); painter.setPen(QtGui.QColor("#267066" if added else "#758490"))
        painter.drawText(QtCore.QRect(x + tile_w - 90, y + 17, 75, 20), QtCore.Qt.AlignRight, "NEW" if added else "EXISTING")
        image = QtGui.QImage(str(image_path))
        assert not image.isNull(), image_path
        image_rect = QtCore.QRect(x + 10, y + 45, tile_w - 20, 278)
        painter.drawImage(image_rect, image)
        painter.setFont(font(14)); painter.setPen(QtGui.QColor("#526673"))
        painter.drawText(QtCore.QRect(x + 16, y + 327, tile_w - 32, 45), QtCore.Qt.TextWordWrap, caption)
    painter.setFont(font(14)); painter.setPen(QtGui.QColor("#526673"))
    painter.drawText(QtCore.QRect(24, height - 40, width - 48, 30), QtCore.Qt.AlignLeft, footer)
    painter.end()
    assert canvas.save(str(path)), path


def atom_colors(cmd, selection="all"):
    result = []
    cmd.iterate(selection, "values.append((model, index, color))", space={"values": result})
    return result


def setup_scene(cmd, structure):
    cmd.load(str(structure), "publication_demo")
    cmd.hide("everything")
    cmd.show("cartoon", "polymer")
    cmd.show("sticks", "organic")
    cmd.color("marine", "chain A")
    cmd.color("salmon", "chain B")
    cmd.color("forest", "organic and elem C")
    cmd.color("blue", "organic and elem N")
    cmd.color("red", "organic and elem O")
    cmd.set("stick_radius", .22)
    cmd.set("orthoscopic", 1)
    cmd.set("antialias", 1)
    cmd.bg_color("white")
    cmd.set("ray_opaque_background", 1)
    cmd.orient()
    cmd.turn("x", -15); cmd.turn("y", -10); cmd.zoom("all", 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "preview")
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    structure = Path(pymol.__file__).parent / "pymol_path/data/tut/1hpv.pdb"
    captions = {
        "simple": "Balanced everyday lighting; no contours or cast shadows.",
        "soft": "Matte light with surface crevice shading; original settings.",
        "full": "Original stronger depth, cast shadows and highlights.",
        "flat": "Original uniform colors with minimal lighting cues.",
        "publication": "Original gentle light and restrained contours on white.",
        "illustration": "Original flat diagram colors with dark contours.",
        "paper_cutout": "Added matte, softly shaded paper appearance with charcoal contours.",
        "studio": "Added directional illumination and polished depth cues.",
    }
    palette_captions = {
        "original": "Same blue/coral atom colors as the eight-preset comparison.",
        "pastel_chains": "Optional muted categorical colors, applied per polymer chain.",
        "contrast_chains": "Optional stronger categorical colors, applied per polymer chain.",
        "residue_gradient": "Optional teal-to-amber residue order; not confidence or a property map.",
    }
    report = {"structure": "bundled Open-Source PyMOL tutorial 1HPV", "structureSHA256": hashlib.sha256(structure.read_bytes()).hexdigest(),
              "engine": "official Open-Source PyMOL", "rendering": "actual PyMOL Ray; 720 x 500 px; antialias=1; white background; orthographic", "presets": {}, "palettes": {}, "surfacePresets": {}}
    with pymol2.PyMOL() as engine:
        cmd = engine.cmd; setup_scene(cmd, structure); graphics = GraphicsControls(cmd)
        camera, colors = list(cmd.get_view()), atom_colors(cmd)
        positions = cmd.get_coords().copy()
        representations = {rep: cmd.count_atoms("rep " + rep) for rep in ["cartoon", "sticks", "lines", "surface", "spheres"]}
        report["camera"] = camera
        preset_panels = []
        for key in PRESETS:
            graphics.apply_preset(key)
            assert all(abs(a-b)<1e-6 for a,b in zip(camera,cmd.get_view()))
            assert atom_colors(cmd) == colors and (cmd.get_coords() == positions).all()
            assert representations == {rep: cmd.count_atoms("rep " + rep) for rep in representations}
            path = output / ("preset-" + key + ".png")
            cmd.png(str(path), 720, 500, ray=1, quiet=1)
            report["presets"][key] = graphics.state()
            preset_panels.append((path, PRESETS[key][0], captions[key], key in {"paper_cutout", "studio"}))
            print("Rendered", key, flush=True)
        graphics.apply_preset("paper_cutout")
        palette_panels = []
        nonpolymers = atom_colors(cmd, "not polymer")
        for key, label in [("original", "Current colors"), ("pastel_chains", "Pastel chains"), ("contrast_chains", "Contrast chains"), ("residue_gradient", "Residue gradient")]:
            if key != "original":
                report["palettes"][key] = graphics.apply_palette(key, "polymer")
            assert atom_colors(cmd, "not polymer") == nonpolymers
            assert all(abs(a-b)<1e-6 for a,b in zip(camera,cmd.get_view()))
            assert (cmd.get_coords() == positions).all()
            path = output / ("palette-" + key + ".png")
            cmd.png(str(path), 720, 500, ray=1, quiet=1)
            palette_panels.append((path, label, palette_captions[key], key != "original"))
            print("Rendered palette", key, flush=True)
        graphics.apply_palette("pastel_chains", "polymer")
        graphics.apply_preset("paper_cutout")
        cmd.save(str(output / "publication-preview.pse"))
        cmd.hide("cartoon", "polymer"); cmd.show("surface", "polymer")
        surface_panels = []
        for key, caption in [("soft", "Original soft matte surface shading."), ("paper_cutout", "New matte contours, without cast shadows."), ("studio", "New sculpted surface depth and highlights.")]:
            graphics.apply_preset(key)
            path = output / ("surface-" + key + ".png")
            cmd.png(str(path), 720, 500, ray=1, quiet=1)
            surface_panels.append((path, PRESETS[key][0], caption, key != "soft"))
            report["surfacePresets"][key] = graphics.state()
        report.update(presetCameraPreserved=True,presetAtomColorsPreserved=True,presetRepresentationsPreserved=True,
                      atomCoordinatesPreserved=True,paletteNonpolymerColorsPreserved=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["style-comparison"])
    sheet(output / "preset-comparison.png", "Eight lighting presets · same camera and colors",
          "Original six retained + Paper Cutout and Studio. Actual Ray renders of the bundled 1HPV structure.",
          preset_panels, 4, "Lighting presets preserve molecular colors, camera orientation, coordinates and representations. All panels use white backgrounds.")
    sheet(output / "palette-comparison.png", "Optional polymer colors · separate from lighting",
          "Paper Cutout lighting in every panel. Ligand atom colors and camera are unchanged.",
          palette_panels, 4, "Palettes recolor polymers only when explicitly chosen. These colors do not encode confidence, B-factor, hydrophobicity or experimental data.")
    sheet(output / "surface-comparison.png", "Surface lighting · compare the depth cues",
          "Same molecular surface, pastel chain colors and camera. Surface display was chosen explicitly for this comparison.",
          surface_panels, 3, "Studio shadows and surface depth are strongest in Ray. Applying a lighting preset never switches a cartoon into a surface.")
    (output / "render-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Saved same-camera sheets and publication-preview.pse", flush=True)


if __name__ == "__main__":
    main()
