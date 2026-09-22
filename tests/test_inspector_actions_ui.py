from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from comfyui_support_tools.applications.main_gui.ui.processing.inspector_panel import InspectorPanel
from comfyui_support_tools.entrypoints.inspector import create_inspector
from comfyui_support_tools.shared.contracts.inspector_contracts import TaggerSettings, MediaNotes
from tests.inspector_http_fixture import TaggerFixture
from tests.test_inspector_actions import sample


def pump(window, predicate, timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        window.update()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError("Tk inspector timed out")


class InspectorPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform!='win32' and not os.environ.get('DISPLAY'):
            raise unittest.SkipTest('Tk display required; Windows CI exercises all tests')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.fixture=TaggerFixture()
        self.a=sample(Path(self.tmp.name))
        self.b=sample(Path(self.tmp.name), 'second.png')
        self.window=tk.Tk()
        self.window.geometry('260x760')
        self.errors=[]
        self.window.report_callback_exception=lambda *args:self.errors.append(args)
        self.logs=[]
        self.controller=create_inspector()
        self.panel=InspectorPanel(self.window,self.controller,self.logs.append)
        self.panel.pack(fill='both',expand=True)
        self.panel.select((self.a,))
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        for worker in threading.enumerate():
            if worker.name=='inspector-action':
                worker.join(3)
                self.assertFalse(worker.is_alive())
        self.fixture.close()
        self.tmp.cleanup()
        self.assertEqual(self.errors,[])

    def connect(self):
        self.controller.configure(TaggerSettings(self.fixture.url,'fixture-model'))
        self.controller.start('probe')
        pump(self.window,lambda:not self.controller.status().busy)
        self.panel.refresh()

    def test_initial_state_disabled_and_does_not_auto_connect(self):
        self.assertEqual(str(self.panel.run_button['state']),'disabled')
        self.panel.open_settings()
        self.window.update()
        self.assertEqual(self.fixture.requests,[])
        self.assertIn('未確認',self.panel.reason_text.get())

    def test_confirmation_cancel_makes_no_post(self):
        self.connect()
        with mock.patch('tkinter.messagebox.askyesno',return_value=False) as confirm:
            self.panel.run_button.invoke()
        self.assertTrue(confirm.called)
        self.assertEqual([verb for verb,*_ in self.fixture.requests],['GET'])

    def test_real_button_posts_batch_and_keeps_style_prompt_separate(self):
        self.connect()
        notes=MediaNotes(style_tags=('watercolor',),prompt='blue sky')
        self.controller.save_notes(notes)
        self.panel.select((self.a,self.b))
        with mock.patch('tkinter.messagebox.askyesno',return_value=True):
            self.panel.run_button.invoke()
        self.panel.select((self.b,))
        pump(self.window,lambda:not self.controller.status().busy)
        self.assertIn('成功2',self.panel.status_text.get())
        self.panel.select((self.a,))
        self.assertEqual(self.controller.notes().style_tags,('watercolor',))
        self.assertEqual(self.controller.notes().prompt,'blue sky')
        self.assertIn('landscape',self.panel.fields['content_tags'].get('1.0','end'))
        self.assertEqual(len([x for x in self.fixture.requests if x[0]=='POST']),2)

    def test_selection_change_during_confirmation_aborts_send(self):
        self.connect()
        def confirm(*_args,**_kwargs):
            self.panel.select((self.b,));return True
        with mock.patch('tkinter.messagebox.askyesno',side_effect=confirm):
            self.panel.run_action('tag')
        self.assertEqual(len(self.fixture.requests),1)
        self.assertTrue(any('選択または' in text for text in self.logs))

    def test_video_and_mixed_selection_disable_image_action(self):
        self.connect()
        for values in ((replace(self.a,kind='video'),), (self.a,replace(self.b,kind='video'))):
            self.panel.select(values)
            self.assertEqual(str(self.panel.run_button['state']),'disabled')
            self.assertEqual(str(self.panel.save_button['state']),'disabled')
            self.assertIn('画像のみ',self.panel.reason_text.get())

    def test_notes_saved_only_to_selected_media_session(self):
        self.panel.fields['style_tags'].insert('1.0','ink, sketch')
        self.panel.fields['prompt'].insert('1.0','My prompt')
        self.window.update()
        self.panel.save_button.invoke()
        self.assertEqual(self.controller.notes().style_tags,('ink','sketch'))
        self.assertEqual(self.controller.notes().content_tags,())
        self.panel.select((self.b,))
        self.assertEqual(self.controller.notes(),MediaNotes())
        self.panel.select((self.a,))
        self.assertEqual(self.panel.fields['prompt'].get('1.0','end-1c'),'My prompt')
        self.assertEqual(len(list(Path(self.tmp.name).iterdir())),2)

    def test_unapplied_edits_do_not_leak_on_selection_change(self):
        self.panel.fields['prompt'].insert('1.0','UNSAVED')
        self.window.update()
        self.panel.select((self.b,))
        self.assertEqual(self.panel.fields['prompt'].get('1.0','end-1c'),'')
        self.assertTrue(any('未反映' in line for line in self.logs))

    def test_menu_and_button_share_registry_and_capability_state(self):
        menu=tk.Menu(self.window,tearoff=False)
        self.panel.fill_menu(menu)
        self.assertEqual(menu.entrycget(0,'state'),'disabled')
        self.connect()
        self.panel.fill_menu(menu)
        self.assertEqual(menu.entrycget(0,'state'),'normal')
        self.assertEqual(menu.entrycget(1,'state'),'disabled')
        with mock.patch.object(self.panel,'run_action') as execute:
            menu.invoke(0)
        execute.assert_called_once_with('tag')


class InspectorShellIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform!='win32' and not os.environ.get('DISPLAY'):
            raise unittest.SkipTest('Tk display required')

    def test_real_shell_switching_clears_actions_and_restores_media_notes(self):
        from comfyui_support_tools.applications.main_gui.ui.processing.inspector_shell import InspectorShellWindow
        from comfyui_support_tools.entrypoints.workspace import create_navigation
        from comfyui_support_tools.entrypoints.media_browser import create_media_browser
        from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry
        window=InspectorShellWindow(create_navigation((ToolEntry('t','Test','Utility'),)),lambda _:None,
                                    create_media_browser(),create_inspector())
        errors=[]
        window.report_callback_exception=lambda *args:errors.append(args)
        with tempfile.TemporaryDirectory() as temp:
            record=sample(Path(temp))
            try:
                window.update()
                browser=window.workspace.media
                browser.load_folder(temp)
                pump(window,lambda:not browser.commander.view()[1]['loading'])
                records,_=browser.commander.view()
                browser.select((records[0].id,))
                self.assertEqual(window.action_panel.selection,(records[0],))
                window.workspace.show_tools();window.update()
                self.assertEqual(window.action_panel.selection,())
                window.action_panel.fill_menu(window.action_menu)
                self.assertEqual(window.action_menu.entrycget(0,'state'),'disabled')
                window.workspace.show_media();window.update()
                self.assertEqual(len(window.action_panel.selection),1)
                window.geometry('900x600');window.update()
                self.assertGreater(window.workspace.winfo_width(),250)
                with mock.patch.object(window,'_popup',return_value='break'):
                    from types import SimpleNamespace
                    browser.mode.set('リスト');browser._render();window.update()
                    window._list_context(SimpleNamespace(y=99999,x_root=1,y_root=1))
                    self.assertEqual(window.action_panel.selection,())
            finally:
                window.destroy()
                for worker in threading.enumerate():
                    if worker.name in ('media-scan','media-preview','inspector-action'):
                        worker.join(5)
        self.assertEqual(errors,[])


if __name__=='__main__':
    unittest.main()
