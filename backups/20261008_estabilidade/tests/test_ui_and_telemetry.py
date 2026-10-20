import os
import sys

# Garante modo headless
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

# Garante path de importação
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication
from main import SpectrumLabMainWindow, CardDiagnosticoAS7263, CardKpiCalibracao


def test_ui_and_telemetry():
    print("\n--- Teste de High-DPI, Resolução, Layout e Telemetria AS7263 ---")
    app = QApplication.instance() or QApplication(sys.argv)
    win = SpectrumLabMainWindow()

    # 1. Verifica presença dos cards
    assert hasattr(win, 'card_calibracao'), 'Falta card_calibracao'
    assert hasattr(win, 'card_telemetria'), 'Falta card_telemetria'
    assert isinstance(win.card_calibracao, CardKpiCalibracao), 'card_calibracao tipo incorreto'
    assert isinstance(win.card_telemetria, CardDiagnosticoAS7263), 'card_telemetria tipo incorreto'
    print("[OK] Cards instanciados corretamente.")

    # 2. Verifica valores padrão do card de telemetria
    assert win.card_telemetria.lbl_val_temp.text() == '-- °C'
    assert '64x' in win.card_telemetria.lbl_val_gain.text()
    assert '166 ms' in win.card_telemetria.lbl_val_integration.text()
    assert 'Ativo' in win.card_telemetria.lbl_val_led.text()
    assert 'IEEE 754' in win.card_telemetria.lbl_val_irrad.text()
    assert 'AS7263' in win.card_telemetria.lbl_val_hw.text()
    assert 'Não' in win.card_telemetria.lbl_val_sat.text()
    print("[OK] Valores nominais padrão seguros validados.")

    # 3. Testa recepção de linha serial JSON
    json_msg = '{"die_temp": 31.4, "gain": "16x", "integration": "200 ms", "led": "Desligado", "irradiance": "Disponível", "hw": "AS7263-v2", "status": "Calibrando", "saturation": false}'
    win._on_serial_line_received(json_msg)
    assert '31.4' in win.card_telemetria.lbl_val_temp.text(), f"Temp incorreta: {win.card_telemetria.lbl_val_temp.text()}"
    assert win.card_telemetria.lbl_val_gain.text() == '16x'
    assert win.card_telemetria.lbl_val_integration.text() == '200 ms'
    assert win.card_telemetria.lbl_val_led.text() == 'Desligado'
    assert win.card_telemetria.lbl_val_irrad.text() == 'Disponível'
    assert win.card_telemetria.lbl_val_hw.text() == 'AS7263-v2'
    assert win.card_telemetria.lbl_val_status.text() == 'Calibrando'
    print("[OK] Telemetria JSON atualizada com sucesso.")

    # 4. Testa recepção de linha serial por tags TELEM:
    telem_msg = 'TELEM:TEMP=29.2;GAIN=64x;INT=166ms;LED=Ativo (12.5 mA);SAT=1;STATUS=Operacional'
    win._on_serial_line_received(telem_msg)
    assert '29.2' in win.card_telemetria.lbl_val_temp.text()
    assert 'Sim (Saturado!)' in win.card_telemetria.lbl_val_sat.text()
    assert win.card_telemetria.lbl_val_status.text() == 'Operacional'
    print("[OK] Telemetria por tags TELEM: atualizada com sucesso.")

    # 4.1 Testa formato pipe bruto com prefixo DIAG:
    diag_pipe_msg = "DIAG:37|GAIN:64x|INT:140.0ms|LED:50mA|HW:AS7263_NIR|STATUS:READY"
    win._on_serial_line_received(diag_pipe_msg)
    assert win.lbl_die_temp.text() == "37 °C", f"lbl_die_temp incorreto: {win.lbl_die_temp.text()}"
    assert "GAIN" not in win.lbl_die_temp.text(), "Vazamento da string completa para lbl_die_temp detectado!"
    assert win.lbl_ganho.text() == "64x"
    assert win.lbl_integracao.text() == "140.0ms"
    assert win.lbl_driver_led.text() == "Ativo (50mA)"
    assert win.lbl_hardware.text() == "AS7263 NIR"
    assert win.lbl_status_sensor.text() == "READY"
    print("[OK] Telemetria pipe com prefixo DIAG: validada com sucesso.")

    # 4.2 Testa formato pipe bruto sem prefixo DIAG: (apenas valores separados por pipe contendo GAIN: e INT:)
    raw_pipe_msg = "41.5|GAIN:16x|INT:200.0ms|LED:12.5mA|HW:AS7263_NIR|STATUS:READY"
    win._on_serial_line_received(raw_pipe_msg)
    assert win.lbl_die_temp.text() == "41.5 °C", f"lbl_die_temp incorreto: {win.lbl_die_temp.text()}"
    assert "GAIN" not in win.lbl_die_temp.text(), "Vazamento da string completa para lbl_die_temp detectado!"
    assert win.lbl_ganho.text() == "16x"
    assert win.lbl_integracao.text() == "200.0ms"
    assert win.lbl_driver_led.text() == "Ativo (12.5mA)"
    assert win.lbl_hardware.text() == "AS7263 NIR"
    assert win.lbl_status_sensor.text() == "READY"
    print("[OK] Telemetria pipe sem prefixo DIAG: validada com sucesso.")

    # 5. Testa recepção padrão de 6 canais sem saturação
    win._on_serial_data_received([1000.0, 1200.0, 1400.0, 1600.0, 1800.0, 2000.0])
    assert 'Não (Linear)' in win.card_telemetria.lbl_val_sat.text()
    print("[OK] DATA padrão com 6 canais processado com segurança.")

    # 6. Testa recepção de 6 canais com saturação (>= 65500)
    win._on_serial_data_received([1000.0, 1200.0, 65535.0, 1600.0, 1800.0, 2000.0])
    assert 'Sim (Saturado!)' in win.card_telemetria.lbl_val_sat.text()
    print("[OK] Detecção de saturação óptica nos 6 canais validada.")

    # 7. Testa tamanho mínimo
    min_size = win.minimumSize()
    assert min_size.width() >= 1100 and min_size.height() >= 620, f"Tamanho mínimo inesperado: {min_size.width()}x{min_size.height()}"
    print(f"[OK] Resolução mínima ({min_size.width()}, {min_size.height()}) validada.")

    # 8. Testa cálculo de Kappa e classificação industrial sem trava de teto
    from chemometrics import calculate_kappa_number

    # Verifica ausência de trava de teto (> 50.0)
    # Lignin ratio alto (ex: 860nm / 680nm = 5.0) -> Kappa = (5.0 * 14.5) - (1.0 * 3.2) + 8.0 = 77.3
    mock_high_lignin = [1.0, 1.0, 1.0, 1.0, 1.0, 5.0]
    k_high, st_high, _ = calculate_kappa_number(mock_high_lignin, mode="umido")
    assert k_high > 50.0, f"Kappa não deveria estar travado em 50.0: obtido {k_high}"
    assert st_high == "Papelão / Fibras Recicladas", f"Classificação incorreta: {st_high}"
    print(f"[OK] Cálculo sem trava de teto validado: Kappa={k_high} -> '{st_high}'")

    # Verifica labels no supervisório através de process_raw_spectral_data
    assert hasattr(win, "lbl_kappa_valor"), "Falta atributo lbl_kappa_valor"
    assert hasattr(win, "lbl_kappa_classificacao"), "Falta atributo lbl_kappa_classificacao"

    # Testa exibição de amostra de mercado (<= 2.0)
    win.chem_engine.set_mode("seco")
    # Espectro claro de alta alvura (ADC correspondente a ~100% de reflectância)
    mock_white = [v * 0.95 for v in win.chem_engine.vetor_branco]
    win.process_raw_spectral_data(mock_white)
    assert float(win.lbl_kappa_valor.text()) <= 2.0
    assert win.lbl_kappa_classificacao.text() == "Polpa Branqueada de Mercado"
    print(f"[OK] Faixa <= 2.0: {win.lbl_kappa_valor.text()} -> '{win.lbl_kappa_classificacao.text()}'")

    print("\n[SUCESSO] Todos os testes de UI, Telemetria e Escala de Kappa passaram!")


if __name__ == "__main__":
    test_ui_and_telemetry()
