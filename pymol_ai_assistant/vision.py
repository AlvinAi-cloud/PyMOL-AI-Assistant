"""On-demand capture of this application's window or molecular viewport."""
import base64
from pymol.Qt import QtCore, QtGui


def capture_view(window, target):
    widget = window.pymolwidget
    widget.repaint()
    framebuffer = widget.grabFramebuffer() if hasattr(widget, "grabFramebuffer") else widget.grabFrameBuffer()
    if framebuffer.isNull():
        raise ValueError("The molecular viewport could not be captured. Make the PyMOL window visible and retry.")
    if target == "viewport":
        image = framebuffer
    else:
        image = window.grab().toImage()
        painter = QtGui.QPainter(image)
        point = widget.mapTo(window, QtCore.QPoint(0, 0))
        painter.drawImage(QtCore.QRect(point, widget.size()), framebuffer)
        painter.end()
    image = image.scaled(1440, 1080, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    data = QtCore.QByteArray()
    buffer = QtCore.QBuffer(data)
    buffer.open(QtCore.QIODevice.WriteOnly)
    if not image.save(buffer, "JPEG", 80):
        raise ValueError("Could not encode the inspection image.")
    buffer.close()
    encoded = base64.b64encode(bytes(data)).decode("ascii")
    if len(encoded) > 1_000_000:
        raise ValueError("Inspection image is too large. Try inspecting only the viewport.")
    metadata = {"target": target, "width": image.width(), "height": image.height(), "mimeType": "image/jpeg", "note": "Current PyMOL application image attached to the next AI request."}
    return "data:image/jpeg;base64," + encoded, metadata
