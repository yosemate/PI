import os
import sys
import tempfile
import json
import matplotlib.pyplot as plt

# Garante path de importação
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from chemometrics import (
    ChemometricsEngine, calculate_kappa_number,
    OPERATIONAL_MODES, MODE_LABELS
)
from pdf_generator import generate_pdf_report


def test_chemometrics_engine_modes():
    print("\n--- Teste 1: ChemometricsEngine e Alternância de Modos ---")
    engine = ChemometricsEngine()
    
    print(f"Modo inicial: {engine.active_mode}")
    assert engine.active_mode in OPERATIONAL_MODES
    assert "umido" in engine.calibracoes
    assert "seco" in engine.calibracoes
    
    # Comuta para modo seco
    ok_seco = engine.set_mode("seco")
    assert ok_seco is True
    assert engine.active_mode == "seco"
    assert engine.calib_notes == engine.calibracoes["seco"]["notes"]
    print(f"[OK] Comutado para 'seco': Branco={engine.vetor_branco[:3]}...")
    
    # Comuta de volta para modo umido
    ok_umido = engine.set_mode("umido")
    assert ok_umido is True
    assert engine.active_mode == "umido"
    assert engine.calib_notes == engine.calibracoes["umido"]["notes"]
    print(f"[OK] Comutado para 'umido': Branco={engine.vetor_branco[:3]}...")


def test_kappa_calculation_modes():
    print("\n--- Teste 2: Modelos Quimiométricos de Kappa (Úmido vs. Seco) ---")
    
    # Caso A: Modo Úmido (Suspensão Aquosa)
    # Lignin ratio = 1.0, Cellulose ratio = 1.0
    # Kappa = (1.0 * 14.5) - (1.0 * 3.2) + 8.0 = 19.3
    mock_wet = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    kappa_wet, status_wet, color_wet = calculate_kappa_number(mock_wet, mode="umido")
    print(f"Modo Úmido: Kappa={kappa_wet} | Status='{status_wet}'")
    assert abs(kappa_wet - 19.3) < 0.2
    
    # Caso B: Modo Seco - Amostra Comercial Branqueada de Mercado
    # Reflectâncias altas (~80-95%) e r_cel ~ 1.15
    mock_bleached_dry = [0.80, 0.82, 0.72, 0.78, 0.80, 0.82]
    kappa_dry_b, status_dry_b, color_dry_b = calculate_kappa_number(mock_bleached_dry, mode="seco")
    print(f"Modo Seco (Alta Alvura): Kappa={kappa_dry_b} | Status='{status_dry_b}'")
    assert 0.5 <= kappa_dry_b <= 1.5, f"Esperado entre 0.5 e 1.5 para placa de alta alvura, obtido {kappa_dry_b}"
    assert "Alta Alvura" in status_dry_b or "Branqueada" in status_dry_b
    
    # Caso C: Modo Seco - Amostra Kraft Semi-Branqueada
    mock_semi_dry = [0.35, 0.45, 0.30, 0.40, 0.45, 0.50]
    kappa_dry_s, status_dry_s, color_dry_s = calculate_kappa_number(mock_semi_dry, mode="seco")
    print(f"Modo Seco (Kraft Semi-Branqueada): Kappa={kappa_dry_s} | Status='{status_dry_s}'")
    assert 25.0 <= kappa_dry_s <= 35.0, f"Esperado entre 25 e 35, obtido {kappa_dry_s}"
    
    # Caso D: Modo Seco - Papelão Marrom / Massa Crua
    mock_brown_dry = [0.25, 0.50, 0.24, 0.40, 0.45, 0.55]
    kappa_dry_br, status_dry_br, color_dry_br = calculate_kappa_number(mock_brown_dry, mode="seco")
    print(f"Modo Seco (Papelão Marrom / Massa Crua): Kappa={kappa_dry_br} | Status='{status_dry_br}'")
    assert kappa_dry_br >= 35.0, f"Esperado >= 35.0 para papelão marrom, obtido {kappa_dry_br}"
    
    # Caso E: Piso de saturação (clipping) em 0.5 para alvura extrema
    mock_ultra_white = [0.95, 0.90, 0.95, 0.95, 0.95, 0.95]
    kappa_clip, _, _ = calculate_kappa_number(mock_ultra_white, mode="seco")
    print(f"Modo Seco (Clipping inferior): Kappa={kappa_clip}")
    assert kappa_clip == 0.5, f"Esperado clipping em 0.5, obtido {kappa_clip}"
    print("[OK] Cálculos de Kappa validados com sucesso!")


def test_pdf_generation_robustness():
    print("\n--- Teste 3: Blindagem e Geração do Laudo PDF ---")
    temp_dir = tempfile.mkdtemp()
    
    # 1. Geração Normal Modo Úmido
    pdf_path_1 = os.path.join(temp_dir, "laudo_umido.pdf")
    out1 = generate_pdf_report(
        filename=pdf_path_1,
        sample_id="AM-TEST-01",
        operator="Operador Teste",
        material_name="Celulose Sulfato Branqueada",
        match_percentage=94.5,
        values=[1200, 1450, 1800, 1950, 2100, 2250],
        com_port="COM3",
        kappa_value=14.2,
        operational_mode="umido"
    )
    assert os.path.exists(out1)
    assert os.path.getsize(out1) > 1000
    print(f"[OK] Laudo Modo Úmido gerado: {out1} ({os.path.getsize(out1)} bytes)")
    
    # 2. Geração Normal Modo Seco
    pdf_path_2 = os.path.join(temp_dir, "laudo_seco.pdf")
    out2 = generate_pdf_report(
        filename=pdf_path_2,
        sample_id="AM-TEST-02",
        operator="Operador Teste",
        material_name="Amostra de Celulose Branqueada de Mercado",
        match_percentage=98.1,
        values=[2300, 2400, 2450, 2480, 2500, 2520],
        com_port="COM3",
        kappa_value=1.1,
        operational_mode="seco"
    )
    assert os.path.exists(out2)
    assert os.path.getsize(out2) > 1000
    print(f"[OK] Laudo Modo Seco gerado: {out2} ({os.path.getsize(out2)} bytes)")
    
    # 3. Teste defensivo: valores None / vazios
    pdf_path_3 = os.path.join(temp_dir, "laudo_null_values.pdf")
    out3 = generate_pdf_report(
        filename=pdf_path_3,
        sample_id=None,
        operator=None,
        material_name=None,
        match_percentage=None,
        values=None,
        com_port=None,
        kappa_value=None,
        operational_mode="seco"
    )
    assert os.path.exists(out3)
    assert os.path.getsize(out3) > 1000
    print(f"[OK] Laudo com parâmetros None gerado com sucesso: {out3}")
    
    # 4. Verificação de vazamento de figuras do Matplotlib
    open_figs = plt.get_fignums()
    assert len(open_figs) == 0, f"Vazamento de figuras detectado: {open_figs}"
    print("[OK] Nenhuma figura do Matplotlib ficou aberta (sem memory leak)!")
    
    # Limpeza
    for p in (out1, out2, out3):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


if __name__ == "__main__":
    test_chemometrics_engine_modes()
    test_kappa_calculation_modes()
    test_pdf_generation_robustness()
    print("\n[SUCESSO] TODOS OS TESTES PASSARAM COM EXCELENCIA!")
