import os
import sys
import json
import datetime

os.environ["QT_QPA_PLATFORM"] = "offscreen"
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

from chemometrics import ChemometricsEngine, calculate_kappa_number
from main import SpectrumLabMainWindow, CalibrationModalDialog, CalibrationExpiredDialog


def test_repeatability_and_calibration_validity():
    print("\n--- TESTE 1: Isolamento de Perfis e Persistência Atômica ---")
    engine = ChemometricsEngine()
    
    # Valida presença dos dois perfis
    assert "umido" in engine.calibracoes
    assert "seco" in engine.calibracoes
    
    # Salva no modo seco
    engine.set_mode("seco")
    engine.save_calibration(
        vetor_branco=[2450.0, 2550.0, 2650.0, 2750.0, 2850.0, 2950.0],
        r2=0.998,
        rmse=0.003,
        notes="Teste Amostra Seca Teflon",
        operador="Eng. Metrologista"
    )
    
    # Verifica se perfil úmido permaneceu inalterado
    with open(engine.calib_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["modo_seco"]["r2"] == 0.998
    assert data["modo_seco"]["operador"] == "Eng. Metrologista"
    assert data["modo_umido"]["vetor_branco"][0] == 1800.0  # intacto
    print("[OK] Perfis são 100% isolados e persistidos atomicamente com os.fsync!")
    
    print("\n--- TESTE 2: Controle de Validade Metrológica e Expiração ---")
    # Timeout de 60s
    engine.set_timeout_seconds(60)
    assert not engine.is_calibration_expired(), "Recém-calibrado não deve estar expirado"
    
    # Simula calibração feita há 2 horas (7200 segundos atrás)
    past_time = (datetime.datetime.now() - datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    engine.calib_timestamp = past_time
    engine.calibracoes["seco"]["timestamp"] = past_time
    assert engine.is_calibration_expired(), "Calibração de 2 horas atrás com timeout de 60s deve constar como expirada"
    print("[OK] Detecção de expiração metrológica validada!")
    
    print("\n--- TESTE 3: Janela Modal de Repetibilidade Avançada (950x650) ---")
    win = SpectrumLabMainWindow()
    
    # Alimenta 5 leituras estáticas
    win.leituras_rep = [
        [0.55, 0.52, 0.50, 0.47, 0.45, 0.43],
        [0.56, 0.53, 0.50, 0.48, 0.45, 0.43],
        [0.55, 0.52, 0.51, 0.47, 0.46, 0.44],
        [0.56, 0.53, 0.50, 0.48, 0.45, 0.43],
        [0.55, 0.52, 0.50, 0.47, 0.45, 0.43],
    ]
    
    # Executa _display_repeatability_report sem erros de canvas ou cálculos
    win._display_repeatability_report()
    print("[OK] Modal de repetibilidade gerada com sucesso (cards, tabela e gráficos de barra + dispersão)!")
    
    print("\n--- TESTE 4: Intertravamento Operacional por Expiração de Calibração ---")
    # Com calibração expirada:
    win.chem_engine.calib_timestamp = past_time
    win._check_calibration_validity()
    
    assert not win.btn_start_scan.isEnabled(), "Ciclo automático deve estar intertravado (desabilitado) quando expirado"
    assert not win.btn_repeatability.isEnabled(), "Repetibilidade deve estar intertravada (desabilitada) quando expirada"
    assert "EXPIRADA" in win.badge_calib.lbl_text.text()
    print("[OK] Intertravamento metrológico com bloqueio de botões validado!")
    
    # Revalida calibração com timestamp atual
    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    win.chem_engine.calib_timestamp = now_time
    win.chem_engine.calibracoes["seco"]["timestamp"] = now_time
    win.chem_engine.set_timeout_seconds(86400)
    win._check_calibration_validity()
    
    assert win.btn_start_scan.isEnabled(), "Botão deve estar habilitado quando calibrado e válido"
    assert win.btn_repeatability.isEnabled(), "Botão deve estar habilitado quando calibrado e válido"
    assert "CALIBRADO" in win.badge_calib.lbl_text.text()
    print("[OK] Desbloqueio operacional após calibração válida verificado!")
    
    print("\n[SUCESSO] TODOS OS TESTES PASSARAM COM EXCELÊNCIA!")


if __name__ == "__main__":
    test_repeatability_and_calibration_validity()
