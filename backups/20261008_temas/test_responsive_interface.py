"""Escala proporcional, visibilidade completa e interação sem hardware real."""
import os,sys,pathlib,tempfile,unittest,importlib.util
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location("stability",ROOT/"tests/test_stability_regression.py")
regression=importlib.util.module_from_spec(spec);spec.loader.exec_module(regression)
from PyQt5.QtCore import QPoint,Qt,QRect,QSize,QEvent
from PyQt5.QtWidgets import QApplication,QDialog,QVBoxLayout,QLabel,QGraphicsView
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtTest import QTest
from responsive_layout import DialogScreenAdapter
import main

class ResponsiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        for face in ("segoeui.ttf","segoeuib.ttf"):
            path=pathlib.Path("C:/Windows/Fonts")/face
            if path.exists():QFontDatabase.addApplicationFont(str(path))
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"SPECTRUM_LAB_DATA_DIR":self.tmp.name});self.env.start()
        self.worker=patch.object(main,"ConnectionWorker",regression.FakeWorker);self.worker.start()
        self.window=main.SpectrumLabMainWindow()
        self.window._heartbeat_timer.stop();self.window._calib_validity_timer.stop()
        self.window.show();QTest.qWait(70)
    def tearDown(self):
        self.window.serial_worker.connected=False
        self.window.close();self.window.deleteLater();self.app.processEvents()
        self.worker.stop();self.env.stop();self.tmp.cleanup()
    def arrange(self,width,height):
        self.window.resize(width,height);QTest.qWait(70)
        self.window._adapt_interface();QTest.qWait(70)
        return self.window
    def test_entire_dashboard_fits_without_scroll_and_keeps_layout(self):
        design=self.window.dashboard_content.size()
        y_positions=None
        for size in ((1920,1080),(1366,720),(1093,560),(911,480),(800,450),(600,400),(480,320)):
            with self.subTest(size=size):
                w=self.arrange(*size);view=w.canvas_view
                self.assertEqual((w.width(),w.height()),size)
                self.assertEqual(w.dashboard_content.size(),design)
                self.assertEqual(view.horizontalScrollBarPolicy(),Qt.ScrollBarAlwaysOff)
                self.assertEqual(view.verticalScrollBarPolicy(),Qt.ScrollBarAlwaysOff)
                self.assertFalse(view.horizontalScrollBar().isVisible())
                self.assertFalse(view.verticalScrollBar().isVisible())
                canvas_rect=view.mapFromScene(view.canvas_scene.sceneRect()).boundingRect()
                self.assertTrue(view.viewport().rect().contains(canvas_rect))
                self.assertEqual(w.dashboard_splitter.orientation(),Qt.Horizontal)
                cards=(w.kpi_energy,w.kpi_peak,w.kpi_ratio_cel,w.kpi_ratio_water)
                current=[c.mapTo(w.dashboard_content,QPoint()).y() for c in cards]
                self.assertEqual(len(set(current)),1)
                if y_positions is None:y_positions=current
                self.assertEqual(current,y_positions)
                for widget in (w.btn_start_scan,w.btn_top_emergency,w.card_resultado,w.card_calibracao,
                               w.card_telemetria,w.btn_pdf,w.btn_csv,w.txt_console):
                    rect=view.proxy.subWidgetRect(widget)
                    mapped=view.mapFromScene(rect).boundingRect()
                    self.assertTrue(view.viewport().rect().contains(mapped),widget.objectName())
                self.assertEqual(len(w.auth_manager.listar_leituras()),0)
                if os.environ.get("SPECTRUM_CAPTURE_UI")=="1":
                    directory=ROOT/"validation";directory.mkdir(exist_ok=True)
                    w.grab().save(str(directory/f"interface_4_11_1_{size[0]}.png"))
    def test_scaled_button_click_and_result_survive_resize(self):
        calls=[]
        self.window.btn_refresh_ports.clicked.connect(lambda:calls.append(True))
        for size in ((1366,720),(911,480),(480,320)):
            w=self.arrange(*size);view=w.canvas_view
            w.lbl_kappa_valor.setText("7.25")
            center=view.mapFromScene(view.proxy.subWidgetRect(w.btn_refresh_ports).center())
            QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=center)
            self.assertEqual(w.lbl_kappa_valor.text(),"7.25")
        self.assertEqual(len(calls),3)
    def test_window_fits_available_area_after_screen_change(self):
        w=self.arrange(1920,1080)
        class NotebookScreen:
            def availableGeometry(self):return QRect(0,0,911,480)
        with patch.object(w,"screen",return_value=NotebookScreen()):w._fit_active_screen()
        QTest.qWait(70)
        self.assertLessEqual(w.frameGeometry().width(),911)
        self.assertLessEqual(w.frameGeometry().height(),480)
        self.assertLess(w.canvas_view.scale_factor,1)
        self.assertEqual(w.dashboard_splitter.orientation(),Qt.Horizontal)
    def test_oversized_dialog_scales_without_scroll(self):
        dialog=QDialog();dialog.setFixedSize(960,700)
        layout=QVBoxLayout(dialog);layout.addWidget(QLabel("Teste de diálogo"))
        class SmallScreen:
            def availableGeometry(self):return QRect(0,0,800,450)
        adapter=DialogScreenAdapter(self.app)
        with patch.object(dialog,"screen",return_value=SmallScreen()):
            adapter.eventFilter(dialog,QEvent(QEvent.Show))
        dialog.show();QTest.qWait(70)
        self.assertLessEqual(dialog.width(),760)
        self.assertLessEqual(dialog.height(),390)
        view=dialog._scaled_view
        self.assertEqual(view.horizontalScrollBarPolicy(),Qt.ScrollBarAlwaysOff)
        self.assertEqual(view.verticalScrollBarPolicy(),Qt.ScrollBarAlwaysOff)
        self.assertLess(view.scale_factor,1)
        self.assertTrue(view.viewport().rect().contains(view.mapFromScene(view.sceneRect()).boundingRect()))
        dialog.close();dialog.deleteLater()
if __name__=="__main__":unittest.main(verbosity=2)
