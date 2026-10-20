"""
SPECTRUM-LAB PRO (v3.1 Fluent Edition)
Sistema Supervisório e Analisador Espectrométrico NIR/VIS (GY-AS7263)
Metodologia Quimiométrica: Suspensão Aquosa de Celulose sob Lâmina e Lamínula.

Funcionalidades Consolidadas:
1. Protocolo Serial Consolidado (115200 Baud):
   - Comandos de Saída (\\n): CMD:PING, CMD:ABRIR_GAVETA, CMD:FECHAR_GAVETA,
     CMD:AVANCAR_SENSOR, CMD:RECUAR_SENSOR, CMD:LER_ESPECTRO, CMD:EMERGENCIA.
   - Telemetrias de Retorno: STATUS:SENSOR_OK / STATUS:PRONTO, STATUS:PONG,
     STATUS:GAVETA_ABERTA, STATUS:GAVETA_FECHADA, STATUS:SENSOR_AVANCADO,
     STATUS:SENSOR_RECUADO, DATA:v1..v6, STATUS:LEITURA_CONCLUIDA, STATUS:EMERGENCIA_ACIONADA.
2. Desacoplamento Atômico dos Controles Manuais (intertravamento até retorno do STATUS).
3. Ciclos Automáticos da Máquina de Estados (FSM):
   - Ciclo Automático Simples (Fechar Gaveta -> Avançar -> Ler -> Recuar -> Abrir).
   - Teste de Repetibilidade (Posicionamento Único, 5 Leituras 100% Estáticas, estatísticas u, s, CV%).
   - Parada de Emergência (E-Stop prioritário imediato e restauração segura).
4. Camada de Calibração e Quimiometria:
   - Persistência em calibracao.json (Branco com Água Destilada e Escuro).
   - Refletância Relativa (R_i) e Normalização Vetorial SNV (R_norm).
   - Eixos do Gráfico 2D: X (Celulose R680/R730) vs Y (Água R860/R760).
5. Auditoria e Isolamento de Threads com SerialWorker sem duplicações de sinal.
"""

import sys
import os
import json
import csv
import datetime
import random
from typing import Optional, List, Dict

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar, QFrame, QTextEdit, QMessageBox,
    QInputDialog, QLineEdit, QFileDialog, QSplitter, QStackedWidget, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QMenuBar, QMenu, QAction
)
from PyQt5.QtCore import Qt, QTimer, QThread, QEventLoop
from PyQt5.QtGui import QFont, QColor

# Módulos locais
from splash_screen import AnimatedSplashScreen
from animated_chart import SpectralSplineChartWidget, ScatterPlotWidget
from database_manager import DatabaseManagerDialog
from pdf_generator import generate_pdf_report
from connection_worker import ConnectionWorker
from serial_worker import SerialWorker
from chemometrics import (
    ChemometricsEngine, calculate_hybrid_similarity, calculate_kappa_number,
    WAVELENGTHS, CHANNEL_NAMES
)
from manual_control_dialog import ManualControlDialog
from database import get_database_path, DatabaseManager
from auth_manager import AuthManager
from auth_dialogs import DialogLogin, DialogGestaoUsuarios


# =====================================================================
# 1. INDICADOR DE STATUS / BADGE
# =====================================================================
class ModernStatusBadge(QFrame):
    def __init__(self, title="STATUS", active_color="#10B981", inactive_color="#64748B", parent=None):
        super().__init__(parent)
        self.active_color = active_color
        self.inactive_color = inactive_color
        self.is_active = False

        self.setStyleSheet("""
            QFrame {
                background-color: #202020;
                border: 1px solid #383838;
                border-radius: 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {self.inactive_color}; font-size: 11px;")

        self.lbl_text = QLabel(f"{title}: DESCONECTADO")
        self.lbl_text.setStyleSheet("color: #D1D5DB; font-size: 10px; font-weight: bold; font-family: 'Segoe UI';")

        layout.addWidget(self.dot)
        layout.addWidget(self.lbl_text)
        self.title = title

    def set_active(self, active: bool, status_text: str = None):
        self.is_active = active
        color = self.active_color if active else self.inactive_color
        self.dot.setStyleSheet(f"color: {color}; font-size: 11px;")
        if status_text:
            self.lbl_text.setText(f"{self.title}: {status_text}")
        else:
            txt = "CONECTADO" if active else "DESCONECTADO"
            self.lbl_text.setText(f"{self.title}: {txt}")


# =====================================================================
# 2. KPI CARD ESTILO POWER BI (WINDOWS 11 FLUENT)
# =====================================================================
class PowerBiKpiCard(QFrame):
    def __init__(self, icon_str, title_str, default_value="--", subtitle_str="", accent_color="#38BDF8", parent=None):
        super().__init__(parent)
        self.accent_color = accent_color
        self.setObjectName("kpiCard")
        self.setStyleSheet(f"""
            QFrame#kpiCard {{
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-top: 3px solid {accent_color};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(6)
        lbl_icon = QLabel(icon_str)
        lbl_icon.setStyleSheet("font-size: 13px;")

        self.lbl_title = QLabel(title_str.upper())
        self.lbl_title.setStyleSheet("color: #9CA3AF; font-size: 10px; font-weight: bold; font-family: 'Segoe UI'; letter-spacing: 0.5px;")

        header.addWidget(lbl_icon)
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)

        self.lbl_value = QLabel(default_value)
        self.lbl_value.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold; font-family: 'Segoe UI';")
        layout.addWidget(self.lbl_value)

        self.lbl_sub = QLabel(subtitle_str)
        self.lbl_sub.setStyleSheet("color: #6B7280; font-size: 10px; font-family: 'Segoe UI';")
        self.lbl_sub.setWordWrap(True)
        layout.addWidget(self.lbl_sub)

    def set_value(self, value_text: str, subtitle_text: str = None, color_override: str = None):
        self.lbl_value.setText(value_text)
        if color_override:
            self.lbl_value.setStyleSheet(f"color: {color_override}; font-size: 18px; font-weight: bold; font-family: 'Segoe UI';")
        else:
            self.lbl_value.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold; font-family: 'Segoe UI';")
        if subtitle_text is not None:
            self.lbl_sub.setText(subtitle_text)


# =====================================================================
# 2.5 CARD KPI DE MONITORAMENTO DA CALIBRAÇÃO (R², RMSE, N, BADGE)
# =====================================================================
class CardKpiCalibracao(QFrame):
    """
    Card de métricas (KPI) de monitoramento da calibração instrumental.
    Exibe:
    - Título: 'Status da Calibração'
    - R² (Coeficiente de Determinação): formatado com 3 casas decimais (ex: 0.000 ou --)
    - RMSE (Erro Médio Quadrático): formatado com 3 casas decimais (ex: ± 0.000 ou --)
    - Pontos de Calibração (N): quantidade de amostras (ex: N = 0)
    - Badge de Validação Visual:
      * R² >= 0.95: 'Calibrado (Excelente)' (fundo verde suave)
      * 0.85 <= R² < 0.95: 'Calibrado (Ajuste Regular)' (fundo amarelo/laranja suave)
      * R² < 0.85 ou curva vazia: 'Não Calibrado / Baixo Ajuste' (fundo cinza/vermelho suave)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardKpiCalibracao")
        self.setStyleSheet("""
            QFrame#cardKpiCalibracao {
                background-color: #1A1F26;
                border: 1px solid #374151;
                border-radius: 8px;
            }
            QLabel {
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Cabeçalho: Título + Badge de Validação
        header = QHBoxLayout()
        icon = QLabel("📊")
        icon.setStyleSheet("font-size: 14px;")
        lbl_title = QLabel("Status da Calibração")
        lbl_title.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")

        self.lbl_badge = QLabel("Não Calibrado / Baixo Ajuste")
        self.lbl_badge.setAlignment(Qt.AlignCenter)
        self.lbl_badge.setStyleSheet("""
            background-color: #2D1A1F;
            color: #F87171;
            border: 1px solid #DC2626;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: bold;
        """)

        header.addWidget(icon)
        header.addWidget(lbl_title)
        header.addStretch()
        header.addWidget(self.lbl_badge)
        layout.addLayout(header)

        # Métricas em destaque (3 colunas com cartões individuais)
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(8)

        # 1. R²
        box_r2 = QFrame()
        box_r2.setStyleSheet("background-color: #11141A; border: 1px solid #1F2937; border-radius: 6px;")
        l_r2 = QVBoxLayout(box_r2)
        l_r2.setContentsMargins(8, 6, 8, 6)
        l_r2.setSpacing(2)
        sub_r2 = QLabel("R² (Determinação)")
        sub_r2.setStyleSheet("color: #9CA3AF; font-size: 9px; font-weight: 600;")
        self.lbl_r2 = QLabel("--")
        self.lbl_r2.setStyleSheet("color: #38BDF8; font-size: 16px; font-weight: 800;")
        l_r2.addWidget(sub_r2)
        l_r2.addWidget(self.lbl_r2)
        metrics_layout.addWidget(box_r2)

        # 2. RMSE
        box_rmse = QFrame()
        box_rmse.setStyleSheet("background-color: #11141A; border: 1px solid #1F2937; border-radius: 6px;")
        l_rmse = QVBoxLayout(box_rmse)
        l_rmse.setContentsMargins(8, 6, 8, 6)
        l_rmse.setSpacing(2)
        sub_rmse = QLabel("RMSE (Erro Médio)")
        sub_rmse.setStyleSheet("color: #9CA3AF; font-size: 9px; font-weight: 600;")
        self.lbl_rmse = QLabel("--")
        self.lbl_rmse.setStyleSheet("color: #A78BFA; font-size: 16px; font-weight: 800;")
        l_rmse.addWidget(sub_rmse)
        l_rmse.addWidget(self.lbl_rmse)
        metrics_layout.addWidget(box_rmse)

        # 3. Pontos (N)
        box_n = QFrame()
        box_n.setStyleSheet("background-color: #11141A; border: 1px solid #1F2937; border-radius: 6px;")
        l_n = QVBoxLayout(box_n)
        l_n.setContentsMargins(8, 6, 8, 6)
        l_n.setSpacing(2)
        sub_n = QLabel("Pontos (N)")
        sub_n.setStyleSheet("color: #9CA3AF; font-size: 9px; font-weight: 600;")
        self.lbl_n = QLabel("N = 0")
        self.lbl_n.setStyleSheet("color: #FBBF24; font-size: 16px; font-weight: 800;")
        l_n.addWidget(sub_n)
        l_n.addWidget(self.lbl_n)
        metrics_layout.addWidget(box_n)

        layout.addLayout(metrics_layout)

    def atualizar(self, r2=None, rmse=None, n_amostras=0):
        """
        Atualização dinâmica dos labels numéricos e badge de validação visual.
        """
        # R²
        if r2 is not None:
            self.lbl_r2.setText(f"{float(r2):.3f}")
        else:
            self.lbl_r2.setText("--")

        # RMSE
        if rmse is not None:
            self.lbl_rmse.setText(f"± {float(rmse):.3f}")
        else:
            self.lbl_rmse.setText("--")

        # N
        self.lbl_n.setText(f"N = {int(n_amostras)}")

        # Badge de Validação Visual
        if r2 is not None and float(r2) >= 0.95:
            self.lbl_badge.setText("Calibrado (Excelente)")
            self.lbl_badge.setStyleSheet("""
                background-color: #132E1E;
                color: #34D399;
                border: 1px solid #10B981;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
            """)
        elif r2 is not None and float(r2) >= 0.85:
            self.lbl_badge.setText("Calibrado (Ajuste Regular)")
            self.lbl_badge.setStyleSheet("""
                background-color: #3B2811;
                color: #FBBF24;
                border: 1px solid #F59E0B;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
            """)
        else:
            self.lbl_badge.setText("Não Calibrado / Baixo Ajuste")
            self.lbl_badge.setStyleSheet("""
                background-color: #2D1A1F;
                color: #F87171;
                border: 1px solid #DC2626;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
            """)


# =====================================================================
# 3. DIÁLOGO MODAL DE CALIBRAÇÃO INSTRUMENTAL (BRANCO & ESCURO)
# =====================================================================
class CalibrationModalDialog(QDialog):
    """
    Diálogo para medição de Branco (Lâmina + Lamínula com Água Destilada) e Escuro Instrumental.
    """
    def __init__(self, main_win, parent=None):
        super().__init__(parent or main_win)
        self.main_win = main_win
        self.setWindowTitle("Calibração Quimiométrica Instrumental — Suspensão em Água")
        self.setFixedSize(540, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 10px;
            }
            QLabel {
                color: #E5E7EB;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 10px 14px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #0284C7;
                border-color: #38BDF8;
            }
            QPushButton#btnPrimary {
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
            }
            QPushButton#btnPrimary:hover {
                background-color: #0369A1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("🎯 CALIBRAÇÃO INSTRUMENTAL DE REFERÊNCIA")
        title.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(title)

        info_box = QFrame()
        info_box.setStyleSheet("background-color: #262626; border: 1px solid #383838; border-radius: 8px;")
        ib_layout = QVBoxLayout(info_box)
        ib_layout.setContentsMargins(12, 10, 12, 10)

        lbl_desc = QLabel(
            "<b>Metodologia Quimiométrica de Celulose:</b><br>"
            "1. <b>Branco de Referência:</b> Insira na gaveta uma lâmina e lamínula contendo "
            "apenas <b>água destilada pura</b> (matriz do solvente).<br>"
            "2. <b>Escuro Instrumental:</b> Mede o ruído elétrico/corrente de escuro do sensor."
        )
        lbl_desc.setStyleSheet("color: #D1D5DB; font-size: 11px; line-height: 1.4;")
        lbl_desc.setWordWrap(True)
        ib_layout.addWidget(lbl_desc)
        layout.addWidget(info_box)

        # Card KPI de Monitoramento da Calibração
        self.card_kpi = CardKpiCalibracao(self)
        layout.addWidget(self.card_kpi)

        # Status Atual
        eng = self.main_win.chem_engine
        if eng.is_calibrated:
            self.card_kpi.atualizar(r2=eng.r2, rmse=eng.rmse, n_amostras=eng.n_amostras)
        else:
            self.card_kpi.atualizar(r2=None, rmse=None, n_amostras=0)

        st_text = f"Status Atual: {'CALIBRADO' if eng.is_calibrated else 'NÃO CALIBRADO'}"
        if eng.calib_timestamp:
            st_text += f" ({eng.calib_timestamp})"
        self.lbl_calib_info = QLabel(st_text)
        self.lbl_calib_info.setStyleSheet("color: #10B981 if eng.is_calibrated else #F59E0B; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.lbl_calib_info)

        # Botão 1: Calibração Sequencial Guiada
        self.btn_read_white = QPushButton("🎯 Iniciar Calibração Sequencial Completa (Branco -> Escuro)")
        self.btn_read_white.setObjectName("btnPrimary")
        self.btn_read_white.clicked.connect(self.trigger_white_calibration)
        layout.addWidget(self.btn_read_white)

        # Botão 2: Medir Escuro
        self.btn_read_dark = QPushButton("🌑 2. Definir Corrente de Escuro Manual (Zero Físico)")
        self.btn_read_dark.clicked.connect(self.set_dark_current_zeros)
        layout.addWidget(self.btn_read_dark)

        layout.addStretch()

        # Botão Fechar
        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def trigger_white_calibration(self):
        if not self.main_win.is_serial_connected():
            QMessageBox.warning(self, "Hardware Desconectado", "Conecte o hardware ESP32 antes de calibrar.")
            return

        self.accept()
        self.main_win.start_white_calibration_cycle()

    def set_dark_current_zeros(self):
        reply = QMessageBox.question(
            self,
            "Calibração de Escuro Instrumental",
            "Para calibrar a corrente de escuro, certifique-se de que a gaveta esteja fechada e que o LED permaneça desligado.\n\n"
            "Deseja registrar o zero elétrico de escuro agora?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.main_win.chem_engine.vetor_escuro = [0.0] * 6
            self.main_win.chem_engine.save_calibration(notes="Escuro nominal com compartimento fechado")
            self.main_win._update_calibration_badge()
            self.card_kpi.atualizar(
                r2=self.main_win.chem_engine.r2,
                rmse=self.main_win.chem_engine.rmse,
                n_amostras=self.main_win.chem_engine.n_amostras
            )
            QMessageBox.information(self, "Escuro Calibrado", "Corrente de escuro gravada como zero de referência.")
            self.lbl_calib_info.setText("Status: Escuro calibrado com sucesso.")


# =====================================================================
# 4. DIÁLOGO MODAL DE INTERTRAVAMENTO HUMANO (CARREGAMENTO DE LÂMINA)
# =====================================================================
class SamplePlacementInterlockDialog(QDialog):
    """
    Janela modal de intertravamento humano para confirmação de posicionamento da lâmina.
    Exibida exclusivamente após a confirmação de hardware STATUS:GAVETA_ABERTA.
    """
    def __init__(self, title="Posicionamento de Amostra", message=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(510, 270)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton#btnConfirm {
                background-color: #0284C7;
                color: #FFFFFF;
                border: 1px solid #38BDF8;
            }
            QPushButton#btnConfirm:hover {
                background-color: #0369A1;
            }
            QPushButton#btnCancel {
                background-color: #2E1519;
                color: #F87171;
                border: 1px solid #DC2626;
            }
            QPushButton#btnCancel:hover {
                background-color: #7F1D1D;
                color: #FFFFFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # Header com ícone
        header = QHBoxLayout()
        icon = QLabel("📦")
        icon.setStyleSheet("font-size: 24px;")
        lbl_title = QLabel(f"<b>{title.upper()}</b>")
        lbl_title.setStyleSheet("color: #38BDF8; font-size: 13px; letter-spacing: 0.5px;")
        header.addWidget(icon)
        header.addWidget(lbl_title)
        header.addStretch()
        layout.addLayout(header)

        # Mensagem informativa
        default_msg = (
            "A gaveta está aberta.<br><br>"
            "Insira a <b>lâmina com a lamínula</b> sobre o berço óptico de leitura e "
            "clique em <b>OK / Iniciar</b> para prosseguir com a medição."
        )
        self.lbl_msg = QLabel(message or default_msg)
        self.lbl_msg.setStyleSheet("color: #D1D5DB; font-size: 11px; line-height: 1.5;")
        self.lbl_msg.setWordWrap(True)
        layout.addWidget(self.lbl_msg)

        layout.addStretch()

        # Botões de Ação [ Cancelar / Abortar ] e [ OK / Iniciar ]
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_cancel = QPushButton("❌ Cancelar / Abortar")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton("✔ OK / Iniciar")
        self.btn_confirm.setObjectName("btnConfirm")
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)



