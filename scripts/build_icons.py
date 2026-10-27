"""Generate native app/document icons from the upstream PyMOL SVG artwork."""
import argparse
import os
import sys
import subprocess
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5 import QtCore, QtGui, QtSvg, QtWidgets


def render(svg, size, label=None):
    image = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.scale(size / 1024, size / 1024)
    renderer = QtSvg.QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise RuntimeError("Invalid upstream SVG icon")
    if label:
        page = QtGui.QPainterPath()
        page.moveTo(190, 72)
        page.lineTo(670, 72)
        page.lineTo(852, 254)
        page.lineTo(852, 928)
        page.quadTo(852, 960, 820, 960)
        page.lineTo(190, 960)
        page.quadTo(158, 960, 158, 928)
        page.lineTo(158, 104)
        page.quadTo(158, 72, 190, 72)
        painter.setBrush(QtGui.QColor("#f7fafc"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#a5b3bf"), 12))
        painter.drawPath(page)
        fold = QtGui.QPolygonF([QtCore.QPointF(670, 72), QtCore.QPointF(670, 254), QtCore.QPointF(852, 254)])
        painter.setBrush(QtGui.QColor("#dbe6ef"))
        painter.drawPolygon(fold)
        renderer.render(painter, QtCore.QRectF(228, 285, 550, 480))
        painter.setPen(QtGui.QColor("#16415f"))
        font = QtGui.QFont("Helvetica Neue", 92, QtGui.QFont.Bold)
        painter.setFont(font)
        painter.drawText(QtCore.QRectF(180, 790, 650, 135), QtCore.Qt.AlignCenter, label)
    else:
        renderer.render(painter, QtCore.QRectF(24, 24, 976, 976))
    painter.end()
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("svg", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    application = QtWidgets.QApplication([])
    args.destination.mkdir(parents=True, exist_ok=True)
    for name, label in [("PyMOL", None), ("PDB", "PDB"), ("CIF", "CIF"), ("PSE", "PSE"), ("MOL", "MOL/SDF"), ("MOL2", "MOL2")]:
        iconset = args.destination / (name + ".iconset")
        iconset.mkdir(exist_ok=True)
        for size in [16, 32, 128, 256, 512]:
            for scale, suffix in [(1, ""), (2, "@2x")]:
                image = render(args.svg, size * scale, label)
                if not image.save(str(iconset / ("icon_%dx%d%s.png" % (size, size, suffix)))):
                    raise RuntimeError("Could not save icon image")
        if sys.platform == "darwin":
            subprocess.run(["/usr/bin/iconutil", "-c", "icns", "-o", str(args.destination / (name + ".icns")), str(iconset)], check=True)
        render(args.svg, 512, label).save(str(args.destination / (name + ".png")))
        if not render(args.svg, 256, label).save(str(args.destination / (name + ".ico")), "ICO"):
            raise RuntimeError("Could not save Windows icon")
    render(args.svg, 512, "PDB").save(str(args.destination / "document-preview.png"))
    application.quit()


if __name__ == "__main__":
    main()
