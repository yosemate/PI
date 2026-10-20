import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt5.QtWidgets import QApplication
import sys

workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

app = QApplication(sys.argv)
from main import SpectrumLabMainWindow


def test_static_repeatability_fsm():
    print("\n--- Testando FSM de Repetibilidade Estática Instrumental ---")
    win = SpectrumLabMainWindow()
    
    commands_sent = []
    win.send_serial_command = lambda cmd: commands_sent.append(cmd)
    
    # Simula início da repetibilidade pós-confirmação
    win.modo_repetibilidade = True
    win.leituras_rep = []
    win.fsm_state = "REP_FECHANDO_GAVETA"
    
    # 1. Gaveta fechou -> Avança sensor para a medição
    win._handle_repeatability_fsm("GAVETA_FECHADA")
    assert win.fsm_state == "REP_AVANCANDO_SENSOR"
    assert commands_sent[-1] == "CMD:AVANCAR_SENSOR"
    print("[Passo 1 OK] CMD:AVANCAR_SENSOR despachado.")
    
    # 2. Sensor avançado -> Dispara leitura 1
    win._handle_repeatability_fsm("SENSOR_AVANCADO")
    assert win.fsm_state == "REP_LENDO_ESPECTRO"
    assert commands_sent[-1] == "CMD:LER_ESPECTRO"
    print("[Passo 2 OK] Leitura 1 disparada (CMD:LER_ESPECTRO).")
    
    # 3. Simula leituras 1 a 4 com retenção estática
    for i in range(1, 5):
        win._last_raw_payload = [1000.0 + i * 10] * 6
        win._handle_repeatability_fsm("LEITURA_CONCLUIDA")
        assert len(win.leituras_rep) == i
        assert win.fsm_state == "REP_AGUARDANDO_PROXIMA"
        print(f"[Leitura {i} OK] Aguardando próxima sem mover carrinho...")
        
        # Dispara o timer callback
        win._trigger_next_repeatability_read()
        assert win.fsm_state == "REP_LENDO_ESPECTRO"
        assert commands_sent[-1] == "CMD:LER_ESPECTRO"
        print(f"[Leitura {i+1} Disparada OK] Sensor permanece avançado na posição!")
        
    # 4. Leitura 5 concluída -> Agora e somente agora recua o sensor
    win._last_raw_payload = [1050.0] * 6
    win._handle_repeatability_fsm("LEITURA_CONCLUIDA")
    assert len(win.leituras_rep) == 5
    assert win.fsm_state == "REP_RECUANDO_SENSOR"
    assert commands_sent[-1] == "CMD:RECUAR_SENSOR"
    print("[Leitura 5 Concluída OK] Recuando sensor (CMD:RECUAR_SENSOR)...")
    
    # 5. Sensor recuado -> Abre a gaveta
    win._handle_repeatability_fsm("SENSOR_RECUADO")
    assert win.fsm_state == "REP_ABRINDO_GAVETA"
    assert commands_sent[-1] == "CMD:ABRIR_GAVETA"
    print("[Sensor Recuado OK] Abrindo gaveta (CMD:ABRIR_GAVETA)...")
    
    # Contagem total de comandos
    count_avancar = commands_sent.count("CMD:AVANCAR_SENSOR")
    count_recuar = commands_sent.count("CMD:RECUAR_SENSOR")
    count_ler = commands_sent.count("CMD:LER_ESPECTRO")
    count_abrir = commands_sent.count("CMD:ABRIR_GAVETA")
    
    print(f"\nResumo de Comandos:")
    print(f"  CMD:AVANCAR_SENSOR: {count_avancar} (Esperado: 1)")
    print(f"  CMD:RECULAR_SENSOR: {count_recuar} (Esperado: 1)")
    print(f"  CMD:LER_ESPECTRO:   {count_ler} (Esperado: 5)")
    print(f"  CMD:ABRIR_GAVETA:   {count_abrir} (Esperado: 1)")
    
    assert count_avancar == 1, f"CMD:AVANCAR_SENSOR deve ser chamado apenas 1 vez, foi {count_avancar}"
    assert count_recuar == 1, f"CMD:RECUAR_SENSOR deve ser chamado apenas 1 vez, foi {count_recuar}"
    assert count_ler == 5, f"CMD:LER_ESPECTRO deve ser chamado 5 vezes, foi {count_ler}"
    assert count_abrir == 1, f"CMD:ABRIR_GAVETA deve ser chamado apenas 1 vez, foi {count_abrir}"
    
    print("\n[SUCESSO] Repetibilidade Estática Instrumental 100% validada sem folgas mecânicas!")


if __name__ == "__main__":
    test_static_repeatability_fsm()
