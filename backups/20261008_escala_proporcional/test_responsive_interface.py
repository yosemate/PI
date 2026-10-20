"""Testes geométricos e imagens em ambiente isolado, sem bancada física."""
import os,sys,pathlib,tempfile,unittest,importlib.util
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location("stability",ROOT/"tests/test_stability_regression.py")
regression=importlib.util.module_from_spec(spec);spec.loader.exec_module(regression)
from PyQt5.QtCore import QPoint,Qt,QRect
from PyQt5.QtWidgets import QApplication,QDialog,QVBoxLayout,QLabel,QScrollArea
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtTest import QTest
from responsive_layout import DialogScreenAdapter
import main

class ResponsiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        # O plugin offscreen do Windows não enumera as fontes instaladas.
        for face in ("segoeui.ttf","segoeuib.ttf"):
            path=pathlib.Path("C:/Windows/Fonts")/face
            if path.exists(): QFontDatabase.addApplicationFont(str(path))
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"SPECTRUM_LAB_DATA_DIR":self.tmp.name})
        self.env.start()
        self.worker=patch.object(main,"ConnectionWorker",regression.FakeWorker)
        self.worker.start()
        self.window=main.SpectrumLabMainWindow()
        self.window._heartbeat_timer.stop();self.window._calib_validity_timer.stop()
        self.window.show()
        QTest.qWait(60)
    def tearDown(self):
        self.window.serial_worker.connected=False
        self.window.close();self.window.deleteLater();self.app.processEvents()
        self.worker.stop();self.env.stop();self.tmp.cleanup()
    def arrange(self,width,height):
        w=self.window
        w.resize(width,height)
        QTest.qWait(70);w._adapt_interface();QTest.qWait(70)
        return w
    def test_screen_sizes_no_horizontal_overflow_and_emergency_visible(self):
        for size in ((1920,1080),(1366,720),(1093,560),(911,480),(800,450),(600,400),(480,320)):
            with self.subTest(size=size):
                w=self.arrange(*size)
                self.assertEqual((w.width(),w.height()),size)
                self.assertEqual(w.content_scroll.horizontalScrollBar().maximum(),0)
                rect=QRect(w.btn_top_emergency.mapTo(w,QPoint()),w.btn_top_emergency.size())
                self.assertTrue(w.rect().contains(rect))
                self.assertGreaterEqual(w.btn_top_emergency.width(),w.btn_top_emergency.sizeHint().width())
                for card in (w.kpi_energy,w.kpi_peak,w.kpi_ratio_cel,w.kpi_ratio_water):
                    self.assertGreater(card.lbl_title.width(),80)
                self.assertEqual(len(w.auth_manager.listar_leituras()),0)
                if os.environ.get("SPECTRUM_CAPTURE_UI")=="1":
                    directory=ROOT/"validation";directory.mkdir(exist_ok=True)
                    w.grab().save(str(directory/f"interface_4_11_0_{size[0]}.png"))
    def test_window_fits_available_area_after_screen_change(self):
        w=self.arrange(1920,1080)
        class NotebookScreen:
            def availableGeometry(self): return QRect(0,0,911,480)
        with patch.object(w,"screen",return_value=NotebookScreen()):
            w._fit_active_screen()
        QTest.qWait(70)
        self.assertLessEqual(w.frameGeometry().width(),911)
        self.assertLessEqual(w.frameGeometry().height(),480)
        self.assertEqual(w.dashboard_splitter.orientation(),Qt.Vertical)

    def test_reflow_back_to_desktop_preserves_widgets_and_state(self):
        w=self.arrange(911,480)
        self.assertEqual(w._kpi_columns,2)
        self.assertEqual(w.dashboard_splitter.orientation(),Qt.Vertical)
        w.lbl_kappa_valor.setText("7.25")
        w=self.arrange(1920,1080)
        self.assertEqual(w._kpi_columns,4)
        self.assertEqual(w.dashboard_splitter.orientation(),Qt.Horizontal)
        self.assertEqual(w.lbl_kappa_valor.text(),"7.25")
        self.assertIs(w.dashboard_splitter.widget(0),w.left_panel)
        self.assertIs(w.dashboard_splitter.widget(1),w.right_panel)
    def test_oversized_dialog_fits_screen_with_scroll(self):
        dialog=QDialog()
        dialog.setFixedSize(960,700)
        layout=QVBoxLayout(dialog);layout.addWidget(QLabel("Teste de diálogo"))
        class SmallScreen:
            def availableGeometry(self): return QRect(0,0,800,450)
        adapter=DialogScreenAdapter(self.app)
        from PyQt5.QtCore import QEvent
        with patch.object(dialog,"screen",return_value=SmallScreen()):
            adapter.eventFilter(dialog,QEvent(QEvent.Show))
        self.assertLessEqual(dialog.width(),760)
        self.assertLessEqual(dialog.height(),390)
        self.assertEqual(len(dialog.findChildren(QScrollArea)),1)
        self.assertEqual(dialog.minimumWidth(),0)
        dialog.deleteLater()
if __name__=="__main__":
    unittest.main(verbosity=2)
