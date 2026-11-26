"""Render the actual translucent-protein focus option, with unchanged camera/colors."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from render_style_comparison import (
    QtWidgets, QtGui, GraphicsControls, atom_colors, pymol, pymol2,
    setup_scene, sheet,
)
from pymol_ai_assistant.focus import apply_focus


def scalar_values(cmd):
    result = []
    cmd.iterate("all", "values.append((model, index, b, q))", space={"values": result})
    return result


def atom_setting(cmd, selection, name):
    values = []
    cmd.iterate(selection, "values.append(s." + name + ")", space={"values": values})
    return values


def image_measurements(path):
    image = QtGui.QImage(str(path))
    assert not image.isNull()
    visible, saturation = 0, 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            values = color.red(), color.green(), color.blue()
            if min(values) < 245:
                visible += 1
                saturation += max(values) - min(values)
    return {"nonWhitePixels": visible, "summedColorChroma": saturation,
            "width": image.width(), "height": image.height()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "preview-0.7.1")
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    structure = Path(pymol.__file__).parent / "pymol_path/data/tut/1hpv.pdb"
    report = {
        "structure": "bundled 1HPV tutorial structure",
        "structureSHA256": hashlib.sha256(structure.read_bytes()).hexdigest(),
        "lighting": "existing Soft preset; no outlines",
        "rendering": "actual PyMOL Ray; white background; orthographic; antialias=1; 720 x 500 px per panel",
        "proteinTransparency": .70,
        "panels": {},
    }
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["focus-comparison"])
    with tempfile.TemporaryDirectory(prefix="pymol-focus-render-") as temporary:
        folder = Path(temporary)
        with pymol2.PyMOL() as engine:
            cmd = engine.cmd
            setup_scene(cmd, structure)
            graphics = GraphicsControls(cmd)
            graphics.apply_preset("soft")
            camera, colors = list(cmd.get_view()), atom_colors(cmd)
            coordinates, values = cmd.get_coords().copy(), scalar_values(cmd)
            lighting = graphics.state()
            report["camera"] = camera
            report["graphicsState"] = lighting
            panels = []
            cases = [
                ("original", None, "Original view", "Opaque protein cartoon and the ligand, using the existing chain and element colors.", False),
                ("ligand", "organic", "Ligand focus", "70% transparent protein; the ligand remains fully opaque in sticks.", True),
                ("ligand_asp25", "organic or (polymer.protein and resi 25)", "Ligand + Asp25", "Same focus plus opaque whole-residue sticks for Asp25 in both protein chains.", True),
            ]
            for key, selection, title, caption, added in cases:
                focus = apply_focus(cmd, selection) if selection else None
                assert atom_colors(cmd) == colors
                assert (cmd.get_coords() == coordinates).all()
                assert scalar_values(cmd) == values
                assert all(abs(a-b) < 1e-6 for a,b in zip(camera,cmd.get_view()))
                assert graphics.state() == lighting
                if selection:
                    assert cmd.count_atoms("polymer.protein and rep cartoon") == cmd.count_atoms("polymer.protein")
                    assert all(abs(value - .70) < .001 for value in atom_setting(cmd, "polymer.protein", "cartoon_transparency"))
                    assert cmd.count_atoms("organic and rep sticks") == cmd.count_atoms("organic")
                    assert all(value == 0 for value in atom_setting(cmd, "organic", "stick_transparency"))
                path = folder / (key + ".png")
                cmd.png(str(path), 720, 500, ray=1, quiet=1)
                report["panels"][key] = {"selection": selection, "focusResult": focus, "image": image_measurements(path)}
                panels.append((path, title, caption, added))
                print("Rendered", key, flush=True)
            report["asp25AtomCount"] = cmd.count_atoms("polymer.protein and resi 25")
            report["asp25StickAtomCount"] = cmd.count_atoms("polymer.protein and resi 25 and rep sticks")
            assert report["asp25AtomCount"] == report["asp25StickAtomCount"] > 0
            # Transparency lowers the visible scaffold chroma; adding opaque
            # residue sticks raises it again, without changing any atom colors.
            assert report["panels"]["ligand"]["image"]["summedColorChroma"] < report["panels"]["original"]["image"]["summedColorChroma"]
            assert report["panels"]["ligand_asp25"]["image"]["summedColorChroma"] > report["panels"]["ligand"]["image"]["summedColorChroma"]
            cmd.save(str(output / "focus-preview.pse"))
        sheet(output / "focus-comparison.png", "Transparent protein · opaque molecular focus",
              "70% protein transparency with existing Soft lighting. Same camera, same atom colors; actual Ray renders of 1HPV.",
              panels, 3,
              "Focus changes protein representations and transparency. Atom colors, coordinates, B-factors, camera and lighting are retained.")
    report.update(atomColorsPreserved=True,coordinatesPreserved=True,bFactorsAndOccupanciesPreserved=True,
                  cameraPreserved=True,lightingPreserved=True,ligandOpaque=True,asp25WholeResiduesOpaque=True,
                  renderedScaffoldFades=True,renderedResidueHighlightAddsContrast=True)
    (output / "focus-render-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Saved focus comparison and starter session.", flush=True)


if __name__ == "__main__":
    main()