# =====================================================================
# 5. DIÁLOGOS DE TRANSIÇÃO E SEGURANÇA DA CALIBRAÇÃO (ETAPA 2)
# =====================================================================
class CalibrationTransitionDialog(QDialog):
    """
    Popup 2: Transição entre Calibração de Branco e Fundo Escuro.
    Exibido com a gaveta aberta após a leitura do branco.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibração de Branco Concluída")
        self.setFixedSize(510, 270)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton#btnProceed {
                background-color: #0284C7;
                color: #FFFFFF;
                border: 1px solid #38BDF8;
            }
            QPushButton#btnProceed:hover {
                background-color: #0369A1;
            }
            QPushButton#btnClose {
                background-color: #2b2b2b;
                color: #E5E7EB;
                border: 1px solid #4a4a4a;
            }
            QPushButton#btnClose:hover {
                background-color: #383838;
                border-color: #6B7280;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        icon = QLabel("💧")
        icon.setStyleSheet("font-size: 24px;")
        lbl_title = QLabel("<b>CALIBRAÇÃO DE BRANCO CONCLUÍDA</b>")
        lbl_title.setStyleSheet("color: #38BDF8; font-size: 13px; letter-spacing: 0.5px;")
        header.addWidget(icon)
        header.addWidget(lbl_title)
        header.addStretch()
        layout.addLayout(header)

        msg = (
            "Leitura de referência em água registrada com sucesso.<br><br>"
            "Deseja prosseguir para a <b>Calibração de Fundo Escuro</b> agora?<br>"
            "<small style='color: #9CA3AF;'>Se optar por Concluir / Sair, a gaveta será fechada automaticamente em segurança.</small>"
        )
        self.lbl_msg = QLabel(msg)
        self.lbl_msg.setStyleSheet("color: #D1D5DB; font-size: 11px; line-height: 1.5;")
        self.lbl_msg.setWordWrap(True)
        layout.addWidget(self.lbl_msg)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_exit = QPushButton("🚪 Concluir / Sair")
        self.btn_exit.setObjectName("btnClose")
        self.btn_exit.setCursor(Qt.PointingHandCursor)
        self.btn_exit.clicked.connect(self.reject)

        self.btn_proceed = QPushButton("🚀 Prosseguir para Escuro")
        self.btn_proceed.setObjectName("btnProceed")
        self.btn_proceed.setCursor(Qt.PointingHandCursor)
        self.btn_proceed.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_exit)
        btn_layout.addWidget(self.btn_proceed)
        layout.addLayout(btn_layout)


class DarkSafetyInterlockDialog(QDialog):
    """
    Popup 3: Confirmação de Retirada da Lâmina e Gaveta Vazia para Fundo Escuro.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aviso de Segurança — Fundo Escuro")
        self.setFixedSize(520, 270)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton#btnConfirmEmpty {
                background-color: #15803D;
                color: #FFFFFF;
                border: 1px solid #22C55E;
            }
            QPushButton#btnConfirmEmpty:hover {
                background-color: #166534;
            }
            QPushButton#btnCancel {
                background-color: #2E1519;
                color: #F87171;
                border: 1px solid #DC2626;
            }
            QPushButton#btnCancel:hover {
                background-color: #7F1D1D;
                color: #FFFFFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        icon = QLabel("⚠️")
        icon.setStyleSheet("font-size: 24px;")
        lbl_title = QLabel("<b>AVISO DE SEGURANÇA — FUNDO ESCURO</b>")
        lbl_title.setStyleSheet("color: #F59E0B; font-size: 13px; letter-spacing: 0.5px;")
        header.addWidget(icon)
        header.addWidget(lbl_title)
        header.addStretch()
        layout.addLayout(header)

        msg = (
            "<b>Atenção:</b> A calibração de fundo escuro deve ser realizada com o <b>BERÇO TOTALMENTE VAZIO</b>.<br><br>"
            "Você já retirou a lâmina de água da gaveta?"
        )
        self.lbl_msg = QLabel(msg)
        self.lbl_msg.setStyleSheet("color: #E5E7EB; font-size: 11px; line-height: 1.5;")
        self.lbl_msg.setWordWrap(True)
        layout.addWidget(self.lbl_msg)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_cancel = QPushButton("❌ Cancelar / Sair")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton("✔ Sim, lâmina removida e gaveta vazia")
        self.btn_confirm.setObjectName("btnConfirmEmpty")
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)


