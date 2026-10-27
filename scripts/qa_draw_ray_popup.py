import os,json,sys,traceback
from pathlib import Path
from pymol.Qt import QtCore,QtWidgets,QtGui
from pmg_qt import pymol_qt_gui
out=Path(os.environ['PYMOL_POPUP_QA']);out.mkdir(parents=True,exist_ok=True)
errors=[]
sys.excepthook=lambda typ,value,tb:errors.append(''.join(traceback.format_exception(typ,value,tb)))
def ready():
 try:
  w=pymol_qt_gui.window
  if not hasattr(w,'ai_assistant'):
   QtCore.QTimer.singleShot(200,ready);return
  w.ai_assistant.example()
  button=next(b for b in w.findChildren(QtWidgets.QPushButton) if b.text()=='Draw/Ray')
  menu=button.menu()
  menu.popup(button.mapToGlobal(QtCore.QPoint(0,button.height())))
  QtCore.QTimer.singleShot(250,lambda:inspect(menu))
 except Exception:
  errors.append(traceback.format_exc());finish()
def inspect(menu):
 try:
  assert not errors,errors
  widgets=[a.defaultWidget() for a in menu.actions() if isinstance(a,QtWidgets.QWidgetAction)]
  assert len(widgets)==1,'Popup did not contain its render widget'
  widget=widgets[0]
  widget.findChild(QtWidgets.QCheckBox,'button_lock').setChecked(False)
  widget.findChild(QtWidgets.QSpinBox,'input_width').setValue(400)
  widget.findChild(QtWidgets.QSpinBox,'input_height').setValue(300)
  widget.findChild(QtWidgets.QPushButton,'button_draw').click()
  widget.findChild(QtWidgets.QPushButton,'button_back').click()
  widget.findChild(QtWidgets.QPushButton,'button_ray').click()
  menu.grab().save(str(out/'popup.png'))
  QtCore.QTimer.singleShot(1000,lambda:finish(menu))
 except Exception:
  errors.append(traceback.format_exc());finish(menu)
def finish(menu=None):
 if menu:
  try:
   if not errors:
    pymol_qt_gui.window.cmd.png(str(out/'ray-output.png'),prior=1)
    image=QtGui.QImage(str(out/'ray-output.png'))
    assert image.width()==400 and image.height()==300,'Render result has unexpected dimensions'
   menu.close()
  except Exception: errors.append(traceback.format_exc())
 (out/'result.json').write_text(json.dumps({'ok':not errors,'errors':errors},indent=2))
 QtWidgets.QApplication.instance().quit()
QtCore.QTimer.singleShot(900,ready)
QtCore.QTimer.singleShot(20000,finish)
