"""Regressões de calibração/aquisição com arquivos temporários e hardware simulado."""
import os,sys,pathlib,tempfile,unittest,json,datetime,sqlite3
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
os.environ["QT_QPA_PLATFORM"]="offscreen"
from chemometrics import ChemometricsEngine,calculate_kappa_number
from PyQt5.QtCore import QObject,pyqtSignal
from PyQt5.QtWidgets import QApplication
from connection_worker import ConnectionWorker
from database import DatabaseManager
import main

WHITE=[[1000+i,1200+i,1400+i,1600+i,1800+i,2000+i] for i in range(10)]
DARK=[[10,10,10,10,10,10] for _ in range(10)]
SAMPLE=[700,800,950,1100,1200,1300]
def calibrate(engine):
    return engine.save_calibration(white_scans=WHITE,dark_scans=DARK,
        settings=engine.DEFAULT_SETTINGS,operador="Teste isolado")

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.engine=ChemometricsEngine(str(pathlib.Path(self.tmp.name)/"calibracao.json"))
    def tearDown(self): self.tmp.cleanup()
    def test_no_default_calibration(self):
        self.assertFalse(self.engine.calibration_valid())
        self.assertTrue(all(not p["is_calibrated"] for p in self.engine.calibracoes.values()))
    def test_real_references_and_history(self):
        self.assertTrue(calibrate(self.engine))
        self.assertTrue(self.engine.calibration_valid())
        self.assertIsNone(self.engine.r2)
        self.assertEqual(len(self.engine.history),1)
        e=ChemometricsEngine(self.engine.calib_file_path)
        self.assertEqual(e.calibration_id,self.engine.calibration_id)
        self.assertEqual(e.snapshot()["white_stats"]["n"],10)
        self.assertAlmostEqual(e.calculate_relative_reflectance(SAMPLE)[0],690/994.5)
    def test_save_failure_preserves_old_state(self):
        calibrate(self.engine)
        old=self.engine.snapshot()
        old_bytes=pathlib.Path(self.engine.calib_file_path).read_bytes()
        with patch("chemometrics.os.replace",side_effect=PermissionError("bloqueado")):
            self.assertFalse(calibrate(self.engine))
        self.assertEqual(old,self.engine.snapshot())
        self.assertEqual(old_bytes,pathlib.Path(self.engine.calib_file_path).read_bytes())
    def test_references_must_be_complete(self):
        calibrate(self.engine); old=self.engine.snapshot()
        self.assertFalse(self.engine.save_calibration(vetor_branco=[2000]*6))
        self.assertFalse(self.engine.save_calibration(notes="renovar sem medir"))
        self.assertEqual(old,self.engine.snapshot())
    def test_equal_or_inverted_references_rejected(self):
        for white in ([[10]*6]*10,[[5]*6]*10):
            self.assertFalse(self.engine.save_calibration(white_scans=white,dark_scans=DARK,
                settings=self.engine.DEFAULT_SETTINGS))
    def test_bad_adc_rejected(self):
        for vec in ([0]*6,[float("nan")]*6,[float("inf")]*6,[-1]*6,[65535]*6,[100]*5):
            with self.subTest(vec=vec):
                with self.assertRaises(ValueError): self.engine.validate_raw(vec)
    def test_low_signal_never_produces_kappa(self):
        calibrate(self.engine)
        with self.assertRaises(ValueError): self.engine.calculate_relative_reflectance([10]*6)
        with self.assertRaises(ValueError): calculate_kappa_number([0]*6)
    def test_fraction_above_one_has_no_unit_jump(self):
        a=calculate_kappa_number([0.99,0.9,0.9,0.9,0.9,0.9],mode="seco")[0]
        b=calculate_kappa_number([1.01,0.9,0.9,0.9,0.9,0.9],mode="seco")[0]
        self.assertEqual(a,b)
    def test_legacy_references_not_valid(self):
        pathlib.Path(self.engine.calib_file_path).write_text(json.dumps({"modo_seco":
            {"is_calibrated":True,"timestamp":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "vetor_branco":[1000]*6,"vetor_escuro":[0]*6}}))
        e=ChemometricsEngine(self.engine.calib_file_path)
        self.assertFalse(e.calibration_valid())
    def test_profile_isolation(self):
        calibrate(self.engine); old=self.engine.snapshot()
        self.assertTrue(self.engine.set_mode("umido"))
        self.assertFalse(self.engine.calibration_valid())
        self.assertTrue(calibrate(self.engine))
        self.assertTrue(self.engine.set_mode("seco"))
        self.assertEqual(old,self.engine.snapshot())
        self.assertEqual(len(self.engine.history),2)
    def test_expiry_and_future_timestamp(self):
        calibrate(self.engine)
        self.engine.calib_timestamp="2000-01-01 00:00:00"
        self.assertTrue(self.engine.is_calibration_expired())
        self.engine.calib_timestamp="2099-01-01 00:00:00"
        self.assertTrue(self.engine.is_calibration_expired())