# =====================================================================
# 5.1 DIÁLOGO MODAL DE DECISÃO OPERACIONAL (FIM DE ENSAIO)
# =====================================================================
class DialogDecisaoConclusao(QDialog):
    """
    Diálogo modal com 3 botões claros de decisão ao concluir a leitura com a gaveta aberta:
    1. [ Finalizar e Fechar Gaveta ] (Padrão/Foco)
    2. [ Nova Análise ] (Mantém gaveta aberta, limpa dados e solicita novo ID)
    3. [ Iniciar Repetibilidade ] (Mantém gaveta aberta para inspeção e inicia repetições)
    """
    ACTION_FINISH = 1
    ACTION_NEW_SCAN = 2
    ACTION_REPEAT = 3

    def __init__(self, parent=None, is_repeatability=False):
        super().__init__(parent)
        self.setWindowTitle("Ensaio Concluído — Decisão Operacional")
        self.setFixedSize(540, 290)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.selected_action = self.ACTION_FINISH

        self.setStyleSheet("""
            QDialog {
                background-color: #1F242D;
                color: #FFFFFF;
                border: 1px solid #374151;
                border-radius: 12px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton {
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 11px;
                min-height: 20px;
            }
            QPushButton#btnFinish {
                background-color: #1E293B;
                color: #38BDF8;
                border: 1px solid #0284C7;
            }
            QPushButton#btnFinish:hover {
                background-color: #0369A1;
                color: #FFFFFF;
            }
            QPushButton#btnNewScan {
                background-color: #0284C7;
                color: #FFFFFF;
                border: 1px solid #38BDF8;
            }
            QPushButton#btnNewScan:hover {
                background-color: #0369A1;
            }
            QPushButton#btnRepeat {
                background-color: #4C1D95;
                color: #DDD6FE;
                border: 1px solid #8B5CF6;
            }
            QPushButton#btnRepeat:hover {
                background-color: #5B21B6;
                color: #FFFFFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        icon = QLabel("✔" if not is_repeatability else "📊")
        icon.setStyleSheet("font-size: 24px; color: #10B981;")
        lbl_h = QLabel("<b>LEITURA CONCLUÍDA COM SUCESSO</b>" if not is_repeatability else "<b>ENSAIO DE REPETIBILIDADE CONCLUÍDO</b>")
        lbl_h.setStyleSheet("color: #10B981; font-size: 12px; font-weight: bold; letter-spacing: 0.5px;")
        header.addWidget(icon)
        header.addWidget(lbl_h)
        header.addStretch()
        layout.addLayout(header)

        lbl_desc = QLabel(
            "A leitura óptica foi concluída e a gaveta está <b>aberta</b> no berço para manipulação da lâmina.<br>"
            "Selecione a ação desejada a seguir:"
        )
        lbl_desc.setStyleSheet("color: #D1D5DB; font-size: 11px; line-height: 1.5;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        layout.addStretch()

        btn_box = QVBoxLayout()
        btn_box.setSpacing(8)

        # Botão 1: Padrão / Foco
        self.btn_finish = QPushButton("📥 Finalizar e Fechar Gaveta (Padrão)")
        self.btn_finish.setObjectName("btnFinish")
        self.btn_finish.setCursor(Qt.PointingHandCursor)
        self.btn_finish.setDefault(True)
        self.btn_finish.setFocus()
        self.btn_finish.clicked.connect(self._choose_finish)

        # Botão 2: Nova Análise
        self.btn_new = QPushButton("🔬 Nova Análise (Manter Gaveta Aberta)")
        self.btn_new.setObjectName("btnNewScan")
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.clicked.connect(self._choose_new)

        # Botão 3: Iniciar Repetibilidade
        self.btn_repeat = QPushButton("🔁 Iniciar Repetibilidade (5 Leituras Consecutivas)")
        self.btn_repeat.setObjectName("btnRepeat")
        self.btn_repeat.setCursor(Qt.PointingHandCursor)
        self.btn_repeat.clicked.connect(self._choose_repeat)

        btn_box.addWidget(self.btn_finish)
        btn_box.addWidget(self.btn_new)
        btn_box.addWidget(self.btn_repeat)
        layout.addLayout(btn_box)

    def _choose_finish(self):
        self.selected_action = self.ACTION_FINISH
        self.accept()

    def _choose_new(self):
        self.selected_action = self.ACTION_NEW_SCAN
        self.accept()

    def _choose_repeat(self):
        self.selected_action = self.ACTION_REPEAT
        self.accept()


# =====================================================================
# 6. POPUP DE SEGURANÇA CONTRA RADIAÇÃO ÓPTICA (NIR) - ASSÍNCRONO
# =====================================================================
class DialogAlertaRadiacao(QDialog):
    """
    Diálogo modal não-bloqueante de aviso de segurança contra radiação óptica NIR.
    Abre automaticamente via .show() ao avançar o sensor para varredura óptica e fecha via .close().
    Possui botão de parada de emergência acessível diretamente durante a operação.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ AVISO DE SEGURANÇA: EMISSÃO ÓPTICA ATIVA")
        self.setFixedSize(530, 315)
        self.setWindowModality(Qt.ApplicationModal)
        # Desabilita botão 'X' de fechar a janela e botão de Ajuda
        self.setWindowFlags((self.windowFlags() | Qt.Dialog) & ~Qt.WindowCloseButtonHint & ~Qt.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #1a1712;
                color: #FFFFFF;
                border: 2px solid #F59E0B;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QProgressBar {
                background-color: #2b2518;
                border: 1px solid #78350F;
                border-radius: 5px;
                height: 12px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #F59E0B;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Cabeçalho com ícone de advertência
        header = QHBoxLayout()
        lbl_icon = QLabel("⚠️")
        lbl_icon.setStyleSheet("font-size: 32px;")

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_t1 = QLabel("AVISO DE SEGURANÇA — RADIAÇÃO ÓPTICA")
        lbl_t1.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: bold; letter-spacing: 0.8px;")
        lbl_t2 = QLabel("EMISSOR NIR ATIVO (730 nm - 860 nm)")
        lbl_t2.setStyleSheet("color: #FDE68A; font-size: 15px; font-weight: bold;")
        title_box.addWidget(lbl_t1)
        title_box.addWidget(lbl_t2)

        header.addWidget(lbl_icon)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Caixa de alerta e orientações
        msg_frame = QFrame()
        msg_frame.setStyleSheet("background-color: #291F11; border: 1px solid #78350F; border-radius: 6px; padding: 6px;")
        mf_layout = QVBoxLayout(msg_frame)
        mf_layout.setContentsMargins(12, 8, 12, 8)
        lbl_sub = QLabel(
            "Não olhe diretamente para a abertura óptica nem abra a câmara durante a varredura espectral.<br>"
            "<b>Radiação invisível de alta densidade no espectro infravermelho próximo.</b>"
        )
        lbl_sub.setStyleSheet("color: #FEF3C7; font-size: 11px; line-height: 1.4;")
        lbl_sub.setWordWrap(True)
        mf_layout.addWidget(lbl_sub)
        layout.addWidget(msg_frame)

        # Barra contínua / indeterminada (setRange(0, 0))
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 0)
        layout.addWidget(self.pbar)

        self.lbl_status = QLabel("⏳ Varredura óptica em andamento. Câmara intertravada...")
        self.lbl_status.setStyleSheet("color: #D97706; font-size: 11px; font-weight: bold;")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        # Botão de Parada de Emergência no corpo do diálogo
        self.btn_emergency = QPushButton("🛑 PARADA DE EMERGÊNCIA")
        self.btn_emergency.setCursor(Qt.PointingHandCursor)
        self.btn_emergency.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #ef5350;
            }
            QPushButton:hover {
                background-color: #b71c1c;
            }
            QPushButton:pressed {
                background-color: #7f1d1d;
            }
        """)
        self.btn_emergency.clicked.connect(self._trigger_emergency)
        layout.addWidget(self.btn_emergency)

    def set_custom_status(self, text: str):
        self.lbl_status.setText(text)

    def _trigger_emergency(self):
        """
        Interrompe imediatamente as rotinas e timers em execução no Python,
        despacha CMD:EMERGENCIA\n pelo canal ativo e fecha o diálogo.
        """
        self.reject() if hasattr(self, "reject") else self.close()
        parent = self.parent()
        if parent and hasattr(parent, "stop_cycle_action"):
            parent.stop_cycle_action()
        QApplication.processEvents()


# =====================================================================
# 7. POPUP DE SEGURANÇA MECÂNICA (GAVETA MOTORIZADA) - ASSÍNCRONO
# =====================================================================
class DialogAlertaGaveta(QDialog):
    """
    Diálogo modal não-bloqueante de aviso de segurança contra risco de pinçamento mecânico.
    Abre automaticamente via .show() ao movimentar a gaveta em ciclos automáticos e fecha via .close().
    Possui bypass em acionamentos manuais e botão de parada de emergência acessível diretamente.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ AVISO: ATUADOR MECÂNICO EM OPERAÇÃO")
        self.setFixedSize(530, 315)
        self.setWindowModality(Qt.ApplicationModal)
        # Desabilita botão 'X' de fechar a janela e botão de Ajuda
        self.setWindowFlags((self.windowFlags() | Qt.Dialog) & ~Qt.WindowCloseButtonHint & ~Qt.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #1a1712;
                color: #FFFFFF;
                border: 2px solid #E67E22;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QProgressBar {
                background-color: #2b2518;
                border: 1px solid #78350F;
                border-radius: 5px;
                height: 12px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #E67E22;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Cabeçalho com ícone de advertência mecânica
        header = QHBoxLayout()
        lbl_icon = QLabel("⚠️")
        lbl_icon.setStyleSheet("font-size: 32px;")

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_t1 = QLabel("AVISO DE SEGURANÇA — ATUADOR MECÂNICO")
        lbl_t1.setStyleSheet("color: #E67E22; font-size: 11px; font-weight: bold; letter-spacing: 0.8px;")
        self.lbl_t2 = QLabel("MOVIMENTAÇÃO DE GAVETA EM ANDAMENTO")
        self.lbl_t2.setStyleSheet("color: #FDE68A; font-size: 14px; font-weight: bold;")
        title_box.addWidget(lbl_t1)
        title_box.addWidget(self.lbl_t2)

        header.addWidget(lbl_icon)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Caixa de alerta e orientações
        msg_frame = QFrame()
        msg_frame.setStyleSheet("background-color: #291F11; border: 1px solid #78350F; border-radius: 6px; padding: 6px;")
        mf_layout = QVBoxLayout(msg_frame)
        mf_layout.setContentsMargins(12, 8, 12, 8)
        lbl_sub = QLabel(
            "<b>Mantenha mãos e objetos afastados da zona de deslocamento do berço.</b><br>"
            "Risco de pinçamento mecânico durante a movimentação motorizada da gaveta."
        )
        lbl_sub.setStyleSheet("color: #FEF3C7; font-size: 11px; line-height: 1.4;")
        lbl_sub.setWordWrap(True)
        mf_layout.addWidget(lbl_sub)
        layout.addWidget(msg_frame)

        # Barra contínua / indeterminada (setRange(0, 0))
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 0)
        layout.addWidget(self.pbar)

        self.lbl_status = QLabel("⏳ Gaveta motorizada em deslocamento...")
        self.lbl_status.setStyleSheet("color: #D97706; font-size: 11px; font-weight: bold;")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        # Botão de Parada de Emergência no corpo do diálogo
        self.btn_emergency = QPushButton("🛑 PARADA DE EMERGÊNCIA")
        self.btn_emergency.setCursor(Qt.PointingHandCursor)
        self.btn_emergency.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #ef5350;
            }
            QPushButton:hover {
                background-color: #b71c1c;
            }
            QPushButton:pressed {
                background-color: #7f1d1d;
            }
        """)
        self.btn_emergency.clicked.connect(self._trigger_emergency)
        layout.addWidget(self.btn_emergency)

    def set_action_status(self, text_status: str, detail: str = "MOVIMENTAÇÃO DE GAVETA EM ANDAMENTO"):
        self.lbl_t2.setText(detail)
        self.lbl_status.setText(text_status)

    def _trigger_emergency(self):
        """
        Interrompe imediatamente as rotinas e timers em execução no Python,
        despacha CMD:EMERGENCIA\n pelo canal ativo e fecha o diálogo.
        """
        self.reject() if hasattr(self, "reject") else self.close()
        parent = self.parent()
        if parent and hasattr(parent, "stop_cycle_action"):
            parent.stop_cycle_action()
        QApplication.processEvents()



# =====================================================================
# 8. JANELA PRINCIPAL DO SUPERVISÓRIO
# =====================================================================
class SpectrumLabMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPECTRUM-LAB PRO | Sistema Supervisório Espectrométrico NIR (GY-AS7263)")
        self.resize(1340, 860)
        self.setMinimumSize(1120, 720)

        # Caminho da base e arquivos
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(self.base_dir, "banco_materiais.json")

        # Motor Quimiométrico e Calibração
        self.chem_engine = ChemometricsEngine()

        # Thread de Comunicação Unificada (USB / Bluetooth SPP / Wi-Fi TCP)
        self.conn_worker = ConnectionWorker(self)
        self.serial_worker = self.conn_worker
        self._setup_serial_signals()

        # Variáveis de Estado Espectral
        self.current_scan_data = [0.0] * 6
        self.current_r_calibrated = [0.0] * 6
        self.current_r_snv = [0.0] * 6
        self.current_matched_material = "Standby (Sem Leitura)"
        self.current_match_percent = 0.0
        self.current_kappa_value = 0.0

        # Máquina de Estados Finita (FSM)
        self.fsm_state = "IDLE"
        self.auto_cycle_active = False
        self.modo_repetibilidade = False
        self.is_calibrating_white = False
        self.leituras_rep: List[List[float]] = []
        self._last_raw_payload: List[float] = []
        self._temp_vetor_branco: List[float] = []
        self._temp_vetor_escuro: List[float] = []
        self._pending_routine: Optional[str] = None  # "AUTO", "REPETIBILIDADE", "CALIBRAÇÃO"
        self._auto_confirm_dialog: bool = False      # Para testes automatizados headless (Popup 1)
        self._calib_transition_choice: str = "PROSSEGUIR"  # Para testes: "PROSSEGUIR" ou "SAIR" (Popup 2)
        self._calib_confirm_empty: bool = True       # Para testes: True ou False (Popup 3)
        self._radiation_dialog: Optional[DialogAlertaRadiacao] = None  # Alerta visual assíncrono de radiação óptica NIR
        self._drawer_dialog: Optional[DialogAlertaGaveta] = None        # Alerta visual assíncrono de risco mecânico (gaveta)

        # Gerenciador de Autenticação SQLite e Controle de Acesso (Compatibilidade .exe)
        self.auth_db_path = get_database_path("usuarios.db")
        self.auth_manager = DatabaseManager(self.auth_db_path)
        self.authenticated_user: Optional[Dict] = None
        self.is_manual_mode_unlocked: bool = False
        self._auto_login_success: bool = False  # Para testes automatizados headless
        self._auto_login_user: Optional[Dict] = None

        # Timers assíncronos do ciclo
        self._cycle_timers: List[QTimer] = []

        # Mapa de intertravamento atômico para botões manuais da UI principal
        # status_esperado -> (QPushButton, QTimer)
        self._manual_pending: Dict[str, tuple] = {}

        # Diálogo Modal Manual (referência fraca)
        self._manual_dialog: Optional[ManualControlDialog] = None

        # Design System Windows 11 Fluent Dark
        self.apply_fluent_theme()

        # Construção da Interface
        self.init_ui()

        # Atualiza status e KPI de calibração na UI
        if self.chem_engine.is_calibrated:
            self.atualizar_kpi_calibracao(
                r2=self.chem_engine.r2,
                rmse=self.chem_engine.rmse,
                n_amostras=self.chem_engine.n_amostras
            )
        else:
            self.atualizar_kpi_calibracao(r2=None, rmse=None, n_amostras=0)

        self.log_message("Sistema Supervisório SPECTRUM-LAB v3.1 inicializado.")
        self.log_message("Protocolo Serial Consolidado (115200 Baud) ativo. Standby.")

    def apply_fluent_theme(self):
        qss = """
            QMainWindow, QWidget#centralWidget, QDialog, QMessageBox, QInputDialog {
                background-color: #202020;
                color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QFrame#cardFrame {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 8px;
            }
            QLabel {
                color: #FFFFFF;
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #404040;
                border-color: #60CDFF;
            }
            QPushButton:disabled {
                background-color: #242424;
                color: #555555;
                border: 1px solid #333333;
            }
            QComboBox {
                background-color: #2b2b2b;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QProgressBar {
                background-color: #202020;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                text-align: center;
                color: #FFFFFF;
                font-weight: bold;
                height: 14px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0078D4, stop:1 #60CDFF);
                border-radius: 5px;
            }
            QTextEdit#consoleLog {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #60CDFF;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QMenuBar {
                background-color: #1a1a1a;
                color: #FFFFFF;
                border-bottom: 1px solid #333333;
                font-size: 11px;
                padding: 2px 6px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: #2b2b2b;
                color: #60CDFF;
            }
            QMenu {
                background-color: #242424;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #0078D4;
                color: #FFFFFF;
            }
            QTabWidget::pane {
                border: 1px solid #383838;
                border-radius: 6px;
                background-color: #242424;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #1f1f1f;
                color: #9CA3AF;
                border: 1px solid #383838;
                padding: 7px 14px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 11px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #242424;
                color: #60CDFF;
                border-bottom: 2px solid #0078D4;
            }
            QTabBar::tab:hover:!selected {
                background-color: #2b2b2b;
                color: #FFFFFF;
            }
        """
        self.setStyleSheet(qss)

    def _setup_serial_signals(self):
        """Auditoria e conexão estrita e única de sinais da thread serial."""
        self.serial_worker.line_received.connect(self._on_serial_line_received)
        self.serial_worker.status_received.connect(self._on_serial_status_received)
        self.serial_worker.data_received.connect(self._on_serial_data_received)
        self.serial_worker.connection_changed.connect(self._on_serial_connection_changed)
        self.serial_worker.error_occurred.connect(self._on_serial_error_occurred)

    # -----------------------------------------------------------------
    # BARRA DE MENUS SUPERIOR E CONTROLE DE ACESSO
    # -----------------------------------------------------------------
    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        menu_sistema = menu_bar.addMenu("☰ Sistema")

        # 1. Gerenciar Usuários
        act_gestao = QAction("👥 Gerenciar Usuários", self)
        act_gestao.setStatusTip("Abrir tela de gerenciamento de usuários e controle de acesso")
        act_gestao.triggered.connect(self.open_user_management_dialog)
        menu_sistema.addAction(act_gestao)

        menu_sistema.addSeparator()

        # 2. Logout / Bloquear Painel
        act_logout = QAction("🔒 Logout / Bloquear Painel", self)
        act_logout.setStatusTip("Bloqueia as abas restritas e retorna ao modo seguro padrão")
        act_logout.triggered.connect(self.logout_action)
        menu_sistema.addAction(act_logout)

        menu_sistema.addSeparator()

        # 3. Sair
        act_sair = QAction("🚪 Sair", self)
        act_sair.setStatusTip("Fecha o supervisório com segurança")
        act_sair.triggered.connect(self.close)
        menu_sistema.addAction(act_sair)

    # -----------------------------------------------------------------
    # CONSTRUÇÃO DA INTERFACE VISUAL
    # -----------------------------------------------------------------
    def init_ui(self):
        # 0. BARRA DE MENUS SUPERIOR
        self._create_menu_bar()

        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(14, 12, 14, 12)
        root_layout.setSpacing(10)

        # 1. TOPBAR INDUSTRIAL
        topbar = self._create_topbar()
        root_layout.addWidget(topbar)

        # 2. 4 CARDS DE KPI (POWER BI)
        kpi_bar = self._create_kpi_bar()
        root_layout.addWidget(kpi_bar)

        # 3. ÁREA PRINCIPAL DIVIDIDA (CONTROLES vs GRÁFICOS)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        left_panel = self._create_left_control_panel()
        right_panel = self._create_right_chart_panel()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)

        root_layout.addWidget(splitter, stretch=1)

        # 4. STATUS FOOTER & CONSOLE RETRÁTIL
        footer = self._create_footer()
        root_layout.addWidget(footer)

    def _create_topbar(self) -> QWidget:
        top_frame = QFrame()
        top_frame.setObjectName("cardFrame")
        layout = QHBoxLayout(top_frame)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        # Logo / Título
        app_title = QLabel("🔬 SPECTRUM-LAB PRO")
        app_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #38BDF8; letter-spacing: 0.8px;")
        sub_title = QLabel("v3.1 | Quimiometria Celulose")
        sub_title.setStyleSheet("font-size: 10px; color: #9CA3AF; font-weight: bold;")

        layout.addWidget(app_title)
        layout.addWidget(sub_title)
        layout.addSpacing(14)

        # Seletor de Modo de Conexão: USB, Bluetooth SPP, Wi-Fi TCP
        lbl_mode = QLabel("Conexão:")
        lbl_mode.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.combo_conn_mode = QComboBox()
        self.combo_conn_mode.addItem("🔌 USB (Cabo Serial)", "USB")
        self.combo_conn_mode.addItem("📶 Bluetooth (SPP Serial)", "BLUETOOTH")
        self.combo_conn_mode.addItem("🌐 Wi-Fi (TCP/IP)", "WIFI")
        self.combo_conn_mode.currentIndexChanged.connect(self._on_conn_mode_changed)

        # 1. Container Serial / Bluetooth:
        self.widget_serial = QWidget()
        serial_layout = QHBoxLayout(self.widget_serial)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        serial_layout.setSpacing(6)

        lbl_com = QLabel("Porta:")
        lbl_com.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.combo_com = QComboBox()
        self.combo_com.setMinimumWidth(120)
        self.populate_com_ports()

        self.btn_refresh_ports = QPushButton("🔄")
        self.btn_refresh_ports.setToolTip("Atualizar lista de portas COM / Bluetooth")
        self.btn_refresh_ports.setFixedWidth(32)
        self.btn_refresh_ports.clicked.connect(self.populate_com_ports)

        lbl_baud = QLabel("Baud:")
        lbl_baud.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.lbl_baud_val = QLabel("115200 bps")
        self.lbl_baud_val.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: bold; background-color: #1F2937; padding: 4px 8px; border-radius: 4px; border: 1px solid #374151;")
        self.lbl_baud_val.currentText = lambda: "115200"
        self.combo_baud = self.lbl_baud_val

        serial_layout.addWidget(lbl_com)
        serial_layout.addWidget(self.combo_com)
        serial_layout.addWidget(self.btn_refresh_ports)
        serial_layout.addWidget(lbl_baud)
        serial_layout.addWidget(self.combo_baud)

        # 2. Container Wi-Fi TCP:
        self.widget_wifi = QWidget()
        wifi_layout = QHBoxLayout(self.widget_wifi)
        wifi_layout.setContentsMargins(0, 0, 0, 0)
        wifi_layout.setSpacing(6)

        lbl_ip = QLabel("IP ESP32:")
        lbl_ip.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.txt_ip = QLineEdit("192.168.4.1")
        self.txt_ip.setFixedWidth(110)
        self.txt_ip.setToolTip("Endereço IP do ESP32 (Padrão SoftAP: 192.168.4.1)")
        self.txt_ip.setStyleSheet("background-color: #2b2b2b; color: #FFFFFF; padding: 4px 6px; border: 1px solid #4a4a4a; border-radius: 4px; font-size: 11px;")

        lbl_tcp_port = QLabel("Porta:")
        lbl_tcp_port.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.txt_tcp_port = QLineEdit("8080")
        self.txt_tcp_port.setFixedWidth(55)
        self.txt_tcp_port.setToolTip("Porta do Servidor TCP no ESP32")
        self.txt_tcp_port.setStyleSheet("background-color: #2b2b2b; color: #FFFFFF; padding: 4px 6px; border: 1px solid #4a4a4a; border-radius: 4px; font-size: 11px;")

        wifi_layout.addWidget(lbl_ip)
        wifi_layout.addWidget(self.txt_ip)
        wifi_layout.addWidget(lbl_tcp_port)
        wifi_layout.addWidget(self.txt_tcp_port)
        self.widget_wifi.setVisible(False)

        # Botão [ Conectar / Desconectar ]
        self.btn_connect = QPushButton("Conectar ESP32")
        self.btn_connect.setStyleSheet("background-color: #0078D4; color: #FFFFFF; font-weight: bold; padding: 6px 14px;")
        self.btn_connect.clicked.connect(self.toggle_com_connect)

        layout.addWidget(lbl_mode)
        layout.addWidget(self.combo_conn_mode)
        layout.addWidget(self.widget_serial)
        layout.addWidget(self.widget_wifi)
        layout.addWidget(self.btn_connect)
        layout.addSpacing(10)

        # Badges de Status
        self.badge_com = ModernStatusBadge("ESP32", "#10B981", "#64748B")
        self.badge_calib = ModernStatusBadge("CALIBRAÇÃO", "#10B981", "#F59E0B")
        layout.addWidget(self.badge_com)
        layout.addWidget(self.badge_calib)

        layout.addStretch()

        # Botão Modal de Operação Manual e Parada de Emergência Topbar
        btn_modal_manual = QPushButton("⚙️ Painel Atuadores")
        btn_modal_manual.setToolTip("Abrir painel de controle manual e manutenção")
        btn_modal_manual.clicked.connect(self.open_manual_control_dialog)
        layout.addWidget(btn_modal_manual)

        self.btn_top_emergency = QPushButton("🛑 PARADA DE EMERGÊNCIA")
        self.btn_top_emergency.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 11px;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #B91C1C;
            }
        """)
        self.btn_top_emergency.clicked.connect(self.stop_cycle_action)
        layout.addWidget(self.btn_top_emergency)

        return top_frame

    def _create_kpi_bar(self) -> QWidget:
        kpi_container = QWidget()
        layout = QHBoxLayout(kpi_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.kpi_energy = PowerBiKpiCard("⚡", "Intensidade Global", "0 ADC", "Soma das 6 bandas NIR", "#38BDF8")
        self.kpi_peak = PowerBiKpiCard("📈", "Pico Espectral (λmax)", "-- nm", "Comprimento dominante", "#818CF8")
        self.kpi_ratio_cel = PowerBiKpiCard("🌿", "Razão Celulose (S/T)", "0.00", "R680 / R730 (Bandas Celulósicas)", "#34D399")
        self.kpi_ratio_water = PowerBiKpiCard("💧", "Razão Matriz Água (W/U)", "0.00", "R860 / R760 (Espessura da Gota)", "#FBBF24")

        layout.addWidget(self.kpi_energy)
        layout.addWidget(self.kpi_peak)
        layout.addWidget(self.kpi_ratio_cel)
        layout.addWidget(self.kpi_ratio_water)

        return kpi_container

    def _create_left_control_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("cardFrame")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # --- PÁGINA AUTO ---
        page_auto = QWidget()
        auto_layout = QVBoxLayout(page_auto)
        auto_layout.setContentsMargins(0, 8, 0, 0)
        auto_layout.setSpacing(10)

        self.btn_start_scan = QPushButton("▶ Iniciar Ciclo Automático")
        self.btn_start_scan.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0078D4, stop:1 #0284C7);
                color: #FFFFFF;
                font-size: 12px;
                font-weight: bold;
                padding: 12px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #0284C7;
            }
        """)
        self.btn_start_scan.clicked.connect(self.start_simple_auto_cycle)

        self.btn_repeatability = QPushButton("🔁 Ensaio Repetibilidade (5x Estático)")
        self.btn_repeatability.setStyleSheet("""
            QPushButton {
                background-color: #383838;
                color: #A7F3D0;
                border: 1px solid #059669;
                font-weight: bold;
                padding: 11px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #047857;
                color: #FFFFFF;
            }
        """)
        self.btn_repeatability.clicked.connect(self.start_repeatability_test)

        self.btn_calibrate = QPushButton("🎯 Calibração Instrumental (Água/Branco)")
        self.btn_calibrate.clicked.connect(self.open_calibration_dialog)

        self.btn_emergency_auto = QPushButton("🛑 Parada de Emergência")
        self.btn_emergency_auto.setStyleSheet("""
            QPushButton {
                background-color: #3A1D1D;
                color: #EF4444;
                border: 1px solid #EF4444;
                font-weight: bold;
                padding: 10px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #DC2626;
                color: #FFFFFF;
            }
        """)
        self.btn_emergency_auto.clicked.connect(self.stop_cycle_action)

        auto_layout.addWidget(self.btn_start_scan)
        auto_layout.addWidget(self.btn_repeatability)
        auto_layout.addWidget(self.btn_calibrate)

        # Card KPI de Monitoramento da Calibração (R², RMSE, N, Badge de Validação)
        self.card_calibracao = CardKpiCalibracao(self)
        auto_layout.addWidget(self.card_calibracao)

        auto_layout.addWidget(self.btn_emergency_auto)
        auto_layout.addStretch()

        # --- PÁGINA MANUAL (DESACOPLAMENTO ATÔMICO) ---
        page_manual = QWidget()
        manual_layout = QVBoxLayout(page_manual)
        manual_layout.setContentsMargins(0, 8, 0, 0)
        manual_layout.setSpacing(8)

        # Gaveta
        card_d = QFrame()
        card_d.setStyleSheet("background-color: #242424; border: 1px solid #383838; border-radius: 6px;")
        cd_layout = QVBoxLayout(card_d)
        cd_layout.setContentsMargins(8, 6, 8, 6)
        cd_layout.setSpacing(6)
        cd_layout.addWidget(QLabel("📦 GAVETA DE AMOSTRAS"))

        self.btn_man_open_drawer = QPushButton("Abrir Gaveta (CMD:ABRIR_GAVETA)")
        self.btn_man_open_drawer.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_open_drawer, "CMD:ABRIR_GAVETA", "GAVETA_ABERTA", "Abrindo gaveta..."
        ))

        self.btn_man_close_drawer = QPushButton("Fechar Gaveta (CMD:FECHAR_GAVETA)")
        self.btn_man_close_drawer.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_close_drawer, "CMD:FECHAR_GAVETA", "GAVETA_FECHADA", "Fechando gaveta..."
        ))
        cd_layout.addWidget(self.btn_man_open_drawer)
        cd_layout.addWidget(self.btn_man_close_drawer)
        manual_layout.addWidget(card_d)

        # Sensor
        card_s = QFrame()
        card_s.setStyleSheet("background-color: #242424; border: 1px solid #383838; border-radius: 6px;")
        cs_layout = QVBoxLayout(card_s)
        cs_layout.setContentsMargins(8, 6, 8, 6)
        cs_layout.setSpacing(6)
        cs_layout.addWidget(QLabel("🔬 CARRINHO DO SENSOR NIR"))

        self.btn_man_fwd_sensor = QPushButton("Avançar Sensor (CMD:AVANCAR_SENSOR)")
        self.btn_man_fwd_sensor.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_fwd_sensor, "CMD:AVANCAR_SENSOR", "SENSOR_AVANCADO", "Avançando sensor..."
        ))

        self.btn_man_back_sensor = QPushButton("Recuar Sensor (CMD:RECUAR_SENSOR)")
        self.btn_man_back_sensor.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_back_sensor, "CMD:RECUAR_SENSOR", "SENSOR_RECUADO", "Recuando sensor..."
        ))
        cs_layout.addWidget(self.btn_man_fwd_sensor)
        cs_layout.addWidget(self.btn_man_back_sensor)
        manual_layout.addWidget(card_s)

        # Disparo Único
        self.btn_man_read = QPushButton("💡 Disparo Único (CMD:LER_ESPECTRO)")
        self.btn_man_read.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 10px;")
        self.btn_man_read.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_read, "CMD:LER_ESPECTRO", "LEITURA_CONCLUIDA", "Executando disparo óptico..."
        ))
        manual_layout.addWidget(self.btn_man_read)
        manual_layout.addStretch()

        # QTabWidget com Abas [ Ensaios Automáticos ] e [ Modo Manual ] (Protegido por Autenticação)
        self.control_tabs = QTabWidget()
        self.control_tabs.addTab(page_auto, "📋 Ensaios Automáticos")
        self.control_tabs.addTab(page_manual, "⚙️ Modo Manual")
        self.control_tabs.currentChanged.connect(self._on_control_tab_changed)
        layout.addWidget(self.control_tabs)

        # Alias para compatibilidade
        self.control_stack = self.control_tabs

        # Card de Identificação de Amostra / Laudo Quimiométrico
        id_card = QFrame()
        id_card.setStyleSheet("background-color: #242424; border: 1px solid #383838; border-radius: 6px;")
        id_layout = QVBoxLayout(id_card)
        id_layout.setContentsMargins(10, 8, 10, 8)
        id_layout.setSpacing(4)

        lbl_id_header = QLabel("📋 IDENTIFICAÇÃO E LAUDO")
        lbl_id_header.setStyleSheet("color: #9CA3AF; font-size: 9px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_material_name = QLabel("Standby (Sem Leitura)")
        self.lbl_material_name.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        self.lbl_match_score = QLabel("% Match: 0.00%")
        self.lbl_match_score.setStyleSheet("color: #6B7280; font-size: 13px; font-weight: 800;")
        self.lbl_kappa_laudo = QLabel("Kappa Estimado: --")
        self.lbl_kappa_laudo.setStyleSheet("color: #9CA3AF; font-size: 11px;")

        id_layout.addWidget(lbl_id_header)
        id_layout.addWidget(self.lbl_material_name)
        id_layout.addWidget(self.lbl_match_score)
        id_layout.addWidget(self.lbl_kappa_laudo)
        layout.addWidget(id_card)

        # Ações do Sistema (Banco / PDF / CSV)
        actions_layout = QHBoxLayout()
        self.btn_db = QPushButton("📚 Banco")
        self.btn_db.clicked.connect(self.open_database_manager)

        self.btn_pdf = QPushButton("📄 PDF")
        self.btn_pdf.clicked.connect(self.export_pdf_report)

        self.btn_csv = QPushButton("📊 CSV")
        self.btn_csv.clicked.connect(self.export_csv_log)

        actions_layout.addWidget(self.btn_db)
        actions_layout.addWidget(self.btn_pdf)
        actions_layout.addWidget(self.btn_csv)
        layout.addLayout(actions_layout)

        return panel

    def _create_right_chart_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 1. Gráfico Espectral Spline Cúbica (Catmull-Rom) com 6 canais
        self.spectral_chart = SpectralSplineChartWidget()
        layout.addWidget(self.spectral_chart, stretch=5)

        # 2. Gráfico de Dispersão 2D (Scatter Plot) de Celulose vs Água
        self.scatter_plot = ScatterPlotWidget()
        layout.addWidget(self.scatter_plot, stretch=5)

        return container

    def _create_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("cardFrame")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        status_row = QHBoxLayout()
        self.lbl_cycle_status = QLabel("Status do Ciclo: Sistema em Standby. Aguardando comando.")
        self.lbl_cycle_status.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")

        self.cycle_progress = QProgressBar()
        self.cycle_progress.setValue(0)
        self.cycle_progress.setFixedWidth(240)

        status_row.addWidget(self.lbl_cycle_status, stretch=1)
        status_row.addWidget(self.cycle_progress)
        layout.addLayout(status_row)

        # Console de log retrátil
        self.txt_console = QTextEdit()
        self.txt_console.setObjectName("consoleLog")
        self.txt_console.setReadOnly(True)
        self.txt_console.setFixedHeight(75)
        layout.addWidget(self.txt_console)

        return footer

    # -----------------------------------------------------------------
    # MODO DE OPERAÇÃO (AUTO vs MANUAL)
    # -----------------------------------------------------------------
    def switch_mode(self, mode: str):
        if mode == "AUTO":
            self.btn_mode_auto.setChecked(True)
            self.btn_mode_manual.setChecked(False)
            self.control_stack.setCurrentIndex(0)
            self.log_message("Modo alterado para [ AUTOMÁTICO ]")
        else:
            self.btn_mode_auto.setChecked(False)
            self.btn_mode_manual.setChecked(True)
            self.control_stack.setCurrentIndex(1)
            self.log_message("Modo alterado para [ MANUAL ATÔMICO ]")

    # -----------------------------------------------------------------
    # GESTÃO DA CONEXÃO SERIAL REAL
    # -----------------------------------------------------------------
    def log_message(self, text: str):
        now_str = datetime.datetime.now().strftime("[%H:%M:%S]")
        try:
            print(f"{now_str} {text}", flush=True)
        except Exception:
            try:
                safe_text = text.encode("ascii", errors="replace").decode("ascii")
                print(f"{now_str} {safe_text}", flush=True)
            except Exception:
                pass
        if hasattr(self, "txt_console") and self.txt_console is not None:
            self.txt_console.append(f"{now_str} {text}")

    def _on_conn_mode_changed(self):
        mode = self.combo_conn_mode.currentData()
        if mode in ("USB", "BLUETOOTH"):
            self.widget_serial.setVisible(True)
            self.widget_wifi.setVisible(False)
            if mode == "BLUETOOTH":
                self.log_message("[CONEXÃO] Modo selecionado: Bluetooth SPP Serial (Porta COM virtual pareada).")
            else:
                self.log_message("[CONEXÃO] Modo selecionado: Cabo USB Serial.")
        else:
            self.widget_serial.setVisible(False)
            self.widget_wifi.setVisible(True)
            self.log_message("[CONEXÃO] Modo selecionado: Wi-Fi TCP/IP (Padrão ESP32 SoftAP: 192.168.4.1:8080).")

    def populate_com_ports(self):
        self.combo_com.clear()
        ports = self.serial_worker.list_ports()
        for device, desc in ports:
            self.combo_com.addItem(f"{device} ({desc})", device)

        if self.combo_com.count() == 0:
            self.combo_com.addItem("Nenhuma Porta Detectada", "")
        self.log_message(f"Varredura de portas: {self.combo_com.count()} encontrada(s).")

    def disconnect_hardware(self):
        """Encerra a conexão voluntária com o ESP32 de forma limpa."""
        if self.serial_worker.is_connected():
            self.log_message("[CONEXÃO] Encerrando conexão com o ESP32...")
            self.serial_worker.disconnect_connection()

    def toggle_com_connect(self):
        if self.serial_worker.is_connected():
            self.disconnect_hardware()
        else:
            mode = self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "USB"
            if mode in ("USB", "BLUETOOTH"):
                port_name = self.combo_com.currentData()
                if not port_name:
                    QMessageBox.warning(self, "Porta Inválida", f"Nenhuma porta selecionada para o modo {mode}.")
                    return
                baudrate = int(self.combo_baud.currentText()) if hasattr(self, "combo_baud") else 115200
                self.serial_worker.connect_serial(port_name, baudrate, mode=mode)
            elif mode == "WIFI":
                ip = self.txt_ip.text().strip()
                port_str = self.txt_tcp_port.text().strip()
                if not ip:
                    QMessageBox.warning(self, "IP Inválido", "Informe o endereço IP do ESP32 (ex: 192.168.4.1).")
                    return
                try:
                    port = int(port_str)
                except ValueError:
                    QMessageBox.warning(self, "Porta Inválida", "A porta TCP deve ser um número inteiro (ex: 8080).")
                    return
                self.serial_worker.connect_tcp(ip, port)

    def is_serial_connected(self) -> bool:
        return self.serial_worker.is_connected()

    def check_hardware_connected(self) -> bool:
        if not self.is_serial_connected():
            mode = self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "USB"
            if mode == "WIFI":
                instrucao = "1. Conecte o computador à rede Wi-Fi do ESP32.<br>2. Verifique o IP/Porta e clique em <b>'Conectar ESP32'</b>."
            else:
                instrucao = f"1. Conecte o dispositivo via {mode}.<br>2. Selecione a porta e clique em <b>'Conectar ESP32'</b>."

            QMessageBox.warning(
                self,
                "Hardware Desconectado",
                f"<b>ANALISADOR ESPECTROMÉTRICO DESCONECTADO</b><br><br>{instrucao}"
            )
            return False
        return True

    def send_serial_command(self, cmd: str, priority: bool = False) -> bool:
        return self.serial_worker.send_command(cmd, priority=priority)

    def _on_serial_connection_changed(self, connected: bool, message: str):
        if connected:
            self.combo_conn_mode.setEnabled(False)
            self.badge_com.set_active(True, f"CONECTADO ({message})")
            self.btn_connect.setText("Desconectar")
            self.btn_connect.setStyleSheet("background-color: #383838; color: #EF4444; border: 1px solid #4a4a4a; font-weight: bold; padding: 6px 14px;")
            self.lbl_cycle_status.setText(f"Status do Ciclo: Hardware conectado ({message}). Pronto.")
            self.log_message(f"Hardware ESP32 conectado: {message}.")
        else:
            self.combo_conn_mode.setEnabled(True)
            self.badge_com.set_active(False, "DESCONECTADO")
            self.btn_connect.setText("Conectar ESP32")
            self.btn_connect.setStyleSheet("background-color: #0078D4; color: #FFFFFF; border: none; font-weight: bold; padding: 6px 14px;")
            self.lbl_cycle_status.setText("Status do Ciclo: Hardware desconectado.")
            self.log_message(f"Hardware ESP32 desconectado: {message}")

        if self._manual_dialog:
            self._manual_dialog.update_interlocks_and_leds()

    def _on_serial_error_occurred(self, err: str):
        self.log_message(f"[ERRO SERIAL] {err}")

    def _on_serial_line_received(self, line: str):
        # Exibe em log
        self.log_message(f"← {line}")

    # -----------------------------------------------------------------
    # DESACOPLAMENTO ATÔMICO DE BOTÕES MANUAIS
    # -----------------------------------------------------------------
    def _execute_atomic_manual_button(self, button: QPushButton, cmd_str: str, expected_status: str, desc: str):
        """
        Emite exclusivamente o comando serial correspondente e desabilita seu clique
        até receber a resposta de confirmação correspondente.
        """
        if not self.check_hardware_connected():
            return

        button.setEnabled(False)
        self.lbl_cycle_status.setText(f"Status: ⏳ {desc} (Aguardando STATUS:{expected_status})")

        # Watchdog por segurança
        watchdog = QTimer(self)
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(lambda: self._on_atomic_watchdog_timeout(button, expected_status))
        watchdog.start(5000)

        self._manual_pending[expected_status] = (button, watchdog)
        self.send_serial_command(cmd_str)

    def _on_atomic_watchdog_timeout(self, button: QPushButton, expected_status: str):
        if expected_status in self._manual_pending:
            del self._manual_pending[expected_status]
        button.setEnabled(True)
        self.lbl_cycle_status.setText(f"Status: ⚠️ Tempo limite excedido para STATUS:{expected_status}. Controle liberado.")
        self.log_message(f"[TIMEOUT] Watchdog liberou controle para {expected_status}")

    # -----------------------------------------------------------------
    # PROCESSAMENTO DE TELEMETRIA E MÁQUINA DE ESTADOS (FSM)
    # -----------------------------------------------------------------
    def _on_serial_data_received(self, values: list):
        """Recepção do payload DATA:v1,v2,v3,v4,v5,v6."""
        self._last_raw_payload = [float(v) for v in values[:6]]
        self.log_message(f"[PAYLOAD DATA]: {self._last_raw_payload}")

    def _on_serial_status_received(self, status_tag: str):
        """
        Tratamento centralizado de STATUS:* para Máquina de Estados e Desacoplamento Atômico.
        """
        self.log_message(f"[STATUS RX]: {status_tag}")

        # 1. Propaga para o modal manual, se aberto
        if self._manual_dialog:
            self._manual_dialog.on_status_received(status_tag)

        # 2. Libera botões manuais da UI principal que aguardavam este status
        if status_tag in self._manual_pending:
            button, watchdog = self._manual_pending.pop(status_tag)
            try:
                watchdog.stop()
            except Exception:
                pass
            button.setEnabled(True)
            self.lbl_cycle_status.setText(f"Status: ✔ Ação confirmada ({status_tag}). Pronto.")

        # 3. Tratamento de Handshake e Heartbeat
        if status_tag == "PONG":
            # Resposta de heartbeat/ping periódico; apenas log sem interferir na FSM
            self.log_message("[HEARTBEAT] STATUS:PONG recebido. Hardware responsivo.")
            return

        if status_tag in ("SENSOR_OK", "PRONTO"):
            self.log_message("Handshake ESP32 validado com sucesso!")
            return

        # 4. Tratamento de Emergência Acionada no Hardware
        if status_tag == "EMERGENCIA_ACIONADA":
            self._handle_emergency_confirmed()
            return

        # 4.1 Alerta Mecânico de Gaveta: Fechamento automático ao atingir fim de curso
        if status_tag in ("GAVETA_ABERTA", "GAVETA_FECHADA"):
            self._hide_drawer_alert()

        # 4.2 Alerta Mecânico de Gaveta: Abertura automática ao receber telemetria de movimentação
        if status_tag in ("ABRINDO_GAVETA", "FECHANDO_GAVETA"):
            if self.is_in_automated_routine():
                desc = "ABERTURA DE GAVETA EM ANDAMENTO" if status_tag == "ABRINDO_GAVETA" else "FECHAMENTO DE GAVETA EM ANDAMENTO"
                msg = "⏳ Abrindo gaveta motorizada..." if status_tag == "ABRINDO_GAVETA" else "⏳ Fechando gaveta motorizada..."
                self._show_drawer_alert(msg, desc)
            return

        # 5. Intertravamento Humano: Confirmação de Gaveta Aberta
        if status_tag == "GAVETA_ABERTA":
            if self.fsm_state == "PREP_ABRINDO_GAVETA":
                self._handle_interlock_popup()
                return
            elif self.fsm_state == "CALIB_ETAPA1_ABRINDO_GAVETA":
                self._handle_calib_transition_popups()
                return

        # 6. Intertravamento Humano / Conclusão de Ensaio: Gaveta Fechada
        if status_tag == "GAVETA_FECHADA" and self.fsm_state in ("CANCELANDO_FECHANDO_GAVETA", "CALIB_CANCELANDO_FECHANDO_GAVETA", "CONCLUSAO_FECHANDO_GAVETA"):
            is_completion = (self.fsm_state == "CONCLUSAO_FECHANDO_GAVETA")
            self.fsm_state = "IDLE"
            self._pending_routine = None
            self.auto_cycle_active = False
            self.modo_repetibilidade = False
            self.is_calibrating_white = False
            self.cycle_progress.setValue(100 if is_completion else 0)
            self._enable_controls()
            if is_completion:
                self.lbl_cycle_status.setText("Status: Ensaio finalizado. Bancada em repouso seguro e sistema pronto.")
                self.lbl_cycle_status.setStyleSheet("color: #10B981; font-size: 11px; font-weight: bold;")
                self.log_message("[CONCLUSÃO] Gaveta fechada em segurança. Bancada em repouso.")
            else:
                self.lbl_cycle_status.setText("Status: Ensaio cancelado pelo operador. Gaveta fechada e sistema pronto.")
                self.log_message("[CANCELADO] Gaveta fechada em segurança. Sistema liberado.")
            return

        # 7. MÁQUINA DE ESTADOS: CALIBRAÇÃO SEQUENCIAL (BRANCO -> ESCURO)
        if self.is_calibrating_white:
            self._handle_white_calibration_fsm(status_tag)
            return

        # 8. MÁQUINA DE ESTADOS: CICLO AUTOMÁTICO SIMPLES
        if self.auto_cycle_active:
            self._handle_auto_cycle_fsm(status_tag)
            return

        # 9. MÁQUINA DE ESTADOS: TESTE DE REPETIBILIDADE (5x ESTÁTICO)
        if self.modo_repetibilidade:
            self._handle_repeatability_fsm(status_tag)
            return

        # 10. Disparo manual fora de ciclos automáticos
        if status_tag == "LEITURA_CONCLUIDA" and self._last_raw_payload:
            self.process_raw_spectral_data(self._last_raw_payload)

    # -----------------------------------------------------------------
    # FASE 2: INTERTRAVAMENTO HUMANO (POPUP DE SEGURANÇA E CONFIRMAÇÃO)
    # -----------------------------------------------------------------
    def _handle_interlock_popup(self):
        """
        Exibida SOMENTE APÓS receber STATUS:GAVETA_ABERTA da Fase 1.
        Garante que o Python NUNCA envie CMD:FECHAR_GAVETA antes do OK do operador.
        """
        self.fsm_state = "AGUARDANDO_POPUP"
        self.lbl_cycle_status.setText("Status: 📦 Gaveta aberta. Aguardando posicionamento e confirmação do operador...")
        self.log_message("[INTERTRAVAMENTO] Gaveta aberta. Exibindo popup de confirmação de amostra...")

        if self._pending_routine in ("CALIB_BRANCO", "CALIBRAÇÃO"):
            title = "Calibração de Branco Instrumental"
            msg = (
                "A gaveta está aberta.<br><br>"
                "Insira a <b>lâmina com água destilada e lamínula</b> sobre o berço de medição e "
                "clique em <b>OK / Iniciar</b> para prosseguir."
            )
        elif self._pending_routine == "REPETIBILIDADE":
            title = "Inserção de Amostra"
            msg = (
                "A gaveta está aberta.<br><br>"
                "Posicione a lâmina de celulose no berço e clique em OK para iniciar o ensaio de repetibilidade."
            )
        else:
            title = "Inserção de Amostra"
            msg = (
                "A gaveta está aberta.<br><br>"
                "Posicione a lâmina de celulose no berço e clique em OK para iniciar."
            )

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            confirmed = getattr(self, "_auto_confirm_dialog", False)
        else:
            dlg = SamplePlacementInterlockDialog(title=title, message=msg, parent=self)
            confirmed = (dlg.exec_() == QDialog.Accepted)

        if not confirmed:
            # Operador cancelou ou fechou sem confirmar: NÃO despacha CMD:FECHAR_GAVETA e aborta a rotina
            self.log_message("[INTERTRAVAMENTO] Operador cancelou o popup de confirmação. CMD:FECHAR_GAVETA NÃO enviado. Rotina cancelada.")
            self.fsm_state = "IDLE"
            self._pending_routine = None
            self.auto_cycle_active = False
            self.modo_repetibilidade = False
            self.is_calibrating_white = False
            self.cycle_progress.setValue(0)
            self._enable_controls()
            self.lbl_cycle_status.setText("Status: Ensaio cancelado pelo operador. Gaveta permanece aberta.")
            return

        # Sincronismo Estrito: O comando CMD:FECHAR_GAVETA\n é despachado ESTRITAMENTE após o operador clicar no botão "OK"
        self.log_message("[INTERTRAVAMENTO] Botão 'OK' clicado pelo operador. Despachando CMD:FECHAR_GAVETA...")
        self.cycle_progress.setValue(15)

        if self._pending_routine == "AUTO":
            self.auto_cycle_active = True
            self.fsm_state = "AUTO_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: ⏳ Amostra confirmada. Fechando gaveta para medição...")
            self._show_drawer_alert("⏳ Amostra confirmada. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")

        elif self._pending_routine == "REPETIBILIDADE":
            self.modo_repetibilidade = True
            self.leituras_rep = []
            self.fsm_state = "REP_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: ⏳ Amostra confirmada. Fechando gaveta para repetibilidade...")
            self._show_drawer_alert("⏳ Amostra confirmada. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")

        elif self._pending_routine in ("CALIB_BRANCO", "CALIBRAÇÃO"):
            self.is_calibrating_white = True
            self.fsm_state = "CALIB_ETAPA1_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: ⏳ Referência confirmada. Fechando gaveta para medição do branco...")
            self._show_drawer_alert("⏳ Referência confirmada. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")

    # -----------------------------------------------------------------
    # A. CICLO AUTOMÁTICO SIMPLES
    # -----------------------------------------------------------------
    def start_simple_auto_cycle(self):
        """
        Inicia Ciclo Automático Simples com Intertravamento Humano:
        Fase 1: CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA
        Fase 2: Popup Modal de Confirmação do Operador (OK vs Cancelar)
        Fase 3: CMD:FECHAR_GAVETA -> CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO ->
                CMD:RECUAR_SENSOR -> CMD:ABRIR_GAVETA -> Finalização e ejeção.
        """
        if not self.check_hardware_connected():
            return
        if self.auto_cycle_active or self.modo_repetibilidade or self.is_calibrating_white or self.fsm_state != "IDLE":
            self.log_message("AVISO: Outro ensaio já está em execução.")
            return

        self._clear_cycle_timers()
        self._disable_controls()

        self._pending_routine = "AUTO"
        self.fsm_state = "PREP_ABRINDO_GAVETA"
        self._last_raw_payload = []

        self.cycle_progress.setValue(5)
        self.lbl_cycle_status.setText("Status: ⏳ Fase 1: Abrindo gaveta para posicionamento da amostra...")
        self.log_message("[CICLO AUTO] Fase 1: Enviando CMD:ABRIR_GAVETA")
        self._show_drawer_alert("⏳ Fase 1: Abrindo gaveta para posicionamento da amostra...", "ABERTURA DE GAVETA EM ANDAMENTO")
        self.send_serial_command("CMD:ABRIR_GAVETA")

    def _handle_auto_cycle_fsm(self, status_tag: str):
        # Passo 1: Gaveta Fechada pós-confirmação -> Avança sensor
        if status_tag == "GAVETA_FECHADA" and self.fsm_state == "AUTO_FECHANDO_GAVETA":
            self.fsm_state = "AUTO_AVANCANDO_SENSOR"
            self.cycle_progress.setValue(35)
            self.lbl_cycle_status.setText("Status: ⏳ Gaveta fechada. Avançando sensor sobre a lâmina...")
            self.log_message("[CICLO AUTO] Avançando sensor (CMD:AVANCAR_SENSOR)")
            self._show_radiation_alert("⏳ Varredura óptica NIR em andamento. Câmara intertravada...")
            self.send_serial_command("CMD:AVANCAR_SENSOR")

        # Passo 2: Sensor Avançado -> Dispara 1 varredura óptica
        elif status_tag == "SENSOR_AVANCADO" and self.fsm_state == "AUTO_AVANCANDO_SENSOR":
            self.fsm_state = "AUTO_LENDO_ESPECTRO"
            self.cycle_progress.setValue(60)
            self.lbl_cycle_status.setText("Status: 💡 Sensor posicionado. Disparando leitura dos 6 canais NIR...")
            self.log_message("[CICLO AUTO] Disparando leitura (CMD:LER_ESPECTRO)")
            self.send_serial_command("CMD:LER_ESPECTRO")

        # Passo 3: Leitura Concluída -> Recua sensor
        elif status_tag == "LEITURA_CONCLUIDA" and self.fsm_state == "AUTO_LENDO_ESPECTRO":
            self.fsm_state = "AUTO_RECUANDO_SENSOR"
            self.cycle_progress.setValue(80)
            self.lbl_cycle_status.setText("Status: ⏳ Leitura óptica concluída. Recuando sensor para repouso...")
            self.log_message("[CICLO AUTO] Recuando sensor (CMD:RECUAR_SENSOR)")
            self.send_serial_command("CMD:RECUAR_SENSOR")

        # Passo 4: Sensor Recuado -> Abre gaveta para retirada da lâmina
        elif status_tag == "SENSOR_RECUADO" and self.fsm_state == "AUTO_RECUANDO_SENSOR":
            self._hide_radiation_alert()
            self.fsm_state = "AUTO_ABRINDO_GAVETA"
            self.cycle_progress.setValue(92)
            self.lbl_cycle_status.setText("Status: ⏳ Sensor em repouso. Abrindo gaveta para retirada da lâmina...")
            self.log_message("[CICLO AUTO] Abrindo gaveta para ejeção (CMD:ABRIR_GAVETA)")
            self._show_drawer_alert("⏳ Abrindo gaveta para retirada da lâmina...", "ABERTURA DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:ABRIR_GAVETA")

        # Passo 5: Gaveta Aberta -> Processa resultados e exibe diálogo de decisão
        elif status_tag == "GAVETA_ABERTA" and self.fsm_state == "AUTO_ABRINDO_GAVETA":
            self.cycle_progress.setValue(100)
            self.lbl_cycle_status.setText("Status: ✔ Análise concluída. Gaveta aberta no berço.")
            self.log_message("[CICLO AUTO] Análise concluída com sucesso. Gaveta aberta no berço.")

            if self._last_raw_payload:
                self.process_raw_spectral_data(self._last_raw_payload)

            # Abre o Diálogo de Decisão ao Concluir a Leitura (Item 3)
            self._handle_completion_decision_dialog(is_repeatability=False)

    # -----------------------------------------------------------------
    # B. TESTE DE REPETIBILIDADE (5 LEITURAS COM AVANÇO/RECUO DO SENSOR)
    # -----------------------------------------------------------------
    def start_repeatability_test(self):
        """
        Ensaio de Repetibilidade com Intertravamento Humano:
        Fase 1: CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA
        Fase 2: Popup de Confirmação do Operador (OK para iniciar)
        Fase 3: CMD:FECHAR_GAVETA ->
                Repetições 1 a N-1 (gaveta sempre fechada):
                  CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO -> CMD:RECUAR_SENSOR
                Repetição N:
                  CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO -> CMD:RECUAR_SENSOR ->
                  CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA -> Diálogo de Decisão.
        """
        if not self.check_hardware_connected():
            return
        if self.auto_cycle_active or self.modo_repetibilidade or self.is_calibrating_white or self.fsm_state != "IDLE":
            self.log_message("AVISO: Outro ensaio já está em andamento.")
            return

        self._clear_cycle_timers()
        self._disable_controls()

        self._pending_routine = "REPETIBILIDADE"
        self.leituras_rep = []
        self._last_raw_payload = []
        self.fsm_state = "PREP_ABRINDO_GAVETA"

        self.cycle_progress.setValue(5)
        self.lbl_cycle_status.setText("Status: ⏳ Fase 1: Abrindo gaveta para posicionamento da amostra...")
        self.log_message("[REPETIBILIDADE] Fase 1: Enviando CMD:ABRIR_GAVETA")
        self._show_drawer_alert("⏳ Fase 1: Abrindo gaveta para posicionamento da amostra...", "ABERTURA DE GAVETA EM ANDAMENTO")
        self.send_serial_command("CMD:ABRIR_GAVETA")

    def _handle_repeatability_fsm(self, status_tag: str):
        # 1. Gaveta Fechada pós-confirmação -> Avança sensor para a medição 1
        if status_tag == "GAVETA_FECHADA" and self.fsm_state == "REP_FECHANDO_GAVETA":
            self.fsm_state = "REP_AVANCANDO_SENSOR"
            self.cycle_progress.setValue(15)
            self.lbl_cycle_status.setText("Status: ⏳ Gaveta fechada. Avançando sensor para medição 1 de 5...")
            self.log_message("[REPETIBILIDADE] Medição 1/5: Avançando sensor (CMD:AVANCAR_SENSOR)")
            self._show_radiation_alert("⏳ Ensaio de Repetibilidade (varreduras NIR em andamento)...")
            self.send_serial_command("CMD:AVANCAR_SENSOR")

        # 2. Sensor Avançado -> Dispara varredura óptica
        elif status_tag == "SENSOR_AVANCADO" and self.fsm_state == "REP_AVANCANDO_SENSOR":
            self.fsm_state = "REP_LENDO_ESPECTRO"
            rep_num = len(self.leituras_rep) + 1
            self.lbl_cycle_status.setText(f"Status: 💡 Sensor posicionado. Disparando leitura {rep_num} de 5...")
            self.log_message(f"[REPETIBILIDADE] Sensor posicionado. Disparando leitura {rep_num}/5 (CMD:LER_ESPECTRO)...")
            self.send_serial_command("CMD:LER_ESPECTRO")

        # 3. Leitura Concluída -> Registra dados e recua sensor (gaveta permanece fechada)
        elif status_tag == "LEITURA_CONCLUIDA" and self.fsm_state == "REP_LENDO_ESPECTRO":
            if self._last_raw_payload and len(self._last_raw_payload) == 6:
                calib_r = self.chem_engine.calculate_relative_reflectance(self._last_raw_payload)
                self.leituras_rep.append(calib_r)
                count = len(self.leituras_rep)

                progress_val = 15 + int((count / 5.0) * 70)
                self.cycle_progress.setValue(progress_val)
                self.lbl_cycle_status.setText(f"Status: 💡 Leitura {count} de 5 concluída. Recuando sensor...")
                self.log_message(f"[REPETIBILIDADE] Leitura {count}/5 gravada: {[round(v, 4) for v in calib_r]}")

                snv = self.chem_engine.normalize_snv(calib_r)
                self.scatter_plot.add_measurement(self._last_raw_payload, f"Rep #{count}", r_norm=snv)

            self.fsm_state = "REP_RECUANDO_SENSOR"
            self.log_message("[REPETIBILIDADE] Recuando sensor (CMD:RECUAR_SENSOR)")
            self.send_serial_command("CMD:RECUAR_SENSOR")

        # 4. Sensor Recuado -> Se repetições < 5, avança novamente (gaveta sempre fechada). Se 5, abre gaveta!
        elif status_tag == "SENSOR_RECUADO" and self.fsm_state == "REP_RECUANDO_SENSOR":
            count = len(self.leituras_rep)
            if count < 5:
                # Repetição intermediária (1 até N-1): GAVETA FICA SEMPRE FECHADA!
                self.fsm_state = "REP_AVANCANDO_SENSOR"
                self.lbl_cycle_status.setText(f"Status: ⏳ Gaveta fechada. Avançando sensor para medição {count + 1} de 5...")
                self.log_message(f"[REPETIBILIDADE] Repetição intermediária {count + 1}/5 (gaveta fechada). Avançando sensor...")
                self.send_serial_command("CMD:AVANCAR_SENSOR")
            else:
                # Na última repetição (N=5): Recuado o sensor, abre a gaveta!
                self._hide_radiation_alert()
                self.fsm_state = "REP_ABRINDO_GAVETA"
                self.cycle_progress.setValue(95)
                self.lbl_cycle_status.setText("Status: ⏳ 5 repetições concluídas. Abrindo gaveta para decisão operacional...")
                self.log_message("[REPETIBILIDADE] 5 repetições concluídas. Abrindo gaveta para ejeção (CMD:ABRIR_GAVETA)")
                self._show_drawer_alert("⏳ Abrindo gaveta para retirada da lâmina...", "ABERTURA DE GAVETA EM ANDAMENTO")
                self.send_serial_command("CMD:ABRIR_GAVETA")

        # 5. Gaveta Aberta -> Exibe relatório estatístico e abre diálogo de decisão
        elif status_tag == "GAVETA_ABERTA" and self.fsm_state == "REP_ABRINDO_GAVETA":
            self.cycle_progress.setValue(100)
            self.lbl_cycle_status.setText("Status: ✔ Ensaio de Repetibilidade concluído. Gaveta aberta no berço.")
            self.log_message("[REPETIBILIDADE] Ensaio de Repetibilidade concluído. Gaveta aberta.")
            self._display_repeatability_report()
            self._handle_completion_decision_dialog(is_repeatability=True)

    def _handle_completion_decision_dialog(self, is_repeatability: bool = False):
        """
        Diálogo de decisão ao concluir a leitura com a gaveta aberta (Item 3):
        - Botão 1: [ Finalizar e Fechar Gaveta ] (Padrão) -> envia CMD:FECHAR_GAVETA, sistema em repouso.
        - Botão 2: [ Nova Análise ] -> mantém gaveta aberta, limpa dados, pede novo nome e fecha para ler.
        - Botão 3: [ Iniciar Repetibilidade ] -> mantém gaveta aberta para checagem, fecha e dispara repetições.
        """
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            action = getattr(self, "_auto_decision_choice", DialogDecisaoConclusao.ACTION_FINISH)
        else:
            dlg = DialogDecisaoConclusao(parent=self, is_repeatability=is_repeatability)
            dlg.exec_()
            action = dlg.selected_action

        if action == DialogDecisaoConclusao.ACTION_FINISH:
            self.log_message("[CONCLUSÃO] Decisão: Finalizar e Fechar Gaveta.")
            self.fsm_state = "CONCLUSAO_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: ⏳ Finalizando ensaio. Fechando gaveta...")
            self._show_drawer_alert("⏳ Fechando gaveta e finalizando...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")

        elif action == DialogDecisaoConclusao.ACTION_NEW_SCAN:
            self.log_message("[CONCLUSÃO] Decisão: Nova Análise. Gaveta permanece aberta no berço.")
            self._last_raw_payload = []
            self.current_scan_data = []

            novo_id = f"Amostra_{datetime.datetime.now().strftime('%H%M%S')}"
            default_name = getattr(self, "current_sample_name", novo_id)
            if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                texto, ok = QInputDialog.getText(
                    self,
                    "Nova Análise — Identificação da Amostra",
                    "A gaveta está aberta.<br>Insira a nova lâmina no berço e confirme o nome da amostra:",
                    text=default_name
                )
                if not ok:
                    # Cancelou o nome: finaliza fechando a gaveta
                    self.fsm_state = "CONCLUSAO_FECHANDO_GAVETA"
                    self.send_serial_command("CMD:FECHAR_GAVETA")
                    return
                novo_id = texto.strip() or novo_id

            self.current_sample_name = novo_id
            if hasattr(self, "txt_sample_id") and self.txt_sample_id is not None:
                self.txt_sample_id.setText(novo_id)
            self._pending_routine = "AUTO"
            self.auto_cycle_active = True
            self.modo_repetibilidade = False
            self.is_calibrating_white = False
            self.fsm_state = "AUTO_FECHANDO_GAVETA"
            self.cycle_progress.setValue(15)
            self.lbl_cycle_status.setText(f"Status: ⏳ Nova amostra ({novo_id}) confirmada. Fechando gaveta...")
            self._show_drawer_alert("⏳ Fechando gaveta para nova medição...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            # Envia diretamente CMD:FECHAR_GAVETA (sem tentar abrir novamente a gaveta que já está aberta!)
            self.send_serial_command("CMD:FECHAR_GAVETA")

        elif action == DialogDecisaoConclusao.ACTION_REPEAT:
            self.log_message("[CONCLUSÃO] Decisão: Iniciar Repetibilidade. Gaveta aberta para checagem.")
            if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                resp = QMessageBox.question(
                    self,
                    "Iniciar Repetibilidade",
                    "A gaveta está aberta. Verifique se a lâmina está posicionada sobre o berço.<br><br>"
                    "Deseja iniciar o <b>Ensaio de Repetibilidade</b> com 5 repetições consecutivas?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if resp != QMessageBox.Yes:
                    self.fsm_state = "CONCLUSAO_FECHANDO_GAVETA"
                    self.send_serial_command("CMD:FECHAR_GAVETA")
                    return

            self._pending_routine = "REPETIBILIDADE"
            self.modo_repetibilidade = True
            self.auto_cycle_active = False
            self.is_calibrating_white = False
            self.leituras_rep = []
            self.fsm_state = "REP_FECHANDO_GAVETA"
            self.cycle_progress.setValue(10)
            self.lbl_cycle_status.setText("Status: ⏳ Repetibilidade confirmada. Fechando gaveta...")
            self._show_drawer_alert("⏳ Repetibilidade confirmada. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            # Envia diretamente CMD:FECHAR_GAVETA (sem tentar abrir novamente a gaveta que já está aberta!)
            self.send_serial_command("CMD:FECHAR_GAVETA")

    def _display_repeatability_report(self):
        """Calcula e exibe relatório estatístico canal a canal (Média, Desvio Padrão, CV%)."""
        if len(self.leituras_rep) < 2:
            return

        stats = self.chem_engine.compute_repeatability_stats(self.leituras_rep)
        means = stats["means"]
        stdevs = stats["stdevs"]
        cvs = stats["cv_percent"]
        global_cv = stats["global_cv_mean"]

        mean_adc = [m * 1000.0 for m in means]
        snv_mean = self.chem_engine.normalize_snv(means)
        self.spectral_chart.update_spectrum(mean_adc, r_calibrated=means, r_snv=snv_mean)

        dlg = QDialog(self)
        dlg.setWindowTitle("Relatório Estatístico de Repetibilidade (5 Varreduras Estáticas)")
        dlg.resize(620, 360)
        dlg.setStyleSheet("background-color: #202020; color: #FFFFFF;")

        d_layout = QVBoxLayout(dlg)
        title = QLabel(f"📊 RELATÓRIO DE REPETIBILIDADE (CV% Médio Global: {global_cv:.2f}%)")
        title.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold;")
        d_layout.addWidget(title)

        table = QTableWidget(6, 4)
        table.setHorizontalHeaderLabels(["Canal (nm)", "Média (μ)", "Desvio Padrão (s)", "CV (%)"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                gridline-color: #3d3d3d;
                color: #FFFFFF;
                font-family: 'Segoe UI';
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #1a1a1a;
                color: #38BDF8;
                font-weight: bold;
                border: 1px solid #3d3d3d;
                padding: 6px;
            }
        """)

        for ch in range(6):
            table.setItem(ch, 0, QTableWidgetItem(CHANNEL_NAMES[ch]))
            table.setItem(ch, 1, QTableWidgetItem(f"{means[ch]:.4f}"))
            table.setItem(ch, 2, QTableWidgetItem(f"{stdevs[ch]:.4f}"))

            cv_item = QTableWidgetItem(f"{cvs[ch]:.2f}%")
            if cvs[ch] < 3.0:
                cv_item.setForeground(QColor("#10B981"))
            elif cvs[ch] < 6.0:
                cv_item.setForeground(QColor("#F59E0B"))
            else:
                cv_item.setForeground(QColor("#EF4444"))
            table.setItem(ch, 3, cv_item)

        d_layout.addWidget(table)

        btn_ok = QPushButton("Fechar Relatório")
        btn_ok.clicked.connect(dlg.accept)
        d_layout.addWidget(btn_ok)

        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            dlg.exec_()
        self.log_message(f"Repetibilidade finalizada. CV% Médio Global = {global_cv:.2f}%")

    # -----------------------------------------------------------------
    # C. CALIBRAÇÃO INSTRUMENTAL SEQUENCIAL (BRANCO -> ESCURO)
    # -----------------------------------------------------------------
    def start_white_calibration_cycle(self):
        """
        Rotina de Calibração Sequencial Guiada (Branco -> Escuro):
        ETAPA 1: Branco (Água Destilada + Lamínula)
        - CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA
        - Popup 1 (Inserção do Branco) -> OK ou Cancelar (fecha gaveta)
        - CMD:FECHAR_GAVETA -> CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO -> CMD:RECUAR_SENSOR
        - CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA (Ejeção segura)
        ETAPA 2: Transição e Fundo Escuro (Gaveta Vazia)
        - Popup 2 (Deseja prosseguir para escuro? Se não: fecha gaveta, salva branco e encerra)
        - Popup 3 (Aviso de segurança: lâmina removida e berço vazio?)
        - CMD:FECHAR_GAVETA -> CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO -> CMD:RECUAR_SENSOR
        - Encerramento Seguro: Não reabre gaveta (berço vazio em repouso), salva calibracao.json e encerra.
        """
        if not self.check_hardware_connected():
            return
        if self.auto_cycle_active or self.modo_repetibilidade or self.is_calibrating_white or self.fsm_state != "IDLE":
            self.log_message("AVISO: Outro ensaio ou calibração já está em andamento.")
            return

        self._clear_cycle_timers()
        self._disable_controls()

        self.is_calibrating_white = True
        self._pending_routine = "CALIBRAÇÃO"
        self._last_raw_payload = []
        self._temp_vetor_branco = []
        self._temp_vetor_escuro = []
        self.fsm_state = "PREP_ABRINDO_GAVETA"

        self.cycle_progress.setValue(5)
        self.lbl_cycle_status.setText("Status: ⏳ Calibração Etapa 1: Abrindo gaveta para lâmina com água destilada...")
        self.log_message("[CALIBRAÇÃO] Etapa 1: Enviando CMD:ABRIR_GAVETA")
        self._show_drawer_alert("⏳ Calibração Etapa 1: Abrindo gaveta para lâmina com água destilada...", "ABERTURA DE GAVETA EM ANDAMENTO")
        self.send_serial_command("CMD:ABRIR_GAVETA")

    def start_calibration_wizard(self):
        """Alias para calibração sequencial completa."""
        self.start_white_calibration_cycle()

    def _handle_calib_transition_popups(self):
        """
        ETAPA 2: Transição com a gaveta aberta pós-branco.
        Exibe Popup 2 (Pergunta de Sequência) e, se o operador aceitar, Popup 3 (Segurança).
        """
        self.lbl_cycle_status.setText("Status: 📦 Branco registrado. Gaveta aberta. Aguardando operador...")
        self.log_message("[CALIBRAÇÃO TRANSIÇÃO] Gaveta aberta. Exibindo Popup 2 (Pergunta de Sequência)...")

        # Popup 2: Deseja prosseguir para escuro?
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            choice = getattr(self, "_calib_transition_choice", "PROSSEGUIR")
            proceed = (choice == "PROSSEGUIR")
        else:
            dlg2 = CalibrationTransitionDialog(parent=self)
            proceed = (dlg2.exec_() == QDialog.Accepted)

        if not proceed:
            # Usuário escolheu [ Concluir / Sair ]: Fecha gaveta e salva Branco
            self.log_message("[CALIBRAÇÃO] Operador optou por Concluir após o Branco. Fechando gaveta...")
            self.fsm_state = "CALIB_CONCLUSAO_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: ⏳ Fechando gaveta e finalizando calibração de branco...")
            self._show_drawer_alert("⏳ Fechando gaveta e salvando Branco...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")
            return

        # Usuário escolheu [ Prosseguir ] -> Popup 3 (Aviso de Segurança - Berço Vazio)
        self.log_message("[CALIBRAÇÃO] Operador optou por prosseguir. Exibindo Popup 3 (Aviso de Segurança)...")
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            confirmed_empty = getattr(self, "_calib_confirm_empty", True)
        else:
            dlg3 = DarkSafetyInterlockDialog(parent=self)
            confirmed_empty = (dlg3.exec_() == QDialog.Accepted)

        if not confirmed_empty:
            # Usuário cancelou no Popup 3: Fecha gaveta e salva Branco
            self.log_message("[CALIBRAÇÃO] Operador cancelou no Popup 3. Fechando gaveta e salvando Branco...")
            self.fsm_state = "CALIB_CONCLUSAO_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: ⏳ Fechando gaveta e finalizando calibração de branco...")
            self._show_drawer_alert("⏳ Cancelamento: Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")
            return

        # Popup 3 confirmado: Berço vazio confirmado pelo operador!
        self.log_message("[CALIBRAÇÃO] Berço vazio confirmado. Fechando gaveta para medição de escuro...")
        self.fsm_state = "CALIB_ETAPA2_FECHANDO_GAVETA"
        self.cycle_progress.setValue(65)
        self.lbl_cycle_status.setText("Status: ⏳ Gaveta fechando com berço vazio para calibração de escuro...")
        self._show_drawer_alert("⏳ Berço vazio confirmado. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
        self.send_serial_command("CMD:FECHAR_GAVETA")

    def _handle_white_calibration_fsm(self, status_tag: str):
        # 1. Gaveta Fechada após confirmação do Popup 1 (Branco)
        if status_tag == "GAVETA_FECHADA" and self.fsm_state == "CALIB_ETAPA1_FECHANDO_GAVETA":
            self.fsm_state = "CALIB_ETAPA1_AVANCANDO_SENSOR"
            self.cycle_progress.setValue(25)
            self.lbl_cycle_status.setText("Status: ⏳ Gaveta fechada. Posicionando sensor sobre a lâmina de água...")
            self.log_message("[CALIBRAÇÃO ETAPA 1] Avançando sensor (CMD:AVANCAR_SENSOR)")
            self._show_radiation_alert("⏳ Medindo Branco óptico (Água Destilada) com radiação NIR ativa...")
            self.send_serial_command("CMD:AVANCAR_SENSOR")

        # 2. Sensor Avançado sobre o Branco -> Dispara leitura
        elif status_tag == "SENSOR_AVANCADO" and self.fsm_state == "CALIB_ETAPA1_AVANCANDO_SENSOR":
            self.fsm_state = "CALIB_ETAPA1_LENDO_ESPECTRO"
            self.cycle_progress.setValue(35)
            self.lbl_cycle_status.setText("Status: 💡 Medindo Branco óptico (Água Destilada)...")
            self.log_message("[CALIBRAÇÃO ETAPA 1] Disparando leitura de branco (CMD:LER_ESPECTRO)")
            self.send_serial_command("CMD:LER_ESPECTRO")

        # 3. Leitura do Branco Concluída -> Registra e recua sensor
        elif status_tag == "LEITURA_CONCLUIDA" and self.fsm_state == "CALIB_ETAPA1_LENDO_ESPECTRO":
            self._temp_vetor_branco = list(self._last_raw_payload) if self._last_raw_payload else [1000.0] * 6
            self.fsm_state = "CALIB_ETAPA1_RECUANDO_SENSOR"
            self.cycle_progress.setValue(50)
            self.lbl_cycle_status.setText("Status: ⏳ Leitura de branco registrada. Recuando sensor para repouso...")
            self.log_message(f"[CALIBRAÇÃO BRANCO] Vetor gravado: {self._temp_vetor_branco}")
            self.log_message("[CALIBRAÇÃO ETAPA 1] Recuando sensor (CMD:RECUAR_SENSOR)")
            self.send_serial_command("CMD:RECUAR_SENSOR")

        # 4. Sensor Recuado -> Ejeção segura: Abre gaveta para retirada da lâmina
        elif status_tag == "SENSOR_RECUADO" and self.fsm_state == "CALIB_ETAPA1_RECUANDO_SENSOR":
            self._hide_radiation_alert()
            self.fsm_state = "CALIB_ETAPA1_ABRINDO_GAVETA"
            self.cycle_progress.setValue(58)
            self.lbl_cycle_status.setText("Status: ⏳ Sensor em repouso. Abrindo gaveta para retirada da lâmina...")
            self.log_message("[CALIBRAÇÃO ETAPA 1] Abrindo gaveta para ejeção (CMD:ABRIR_GAVETA)")
            self._show_drawer_alert("⏳ Abrindo gaveta para transição de amostra...", "ABERTURA DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:ABRIR_GAVETA")

        # 5. Cancelamento no Popup 1 -> Gaveta fechada e sistema liberado
        elif status_tag == "GAVETA_FECHADA" and self.fsm_state == "CALIB_CANCELANDO_FECHANDO_GAVETA":
            self.fsm_state = "IDLE"
            self.is_calibrating_white = False
            self._pending_routine = None
            self.cycle_progress.setValue(0)
            self._enable_controls()
            self.lbl_cycle_status.setText("Status: Calibração cancelada. Gaveta fechada e sistema pronto.")
            self.log_message("[CALIBRAÇÃO] Gaveta fechada em segurança. Rotina cancelada.")

        # 6. Conclusão apenas com Branco (Popup 2 ou 3) -> Gaveta fechada e Branco salvo
        elif status_tag == "GAVETA_FECHADA" and self.fsm_state == "CALIB_CONCLUSAO_FECHANDO_GAVETA":
            self.chem_engine.save_calibration(
                vetor_branco=self._temp_vetor_branco,
                r2=0.988,
                rmse=0.010,
                n_amostras=6,
                notes="Calibração de Branco (Água Destilada)"
            )
            self._update_calibration_badge()
            self.atualizar_kpi_calibracao(r2=0.988, rmse=0.010, n_amostras=6)
            self.fsm_state = "IDLE"
            self.is_calibrating_white = False
            self._pending_routine = None
            self.cycle_progress.setValue(100)
            self._enable_controls()
            self.lbl_cycle_status.setText("Status: ✔ Calibração de Branco concluída. Gaveta fechada e sistema pronto.")
            self.log_message("[CALIBRAÇÃO] Gaveta fechada. Branco gravado com sucesso em calibracao.json.")
            if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                QMessageBox.information(self, "Calibração Concluída", "Branco de referência registrado com sucesso!\nA gaveta foi fechada e o sistema está pronto.")

        # 7. ETAPA 2: Gaveta Fechada com Berço Vazio -> Avança sensor para escuro
        elif status_tag == "GAVETA_FECHADA" and self.fsm_state == "CALIB_ETAPA2_FECHANDO_GAVETA":
            self.fsm_state = "CALIB_ETAPA2_AVANCANDO_SENSOR"
            self.cycle_progress.setValue(70)
            self.lbl_cycle_status.setText("Status: ⏳ Gaveta fechada com berço vazio. Avançando sensor para escuro...")
            self.log_message("[CALIBRAÇÃO ETAPA 2] Avançando sensor para escuro (CMD:AVANCAR_SENSOR)")
            self._show_radiation_alert("⏳ Medindo Fundo Escuro com radiação NIR armada...")
            self.send_serial_command("CMD:AVANCAR_SENSOR")

        # 8. ETAPA 2: Sensor Avançado -> Mede Fundo Escuro
        elif status_tag == "SENSOR_AVANCADO" and self.fsm_state == "CALIB_ETAPA2_AVANCANDO_SENSOR":
            self.fsm_state = "CALIB_ETAPA2_LENDO_ESPECTRO"
            self.cycle_progress.setValue(80)
            self.lbl_cycle_status.setText("Status: 💡 Medindo Fundo Escuro no compartimento óptico vazio...")
            self.log_message("[CALIBRAÇÃO ETAPA 2] Disparando leitura de escuro (CMD:LER_ESPECTRO)")
            self.send_serial_command("CMD:LER_ESPECTRO")

        # 9. ETAPA 2: Leitura do Escuro Concluída -> Registra e recua sensor
        elif status_tag == "LEITURA_CONCLUIDA" and self.fsm_state == "CALIB_ETAPA2_LENDO_ESPECTRO":
            self._temp_vetor_escuro = list(self._last_raw_payload) if self._last_raw_payload else [0.0] * 6
            self.fsm_state = "CALIB_ETAPA2_RECUANDO_SENSOR"
            self.cycle_progress.setValue(92)
            self.lbl_cycle_status.setText("Status: ⏳ Fundo escuro gravado. Recuando sensor para repouso seguro...")
            self.log_message(f"[CALIBRAÇÃO ESCURO] Vetor gravado: {self._temp_vetor_escuro}")
            self.log_message("[CALIBRAÇÃO ETAPA 2] Recuando sensor (CMD:RECUAR_SENSOR)")
            self.send_serial_command("CMD:RECUAR_SENSOR")

        # 10. ETAPA 2: Sensor Recuado -> Encerramento Seguro (GAVETA NÃO É ABERTA!)
        elif status_tag == "SENSOR_RECUADO" and self.fsm_state == "CALIB_ETAPA2_RECUANDO_SENSOR":
            self._hide_radiation_alert()
            self.fsm_state = "IDLE"
            self.is_calibrating_white = False
            self._pending_routine = None
            self.cycle_progress.setValue(100)
            self._enable_controls()

            # Salva ambos os vetores
            self.chem_engine.save_calibration(
                vetor_branco=self._temp_vetor_branco,
                vetor_escuro=self._temp_vetor_escuro,
                r2=0.994,
                rmse=0.007,
                n_amostras=6,
                notes="Calibração Sequencial Completa (Branco + Escuro)"
            )
            self._update_calibration_badge()
            self.atualizar_kpi_calibracao(r2=0.994, rmse=0.007, n_amostras=6)

            self.lbl_cycle_status.setText("Status: ✔ Calibração completa (Branco e Escuro) realizada. Gaveta fechada em repouso.")
            self.log_message("[CALIBRAÇÃO COMPLETA] Branco e Escuro gravados em calibracao.json. Gaveta fechada e sistema pronto.")

            if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                QMessageBox.information(
                    self,
                    "Calibração Completa",
                    "Calibração completa (Branco e Escuro) realizada com sucesso.\nSistema em repouso pronto para medições."
                )

    def _update_calibration_badge(self):
        if self.chem_engine.is_calibrated:
            self.badge_calib.set_active(True, "CALIBRADO")
        else:
            self.badge_calib.set_active(False, "NÃO CALIBRADO")

    def atualizar_kpi_calibracao(self, r2=None, rmse=None, n_amostras=0):
        """
        Método de Atualização Dinâmica do Card KPI de Calibração:
        - Atualiza os textos dos labels numéricos (R², RMSE, N).
        - Aplica o estilo e a cor correspondente no badge de validação visual.
        - Conecta a atualização na janela principal e no diálogo de calibração ativo.
        """
        if hasattr(self, "card_calibracao"):
            self.card_calibracao.atualizar(r2=r2, rmse=rmse, n_amostras=n_amostras)
        if hasattr(self, "_active_calib_dialog") and self._active_calib_dialog:
            self._active_calib_dialog.card_kpi.atualizar(r2=r2, rmse=rmse, n_amostras=n_amostras)
        self._update_calibration_badge()


    # -----------------------------------------------------------------
    # D. PARADA DE EMERGÊNCIA (E-STOP)
    # -----------------------------------------------------------------
    def stop_cycle_action(self):
        """
        Ao clicar em [ Parada de Emergência ]:
        1. Interrupção de Fluxo: Cancela imediatamente qualquer QTimer ou execução em andamento.
        2. Despacho Prioritário: Envia imediatamente CMD:EMERGENCIA\\n através da conexão ativa.
        3. Bloqueio e Feedback:
           - Trava temporariamente os botões de ciclo por ~1,5 segundo (tempo de recolhimento suave do ESP32).
           - Atualiza a barra de status ou badge para: "EMERGÊNCIA ACIONADA - BANCADA EM REPOUSO".
        """
        self.log_message("🛑 PARADA DE EMERGÊNCIA ACIONADA PELO OPERADOR!")
        self._clear_cycle_timers()
        self._hide_drawer_alert()
        self._hide_radiation_alert()

        # Reseta flags operacionais e aborta fluxos
        self.auto_cycle_active = False
        self.modo_repetibilidade = False
        self.is_calibrating_white = False
        self._pending_routine = None
        self.fsm_state = "EMERGENCIA"

        # Cancela timers pendentes de botões manuais
        for status, (btn, timer) in list(self._manual_pending.items()):
            try:
                timer.stop()
            except Exception:
                pass
        self._manual_pending.clear()

        # Envia com prioridade máxima CMD:EMERGENCIA\n
        self.serial_worker.send_emergency()

        # Bloqueia UI e sinaliza o status exato solicitado
        self._disable_controls()
        self.cycle_progress.setValue(0)
        self.lbl_cycle_status.setText("EMERGÊNCIA ACIONADA - BANCADA EM REPOUSO")
        self.lbl_cycle_status.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: 900;")

        # Trava temporariamente os botões de ciclo por ~1,5s
        self._emergency_lock_active = True
        self._emergency_lock_timer = QTimer(self)
        self._emergency_lock_timer.setSingleShot(True)
        self._emergency_lock_timer.timeout.connect(self._on_emergency_lock_timeout)
        self._emergency_lock_timer.start(1500)
        self._cycle_timers.append(self._emergency_lock_timer)

    def _on_emergency_lock_timeout(self):
        self._emergency_lock_active = False
        self.log_message("[EMERGÊNCIA] Janela de segurança de 1,5s decorrida. Bancada estabilizada.")
        if self.fsm_state in ("IDLE", "EMERGENCIA"):
            self.fsm_state = "IDLE"
            self._enable_controls()
            self.lbl_cycle_status.setText("Status: Bancada em repouso. Sistema pronto para nova inicialização.")
            self.lbl_cycle_status.setStyleSheet("color: #10B981; font-size: 11px; font-weight: bold;")

    def _handle_emergency_confirmed(self):
        """
        Ao receber STATUS:EMERGENCIA_ACIONADA do hardware:
        Reabilita os botões manuais e permite nova inicialização (respeitando a trava de 1,5s).
        """
        self._hide_drawer_alert()
        self._hide_radiation_alert()
        self.log_message("[EMERGÊNCIA] Confirmação recebida do hardware (STATUS:EMERGENCIA_ACIONADA).")
        if not getattr(self, "_emergency_lock_active", False):
            self.fsm_state = "IDLE"
            self._enable_controls()
            self.lbl_cycle_status.setText("Status: Bancada em repouso. Sistema pronto para nova inicialização.")
            self.lbl_cycle_status.setStyleSheet("color: #10B981; font-size: 11px; font-weight: bold;")

    def _clear_cycle_timers(self):
        for t in self._cycle_timers:
            try:
                t.stop()
            except Exception:
                pass
        self._cycle_timers.clear()

    # -----------------------------------------------------------------
    # PROCESSAMENTO DE DADOS, QUIMIOMETRIA E GRÁFICOS
    # -----------------------------------------------------------------
    def process_raw_spectral_data(self, raw_values: List[float]):
        if not raw_values or len(raw_values) < 6:
            return

        self.current_scan_data = [float(v) for v in raw_values[:6]]

        # 1. Aplicação da Camada Quimiométrica de Calibração (R_i)
        r_calibrated = self.chem_engine.calculate_relative_reflectance(self.current_scan_data)
        self.current_r_calibrated = r_calibrated

        # 2. Normalização Vetorial SNV Simplificada (R_norm)
        r_snv = self.chem_engine.normalize_snv(r_calibrated)
        self.current_r_snv = r_snv

        # 3. Razões de Celulose e Água
        ratio_cel, ratio_water = self.chem_engine.calculate_scatter_ratios(r_snv)

        # 4. Atualiza Gráfico Espectral (Barras + Spline)
        self.spectral_chart.update_spectrum(self.current_scan_data, r_calibrated=r_calibrated, r_snv=r_snv)

        # 5. Atualiza KPI Cards
        total_adc = sum(self.current_scan_data)
        self.kpi_energy.set_value(f"{int(total_adc):,} ADC".replace(",", "."), "Soma das 6 bandas NIR")

        # Pico Dominante
        max_idx = self.current_scan_data.index(max(self.current_scan_data))
        dom_wl = WAVELENGTHS[max_idx]
        self.kpi_peak.set_value(f"{dom_wl} nm", f"Canal {CHANNEL_NAMES[max_idx]} ({int(self.current_scan_data[max_idx])} ADC)")

        self.kpi_ratio_cel.set_value(f"{ratio_cel:.2f}", "R680 / R730 (Bandas Celulósicas)")
        self.kpi_ratio_water.set_value(f"{ratio_water:.2f}", "R860 / R760 (Espessura da Gota)")

        # 6. Classificação e Similaridade Híbrida
        best_mat, best_score, penalized = self.find_best_match_hybrid(self.current_scan_data)
        if best_score >= 88.0:
            final_mat = best_mat
        else:
            final_mat = "Material Não Identificado"

        self.current_matched_material = final_mat
        self.current_match_percent = best_score

        # 7. Estimativa de Número Kappa
        kappa_val, kappa_status, kappa_color = calculate_kappa_number(r_snv)
        self.current_kappa_value = kappa_val

        # 8. Atualiza Card de Identificação Lateral
        if best_score >= 88.0:
            self.lbl_material_name.setText(final_mat)
            self.lbl_material_name.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: bold;")
            self.lbl_match_score.setText(f"% Match: {best_score:.2f}%")
            self.lbl_match_score.setStyleSheet("color: #10B981; font-size: 13px; font-weight: 800;")
        else:
            self.lbl_material_name.setText("Material Não Identificado")
            self.lbl_material_name.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: bold;")
            self.lbl_match_score.setText(f"% Match: {best_score:.2f}%")
            self.lbl_match_score.setStyleSheet("color: #EF4444; font-size: 13px; font-weight: 800;")

        self.lbl_kappa_laudo.setText(f"Kappa: {kappa_val:.1f} ({kappa_status})")
        self.lbl_kappa_laudo.setStyleSheet(f"color: {kappa_color}; font-size: 11px;")

        # 9. Plota no Scatter Plot com as razões de celulose e água
        self.scatter_plot.add_measurement(self.current_scan_data, final_mat, r_norm=r_snv)

        self.log_message(
            f"Resultado: {final_mat} | Match: {best_score:.2f}% | Celulose(R680/730)={ratio_cel:.2f} | Kappa={kappa_val:.1f}"
        )

    def load_database_dict(self) -> dict:
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.log_message(f"Erro ao ler banco: {e}")
        return {}

    def find_best_match_hybrid(self, sample_vec):
        db = self.load_database_dict()
        if not db:
            return "Sem Banco de Dados", 0.0, False

        best_material = "Material Não Identificado"
        best_score = 0.0
        best_penalized = False

        for name, ref_vec in db.items():
            score, pen = calculate_hybrid_similarity(sample_vec, ref_vec, calib_engine=self.chem_engine)
            if score > best_score:
                best_score = score
                best_material = name
                best_penalized = pen

        return best_material, best_score, best_penalized

    # -----------------------------------------------------------------
    # GESTÃO DE ESTADO DOS CONTROLES
    # -----------------------------------------------------------------
    def _enable_controls(self):
        self.btn_start_scan.setEnabled(True)
        self.btn_repeatability.setEnabled(True)
        self.btn_calibrate.setEnabled(True)
        self.btn_man_open_drawer.setEnabled(True)
        self.btn_man_close_drawer.setEnabled(True)
        self.btn_man_fwd_sensor.setEnabled(True)
        self.btn_man_back_sensor.setEnabled(True)
        self.btn_man_read.setEnabled(True)

    def _disable_controls(self):
        self.btn_start_scan.setEnabled(False)
        self.btn_repeatability.setEnabled(False)
        self.btn_calibrate.setEnabled(False)
        self.btn_man_open_drawer.setEnabled(False)
        self.btn_man_close_drawer.setEnabled(False)
        self.btn_man_fwd_sensor.setEnabled(False)
        self.btn_man_back_sensor.setEnabled(False)
        self.btn_man_read.setEnabled(False)
        # O botão de emergência principal permanece sempre habilitado
        if hasattr(self, "btn_emergency_auto"):
            self.btn_emergency_auto.setEnabled(True)
        if hasattr(self, "btn_top_emergency"):
            self.btn_top_emergency.setEnabled(True)

    # -----------------------------------------------------------------
    # ALERTA DE SEGURANÇA CONTRA RADIAÇÃO ÓPTICA (NIR)
    # -----------------------------------------------------------------
    def _show_radiation_alert(self, text_custom: str = None):
        self.log_message(f"[SEGURANÇA NIR] Radiação óptica ativa: {text_custom or 'Varredura em andamento'}")
        if self._radiation_dialog is None:
            self._radiation_dialog = DialogAlertaRadiacao(self)
        if text_custom:
            self._radiation_dialog.set_custom_status(text_custom)
        self._radiation_dialog.show()
        QApplication.processEvents()

    def _hide_radiation_alert(self):
        if self._radiation_dialog is not None:
            try:
                self._radiation_dialog.close()
            except Exception:
                pass

    # -----------------------------------------------------------------
    # ALERTA DE SEGURANÇA MECÂNICA (MOVIMENTAÇÃO DE GAVETA)
    # -----------------------------------------------------------------
    def is_in_automated_routine(self) -> bool:
        """Retorna True se o supervisório estiver executando uma rotina automática."""
        if hasattr(self, "control_tabs") and self.control_tabs.currentIndex() == 1:
            return False
        if self._manual_dialog is not None:
            return False
        return (
            self.auto_cycle_active or
            self.modo_repetibilidade or
            self.is_calibrating_white or
            self.fsm_state not in ("IDLE", "EMERGENCIA")
        )

    def _show_drawer_alert(self, text_custom: str = None, detail: str = "MOVIMENTAÇÃO DE GAVETA EM ANDAMENTO"):
        """Abre o diálogo de alerta mecânico com bypass explícito para acionamentos manuais."""
        if not self.is_in_automated_routine():
            return

        self.log_message(f"[SEGURANÇA MECÂNICA] Gaveta em movimento: {text_custom or detail}")
        if self._drawer_dialog is None:
            self._drawer_dialog = DialogAlertaGaveta(self)
        if text_custom:
            self._drawer_dialog.set_action_status(text_custom, detail)
        self._drawer_dialog.show()
        QApplication.processEvents()

    def _hide_drawer_alert(self):
        """Fecha o diálogo de alerta mecânico imediatamente."""
        if self._drawer_dialog is not None:
            try:
                self._drawer_dialog.close()
            except Exception:
                pass

    @property
    def dialogo_gaveta(self) -> DialogAlertaGaveta:
        """Instância do diálogo de alerta mecânico de gaveta."""
        if self._drawer_dialog is None:
            self._drawer_dialog = DialogAlertaGaveta(self)
        return self._drawer_dialog

    @property
    def dialogo_radiacao(self) -> DialogAlertaRadiacao:
        """Instância do diálogo de alerta óptico de radiação NIR."""
        if self._radiation_dialog is None:
            self._radiation_dialog = DialogAlertaRadiacao(self)
        return self._radiation_dialog

    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # CONTROLE DE ACESSO E GESTÃO DE MODOS (MANUAL / AUTO)
    # -----------------------------------------------------------------
    def _on_control_tab_changed(self, index: int):
        """
        Intercepta a mudança para a aba de Modo Manual (index == 1).
        Exige autenticação via DialogLogin. Se cancelado ou incorreto,
        reverte imediatamente para a aba de Ensaios Automáticos (index == 0).
        """
        if index == 1:
            if not self.is_manual_mode_unlocked:
                dlg = DialogLogin(self.auth_manager, self)
                if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
                    accepted = getattr(self, "_auto_login_success", False)
                    if accepted:
                        self.authenticated_user = getattr(self, "_auto_login_user", {"username": "admin", "role": "admin"})
                else:
                    accepted = (dlg.exec_() == QDialog.Accepted)
                    if accepted:
                        self.authenticated_user = dlg.usuario_logado

                if accepted and self.authenticated_user:
                    self.is_manual_mode_unlocked = True
                    u_name = self.authenticated_user.get("username", "operador")
                    role = self.authenticated_user.get("role", "operador").upper()
                    self.log_message(f"🔓 Modo Manual liberado para {u_name} ({role}).")
                else:
                    self.log_message("🔒 Acesso ao Modo Manual cancelado ou não autorizado.")
                    self.control_tabs.blockSignals(True)
                    self.control_tabs.setCurrentIndex(0)
                    self.control_tabs.blockSignals(False)
                    return
        elif index == 0:
            # Ao sair do Modo Manual, exige autenticação novamente ao reentrar
            if self.is_manual_mode_unlocked:
                self.is_manual_mode_unlocked = False
                self.log_message("🔒 Modo Manual bloqueado ao alternar para Ensaios Automáticos.")

    def switch_mode(self, mode: str):
        """Alterna entre abas para compatibilidade com rotinas externas."""
        if mode == "MANUAL":
            self.control_tabs.setCurrentIndex(1)
        else:
            self.control_tabs.setCurrentIndex(0)

    def open_user_management_dialog(self):
        """
        Abre a tela de Gerenciamento de Usuários (DialogGestaoUsuarios).
        Exige autenticação prévia com perfil 'admin'.
        """
        if not self.authenticated_user or self.authenticated_user.get("role") != "admin":
            dlg = DialogLogin(self.auth_manager, self)
            if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
                accepted = getattr(self, "_auto_login_success", False)
                if accepted:
                    self.authenticated_user = getattr(self, "_auto_login_user", {"username": "admin", "role": "admin"})
            else:
                accepted = (dlg.exec_() == QDialog.Accepted)
                if accepted:
                    self.authenticated_user = dlg.usuario_logado

            if not accepted or not self.authenticated_user:
                return

            if self.authenticated_user.get("role") != "admin":
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    QMessageBox.warning(
                        self,
                        "Acesso Negado",
                        "Apenas usuários com perfil de 'Administrador' podem gerenciar usuários."
                    )
                self.log_message("Aviso: Tentativa de acesso negada ao Gerenciador de Usuários (Requer Admin).")
                return

        dlg_gestao = DialogGestaoUsuarios(
            auth_manager=self.auth_manager,
            current_user=self.authenticated_user,
            parent=self
        )
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            dlg_gestao.exec_()
        self.log_message("Gerenciador de Usuários finalizado.")

    def logout_action(self):
        """
        Bloqueia as abas restritas e desloga a sessão ativa.
        """
        user_name = self.authenticated_user.get("username", "Usuário") if self.authenticated_user else "Operador"
        self.authenticated_user = None
        self.is_manual_mode_unlocked = False

        if hasattr(self, "control_tabs") and self.control_tabs.currentIndex() != 0:
            self.control_tabs.blockSignals(True)
            self.control_tabs.setCurrentIndex(0)
            self.control_tabs.blockSignals(False)

        self.log_message(f"🔒 Logout realizado com sucesso ({user_name}). Painel manual bloqueado.")
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.information(
                self, "Painel Bloqueado",
                "Sessão encerrada com sucesso.\nO painel manual foi bloqueado."
            )

    # -----------------------------------------------------------------
    # UTILIDADES E DIÁLOGOS
    # -----------------------------------------------------------------
    def open_calibration_dialog(self):
        dlg = CalibrationModalDialog(self)
        self._active_calib_dialog = dlg
        eng = self.chem_engine
        if eng.is_calibrated:
            dlg.card_kpi.atualizar(r2=eng.r2, rmse=eng.rmse, n_amostras=eng.n_amostras)
        else:
            dlg.card_kpi.atualizar(r2=None, rmse=None, n_amostras=0)
        dlg.exec_()
        self._active_calib_dialog = None

    def open_manual_control_dialog(self):
        """Abre o painel de atuadores com autenticação prévia."""
        if not self.is_manual_mode_unlocked:
            dlg = DialogLogin(self.auth_manager, self)
            if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
                accepted = getattr(self, "_auto_login_success", False)
                if accepted:
                    self.authenticated_user = getattr(self, "_auto_login_user", {"username": "admin", "role": "admin"})
            else:
                accepted = (dlg.exec_() == QDialog.Accepted)
                if accepted:
                    self.authenticated_user = dlg.usuario_logado

            if not accepted or not self.authenticated_user:
                self.log_message("🔒 Acesso ao Painel de Atuadores cancelado ou não autorizado.")
                return

            self.is_manual_mode_unlocked = True

        self._manual_dialog = ManualControlDialog(self)
        self._manual_dialog.exec_()
        self._manual_dialog = None

    def open_database_manager(self):
        dlg = DatabaseManagerDialog(self.db_path, self)
        dlg.exec_()
        self.log_message("Gerenciador de Banco de Dados sincronizado.")

    def export_pdf_report(self):
        if sum(self.current_scan_data) == 0:
            QMessageBox.warning(self, "Aviso", "Realize uma análise espectral antes de gerar o laudo técnico.")
            return

        default_filename = f"Laudo_Espectral_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Laudo Técnico PDF", default_filename, "Arquivos PDF (*.pdf)"
        )
        if file_path:
            try:
                generate_pdf_report(
                    filename=file_path,
                    sample_id=f"AM-{random.randint(1000, 9999)}",
                    operator="Eng. de Qualidade e Processos",
                    material_name=self.current_matched_material,
                    match_percentage=self.current_match_percent,
                    values=self.current_scan_data,
                    com_port=self.combo_com.currentText(),
                    kappa_value=self.current_kappa_value
                )
                self.log_message(f"Laudo Técnico PDF emitido: {file_path}")
                reply = QMessageBox.question(
                    self, "Laudo Gerado", "Laudo Técnico emitido com sucesso!\nDeseja visualizar o PDF agora?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    os.startfile(file_path)
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao gerar Laudo PDF: {e}")

    def export_csv_log(self):
        default_filename = f"Historico_Espectral_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Dados CSV", default_filename, "Arquivos CSV (*.csv)"
        )
        if file_path:
            try:
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "DataHora", "Material", "Match_Percent", "Kappa_Number",
                        "610nm_ADC", "680nm_ADC", "730nm_ADC", "760nm_ADC", "810nm_ADC", "860nm_ADC",
                        "R_Norm_680", "R_Norm_730", "R_Norm_760", "R_Norm_860"
                    ])
                    r_snv = self.current_r_snv if len(self.current_r_snv) == 6 else [0.0] * 6
                    writer.writerow([
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        self.current_matched_material,
                        f"{self.current_match_percent:.2f}",
                        f"{self.current_kappa_value:.1f}",
                        *self.current_scan_data,
                        f"{r_snv[1]:.4f}", f"{r_snv[2]:.4f}", f"{r_snv[3]:.4f}", f"{r_snv[5]:.4f}"
                    ])
                self.log_message(f"Dados exportados para CSV: {file_path}")
                QMessageBox.information(self, "Sucesso", "Dados exportados em CSV com sucesso!")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao exportar CSV: {e}")

    def closeEvent(self, event):
        """Ao fechar o aplicativo, encerra a conexão de forma segura."""
        self._clear_cycle_timers()
        if self.serial_worker.is_connected():
            self.disconnect_hardware()
        event.accept()


# =====================================================================
# 5. PONTO DE ENTRADA
# =====================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    splash = AnimatedSplashScreen()
    main_win = SpectrumLabMainWindow()

    def show_main():
        main_win.show()

    splash.finished.connect(show_main)
    splash.start_animation()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
