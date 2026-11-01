"""Exercise actual menus, shortcut, AI graphics tools and transparent Ray output."""
import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pymol.Qt import QtCore, QtGui, QtWidgets
from pmg_qt import pymol_qt_gui
from pymol_ai_assistant.graphics import PRESETS
from pymol_ai_assistant import __version__
from pymol_ai_assistant.vision import capture_view
from pymol_ai_assistant.config import write_json

OUT=Path(os.environ['PYMOL_GRAPHICS_QA']).resolve();OUT.mkdir(parents=True,exist_ok=True)
requests=[];checks={};errors=[]

class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        try:
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            prompt=json.loads(body['messages'][1]['content']);requests.append(prompt)
            advertised={p['id'] for p in prompt['scene']['graphics']['presets']}
            assert advertised==set(PRESETS)
            if len(requests)==1:
                actions=[{'operation':'graphics_preset','preset':'illustration'},
                         {'operation':'graphics_options','options':{'background':'transparent','material':'matte','shadows':False,'silhouettes':True,'depth_cue':False}},
                         {'operation':'command','command':'png '+str(OUT/'ai-transparent.png')+', width=400, height=300, ray=1'}]
            else:
                assert prompt['toolResults'][-1]['ok']
                execution=json.loads(prompt['toolResults'][-1]['execution'])
                assert execution['results'][0]['result']['preset']=='illustration'
                assert execution['results'][1]['result']['current']['background']=='transparent'
                actions=[]
            reply=json.dumps({'message':'Use the named graphics controls.' if actions else 'The actual graphics results and transparent export succeeded.','actions':actions})
            encoded=json.dumps({'choices':[{'message':{'content':reply},'finish_reason':'stop'}]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
        except Exception:
            errors.append(traceback.format_exc());self.send_error(500)
server=ThreadingHTTPServer(('127.0.0.1',0),Provider)
threading.Thread(target=server.serve_forever,daemon=True).start()

def finish(error=None):
    if (OUT/'result.json').exists():return
    if error:errors.append(error)
    write_json(OUT/'result.json',{'ok':not errors,'errors':errors,**checks,'modelCalls':len(requests)})
    server.shutdown();pymol_qt_gui.window.close()

def completed():
    try:
        w=pymol_qt_gui.window;g=w.graphics_ui;state=w.ai_assistant.tools.graphics.state()
        assert state['background']=='transparent' and state['material']=='matte' and state['silhouettes'] and not state['shadows']
        assert len(requests)==2
        image=QtGui.QImage(str(OUT/'ai-transparent.png'))
        assert image.width()==400 and image.height()==300 and image.hasAlphaChannel() and image.pixelColor(0,0).alpha()==0
        assert any(image.pixelColor(x,y).alpha()>0 for x in range(0,400,10) for y in range(0,300,10))
        assert all(abs(a-b)<1e-5 for a,b in zip(checks['originalView'],w.cmd.get_view()))
        g.refresh();assert g.choices['background']['transparent'].isChecked() and g.choices['material']['matte'].isChecked()
        checks.update(aiNamedPresetAndOptions=True,transparentRayPNG=True,preservedCamera=True,menuReflectsAI=True)
        g.preview_action.trigger()
        checks['renderPreviewAction']=True
        QtCore.QTimer.singleShot(2000,open_menu)
    except Exception:finish(traceback.format_exc())

def open_menu():
    w=pymol_qt_gui.window
    w.graphics_ui.menu.popup(w.graphics_ui.button.mapToGlobal(QtCore.QPoint(0,w.graphics_ui.button.height())))
    QtCore.QTimer.singleShot(300,screenshot)

def screenshot():
    try:
        w=pymol_qt_gui.window;w.graphics_ui.menu.grab().save(str(OUT/'presets-menu.png'));w.graphics_ui.menu.close()
        capture_view(w,'window')
        import base64
        data,_=capture_view(w,'window');(OUT/'review-window.jpg').write_bytes(base64.b64decode(data.split(',',1)[1]))
        finish()
    except Exception:finish(traceback.format_exc())

def configured(value,error):
    if error:finish(str(error));return
    w=pymol_qt_gui.window;d=w.ai_assistant;d.restored(value,None)
    d.agent.finished.connect(completed)
    d.input.setPlainText('Apply Illustration, matte material and a transparent background, then export a 400 by 300 PNG.')
    d.send()

def ready():
    try:
        w=pymol_qt_gui.window
        if not hasattr(w,'graphics_ui') or w.ai_assistant.bridge.process.state() != QtCore.QProcess.Running:
            QtCore.QTimer.singleShot(200,ready);return
        d=w.ai_assistant;g=w.graphics_ui;d.example()
        if os.environ.get('PYMOL_GRAPHICS_EXPECT_REVIEW'):
            from pymol_ai_assistant.config import is_review_build
            assert is_review_build() and ('Local review ' + __version__) in w.windowTitle()
            checks['reviewBuildMarkerAndTitle']=True
        c=w.cmd;checks['originalView']=list(c.get_view())
        button=w.findChild(QtWidgets.QPushButton,'graphics_presets_button')
        assert button and button.menu() is g.menu
        builder=next(b for b in w.findChildren(QtWidgets.QPushButton) if b.text()=='Builder')
        assert button.mapTo(w,QtCore.QPoint(0,0)).y()>builder.mapTo(w,QtCore.QPoint(0,0)).y()
        assert not w.findChild(QtWidgets.QToolBar,'graphics_presets_fallback_toolbar')
        assert len(g.presets)==6 and 'gold_illustration' not in g.presets
        movie=next(b for b in w.findChildren(QtWidgets.QPushButton) if b.text()=='|<')
        row_gap=builder.mapTo(w,QtCore.QPoint(0,0)).y()-movie.mapTo(w,QtCore.QPoint(0,0)).y()-movie.height()
        preset_gap=button.mapTo(w,QtCore.QPoint(0,0)).y()-builder.mapTo(w,QtCore.QPoint(0,0)).y()-builder.height()
        checks.update(otherRowGapPixels=row_gap,presetsGapPixels=preset_gap)
        assert row_gap <= preset_gap <= row_gap+4,(row_gap,preset_gap)
        def check_help(menu):
            assert menu.toolTipsVisible()
            for action in menu.actions():
                if action.isSeparator() or not action.isEnabled():continue
                assert action.toolTip() and len(action.toolTip())>50,action.text()
                if action.menu():check_help(action.menu())
        check_help(g.menu)
        for key in PRESETS:
            g.presets[key].trigger()
            assert d.tools.last_execution['ok']
            assert d.tools.last_execution['results'][0]['result']['preset']==key
        for key in ['shadows','silhouettes','depth_cue']:
            g.refresh();g.toggles[key].trigger();assert d.tools.graphics.state()[key]==g.toggles[key].isChecked()
        for value in ['white','black','transparent']:
            g.choices['background'][value].trigger();assert d.tools.graphics.state()['background']==value
        for value in ['matte','glossy']:
            g.choices['material'][value].trigger();assert d.tools.graphics.state()['material']==value
        checks.update(sixMenuPresets=True,shortcutUnderBuilderProperties=True,sharedMenu=True,independentControls=True)
        g.menu.popup(g.button.mapToGlobal(QtCore.QPoint(0,g.button.height())))
        QtCore.QTimer.singleShot(250,show_tooltip)
    except Exception:finish(traceback.format_exc())

def show_tooltip():
    try:
        w=pymol_qt_gui.window;g=w.graphics_ui
        action=g.presets['full']
        local=g.menu.actionGeometry(action).center()
        g.menu.setActiveAction(action)
        event=QtGui.QHelpEvent(QtCore.QEvent.ToolTip,local,g.menu.mapToGlobal(local))
        QtWidgets.QApplication.sendEvent(g.menu,event)
        QtCore.QTimer.singleShot(250,verify_tooltip)
    except Exception:finish(traceback.format_exc())

def verify_tooltip():
    try:
        assert QtWidgets.QToolTip.isVisible(),'Menu tooltip did not appear'
        assert 'Draw/Ray' in QtWidgets.QToolTip.text()
        tooltip=next(widget for widget in QtWidgets.QApplication.topLevelWidgets()
                     if widget.isVisible() and widget.windowType()==QtCore.Qt.ToolTip)
        tooltip.grab().save(str(OUT/'full-preset-tooltip.png'))
        checks['hoverTooltipVisible']=True
        checks['allPresetAndOptionHelp']=True
        QtWidgets.QToolTip.hideText()
        w=pymol_qt_gui.window;w.graphics_ui.menu.close()
        w.ai_assistant.bridge.request('connect',configured,connection={'provider':'compatible','endpoint':'http://127.0.0.1:%d'%server.server_port,'apiKey':''},model='synthetic-model',remember=False)
    except Exception:finish(traceback.format_exc())

QtCore.QTimer.singleShot(800,ready)
QtCore.QTimer.singleShot(85000,lambda:finish('Graphics GUI QA timed out'))