class FakeWorker(QObject):
    line_received=pyqtSignal(str)
    status_received=pyqtSignal(str)
    data_received=pyqtSignal(list)
    scan_received=pyqtSignal(str,list)
    connection_changed=pyqtSignal(bool,str)
    error_occurred=pyqtSignal(str)
    def __init__(self,parent=None):
        super().__init__(parent); self.sent=[];self.connected=True;self.mode="USB"
    def is_connected(self): return self.connected
    def send_command(self,cmd,priority=False):
        if not self.connected:return False
        self.sent.append(cmd);return True
    def send_emergency(self):self.sent.append("CMD:EMERGENCIA")
    def disconnect_connection(self):self.connected=False
    @staticmethod
    def list_ports():return []

class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"SPECTRUM_LAB_DATA_DIR":self.tmp.name})
        self.env.start()
        self.worker_patch=patch.object(main,"ConnectionWorker",FakeWorker)
        self.worker_patch.start()
        self.win=main.SpectrumLabMainWindow()
        self.win._calib_validity_timer.stop()
        self.win._protocol_ready=True;self.win._sensor_ready=True
        self.win._auto_confirm_dialog=True
        self.assertTrue(calibrate(self.win.chem_engine))
        self.win._refresh_controls()
    def tearDown(self):
        self.win._hardware_watchdog.stop()
        self.win._acquisition_timer.stop()
        self.win._clear_cycle_timers()
        self.win.serial_worker.connected=False
        self.win.close();self.win.deleteLater()
        self.app.processEvents()
        self.worker_patch.stop();self.env.stop();self.tmp.cleanup()
    def status(self,s):self.win._on_serial_status_received(s)
    def batch(self,values):
        w=self.win
        while w._batch is not None:
            token=w._batch["token"]
            w._on_serial_scan_received(token,values)
            self.status("LEITURA_CONCLUIDA:"+token)
            if w._batch:
                w._acquisition_timer.stop();w._dispatch_batch_read()
    def test_complete_calibration_averages_white_and_led_off_dark(self):
        w=self.win
        w.start_white_calibration_cycle()
        self.status("GAVETA_ABERTA")
        self.status("GAVETA_FECHADA")
        self.status("SENSOR_AVANCADO")
        self.assertEqual(w._batch["target"],10)
        self.batch(WHITE[0])
        self.status("SENSOR_RECUADO")
        self.status("GAVETA_ABERTA")
        self.status("GAVETA_FECHADA")
        self.status("SENSOR_AVANCADO")
        self.assertEqual(w._batch["cmd"],"CMD:LER_ESCURO")
        self.batch(DARK[0])
        self.status("SENSOR_RECUADO")
        self.assertEqual(w.fsm_state,"IDLE")
        self.assertTrue(w.chem_engine.calibration_valid())
        self.assertEqual(w.chem_engine.snapshot()["dark_stats"]["n"],10)
        self.assertEqual(len(w.chem_engine.history),2)
    def test_complete_sample_cycle_averages_five_and_records_snapshot(self):
        w=self.win
        w.start_simple_auto_cycle()
        self.status("GAVETA_ABERTA");self.status("GAVETA_FECHADA");self.status("SENSOR_AVANCADO")
        self.assertEqual(w._batch["target"],5)
        self.batch(SAMPLE)
        self.status("SENSOR_RECUADO");self.status("GAVETA_ABERTA")
        rows=w.auth_manager.listar_leituras()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["acquisition_count"],5)
        self.assertEqual(rows[0]["calibration_id"],w.chem_engine.calibration_id)
        self.assertEqual(len(json.loads(rows[0]["raw_scans_json"])),5)
        self.assertTrue(w._result_valid)
        self.status("GAVETA_FECHADA")
        self.assertEqual(w.fsm_state,"IDLE")
    def test_missing_new_payload_aborts(self):
        w=self.win
        w.send_serial_command("CMD:LER_ESPECTRO")
        token=w._batch["token"]
        self.status("LEITURA_CONCLUIDA:"+token)
        self.assertEqual(w.fsm_state,"FALHA")
        self.assertFalse(w._result_valid)
        self.assertEqual(len(w.auth_manager.listar_leituras()),0)
    def test_old_and_duplicate_payloads_discarded(self):
        w=self.win;w.send_serial_command("CMD:LER_ESPECTRO")
        token=w._batch["token"]
        w._on_serial_scan_received("antigo",SAMPLE)
        self.assertIsNone(w._batch["data"])
        w._on_serial_scan_received(token,SAMPLE)
        w._on_serial_scan_received(token,[999]*6)
        self.assertEqual(w._batch["data"],SAMPLE)
        self.status("LEITURA_CONCLUIDA:"+token)
        self.status("LEITURA_CONCLUIDA:"+token)
        self.assertEqual(len(w._batch["scans"]),1)
    def test_invalid_signal_not_persisted(self):
        w=self.win
        w.process_raw_spectral_data(DARK[0])
        self.assertFalse(w._result_valid)
        self.assertEqual(len(w.auth_manager.listar_leituras()),0)
    def test_validity_timer_cannot_unlock_busy_controls(self):
        w=self.win;w.fsm_state="AUTO_LENDO_ESPECTRO"
        w._check_calibration_validity()
        self.assertFalse(w.btn_start_scan.isEnabled())
        self.assertFalse(w.combo_op_mode.isEnabled())
    def test_emergency_waits_for_hardware_ack(self):
        w=self.win;w.stop_cycle_action()
        w._on_emergency_lock_timeout()
        self.assertEqual(w.fsm_state,"EMERGENCIA")
        self.assertFalse(w.btn_start_scan.isEnabled())
        self.status("EMERGENCIA_ACIONADA")
        self.assertEqual(w.fsm_state,"IDLE")
    def test_cancel_incomplete_calibration_keeps_old(self):
        w=self.win;old=w.chem_engine.snapshot()
        w._calib_transition_choice="CONCLUIR"
        w.start_white_calibration_cycle()
        self.status("GAVETA_ABERTA");self.status("GAVETA_FECHADA");self.status("SENSOR_AVANCADO")
        self.batch(WHITE[0])
        self.status("SENSOR_RECUADO");self.status("GAVETA_ABERTA");self.status("GAVETA_FECHADA")
        self.assertEqual(old,w.chem_engine.snapshot())
    def test_save_failure_never_announces_success(self):
        w=self.win;old=w.chem_engine.snapshot()
        w._white_scans=WHITE;w._dark_scans=DARK
        with patch("chemometrics.os.replace",side_effect=PermissionError("bloqueado")):
            self.assertFalse(w._save_measured_calibration())
        self.assertEqual(old,w.chem_engine.snapshot())
        self.assertEqual(w.fsm_state,"FALHA")
    def test_disconnect_aborts_acquisition(self):
        w=self.win;w.send_serial_command("CMD:LER_ESPECTRO");w.fsm_state="AUTO_LENDO_ESPECTRO"
        w.serial_worker.connected=False
        w._on_serial_connection_changed(False,"cabo removido")
        self.assertEqual(w.fsm_state,"FALHA")
        self.assertIsNone(w._batch)
    def test_parser_distinguishes_telemetry_and_tagged_adc(self):
        worker=ConnectionWorker()
        scans=[];statuses=[];errors=[]
        worker.scan_received.connect(lambda token,data:scans.append((token,data)))
        worker.status_received.connect(statuses.append)
        worker.error_occurred.connect(errors.append)
        worker._parse_incoming_line("DIAG:TEMP:37|GAIN:64x|STATUS:READY")
        self.assertEqual(statuses,[])
        worker._parse_incoming_line("SCAN:abc|DATA:1,2,3,4,5,6")
        self.assertEqual(scans,[("abc",[1,2,3,4,5,6])])
        worker._parse_incoming_line("SCAN:abc|DATA:nan,2,3,4,5,6")
        self.assertEqual(len(errors),1)
        worker._parse_incoming_line("CAL_DATA:1,2,3,4,5,6")
        self.assertEqual(len(scans),1)

if __name__=="__main__":
    unittest.main(verbosity=2)
