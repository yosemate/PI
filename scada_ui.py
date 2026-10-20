"""Composição SCADA aprovada: controles à esquerda, bandas à direita, diagnóstico abaixo."""
from PyQt5.QtCore import Qt,QTimer,QSize,QRectF
from PyQt5.QtGui import QPainter,QColor,QPen,QPainterPath
from PyQt5.QtWidgets import (QWidget,QFrame,QLabel,QPushButton,QVBoxLayout,QHBoxLayout,QGridLayout,
                             QSplitter,QDialog,QSizePolicy)
from brand_assets import institutional_signature
from diagnostics import ControllerDiagnosticsCard
from responsive_layout import ScaledCanvasView

class SpectrumMark(QWidget):
    """Six spectral bands and a response curve, drawn crisply at any display scale."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setFixedSize(36,36)
        self.setAccessibleName("Ícone de espectro óptico")
    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#123F48'))
        painter.drawRoundedRect(QRectF(0,0,36,36),9,9)
        for i,(height,color) in enumerate(zip((8,14,21,17,12,7),
                ('#7BDDD4','#55CFC5','#37BDB2','#44AEC0','#789ED4','#A394D6'))):
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(6+i*4.2,29-height,2.6,height),1.3,1.3)
        curve=QPainterPath();curve.moveTo(5,21)
        curve.cubicTo(11,21,12,6,18,8)
        curve.cubicTo(23,9,24,19,31,20)
        painter.setPen(QPen(QColor('#DCF8F5'),1.4));painter.setBrush(Qt.NoBrush)
        painter.drawPath(curve)


def panel():
    box=QFrame();box.setObjectName('scadaPanel');return box

def label(text,size=12,muted=False):
    out=QLabel(text)
    out.setStyleSheet(f'font-size: {size}px;'+('color: #9CA3AF;' if muted else ''))
    return out

def open_login(window):
    if window.authenticated_user:
        window.logout_action();return
    from auth_dialogs import DialogLogin
    dialog=DialogLogin(window.auth_manager,window)
    if dialog.exec_()==QDialog.Accepted and dialog.usuario_logado:
        window.authenticated_user=dialog.usuario_logado
        window.is_manual_mode_unlocked=True
        window.current_operator_name=dialog.usuario_logado.get('username','Operador')
        window.log_message('Sessão autenticada: '+window.current_operator_name)

def build_dashboard(w):
    root=QWidget();root.setObjectName('centralWidget');root.main_win=w
    w.dashboard_content=root
    seeds=[w._create_topbar(),w._create_kpi_bar(),w._create_left_control_panel(),w._create_right_chart_panel(),w._create_footer()]
    # Mantém as páginas manuais existentes e suas conexões, sem recriar a lógica operacional.
    w._ui_seed_widgets=seeds
    for seed in seeds:seed.setParent(root);seed.hide()
    for seed in seeds:
        for widget in [seed,*seed.findChildren(QWidget)]:
            widget.setStyleSheet('');widget._theme_base_qss='';widget._theme_last_qss=''
    layout=QVBoxLayout(root);layout.setContentsMargins(20,16,20,16);layout.setSpacing(14)
    top=panel();w.topbar=top;row=QHBoxLayout(top);row.setContentsMargins(18,12,18,12);row.setSpacing(9)
    brand=QWidget();bl=QHBoxLayout(brand);bl.setContentsMargins(0,0,12,0);bl.setSpacing(9)
    bl.addWidget(SpectrumMark(brand));brand_name=label('Spectrum-LAB',20)
    brand_name.setStyleSheet('font-size: 20px; font-weight: 600;')
    bl.addWidget(brand_name);row.addWidget(brand)
    row.addWidget(w.combo_conn_mode)
    # Conserva os containers utilizados pela troca USB/Bluetooth/Wi-Fi.
    for item in w.widget_serial.findChildren(QLabel):item.hide()
    w.combo_com.setMaximumWidth(120);w.btn_refresh_ports.setText('↻')
    row.addWidget(w.widget_serial);row.addWidget(w.widget_wifi);row.addWidget(w.btn_connect)
    row.addWidget(w.badge_com);row.addStretch()
    manual=next(b for b in seeds[0].findChildren(QPushButton) if 'Atuadores' in b.text())
    manual.setText('Modo manual');manual.setMinimumWidth(115);row.addWidget(manual)
    w.btn_top_emergency.setText('Parada de emergência');w.btn_top_emergency.setObjectName('scadaEmergency')
    row.addWidget(w.btn_top_emergency)
    w.btn_login=QPushButton('Login');w.btn_login.clicked.connect(lambda:open_login(w));row.addWidget(w.btn_login)
    row.addWidget(w.btn_settings);layout.addWidget(top)
    w.kpi_bar=seeds[1]
    for card in (w.kpi_energy,w.kpi_peak,w.kpi_ratio_cel,w.kpi_ratio_water):
        card.setObjectName('scadaPanel');card.layout().setContentsMargins(18,12,18,12);card.layout().setSpacing(2)
        card.lbl_title.setStyleSheet('font-size: 11px; color: #9CA3AF;')
        card.lbl_value.setStyleSheet('font-size: 27px; color: #FFFFFF;')
        card.lbl_sub.setStyleSheet('font-size: 10px; color: #9CA3AF;')
    w.kpi_ratio_cel.lbl_title.setText('Razão R680 / R730');w.kpi_ratio_water.lbl_title.setText('Razão R860 / R760')
    layout.addWidget(w.kpi_bar)
    w.kpi_bar.show()
    w.dashboard_splitter=QSplitter(Qt.Horizontal);w.dashboard_splitter.setChildrenCollapsible(False);w.dashboard_splitter.setHandleWidth(16)
    left=QWidget();w.left_panel=left;ll=QVBoxLayout(left);ll.setContentsMargins(0,0,0,0);ll.setSpacing(12)
    controls=panel();cl=QVBoxLayout(controls);cl.setContentsMargins(16,14,16,14);cl.setSpacing(10)
    cl.addWidget(label('Método analítico',11,True));cl.addWidget(w.combo_op_mode)
    cl.addWidget(label('Ensaios automáticos',14))
    w.btn_start_scan.setText('Realizar leitura');w.btn_start_scan.setObjectName('scadaPrimary')
    w.btn_repeatability.setText('Leitura com repetibilidade · 5×')
    w.btn_calibrate.setText('Calibrar · Branco e escuro')
    for button in (w.btn_start_scan,w.btn_repeatability,w.btn_calibrate):cl.addWidget(button)
    ll.addWidget(controls)
    w.card_housing.setObjectName('scadaPanel')
    ll.addWidget(w.card_housing)
    w.card_calibracao.setObjectName('scadaPanel');w.card_calibracao.layout().setSpacing(5)
    ll.addWidget(w.card_calibracao)
    w.card_resultado.setObjectName('scadaResult')
    w.lbl_kappa_valor.setStyleSheet('font-size: 36px; color: #FFFFFF;')
    w.lbl_metodo_info.setWordWrap(True);w.lbl_kappa_classificacao.setWordWrap(True)
    ll.addWidget(w.card_resultado)
    buttons=QHBoxLayout();buttons.setSpacing(8)
    for button,text in ((w.btn_history,'Histórico'),(w.btn_pdf,'PDF'),(w.btn_csv,'CSV')):
        button.setText(text);button.setMinimumWidth(0);buttons.addWidget(button)
    ll.addLayout(buttons);ll.addStretch(1)
    right=panel();w.right_panel=right;rl=QVBoxLayout(right);rl.setContentsMargins(14,12,14,12)
    rl.addWidget(w.spectral_chart)
    w.dashboard_splitter.addWidget(left);w.dashboard_splitter.addWidget(right)
    w.dashboard_splitter.setStretchFactor(0,0);w.dashboard_splitter.setStretchFactor(1,1)
    w.dashboard_splitter.setSizes([420,1120]);layout.addWidget(w.dashboard_splitter,1)
    w.card_esp32=ControllerDiagnosticsCard(w)
    diagnostics=QWidget();dg=QGridLayout(diagnostics);dg.setContentsMargins(0,0,0,0);dg.setSpacing(16)
    dg.addWidget(w.card_esp32,0,0);dg.addWidget(w.card_telemetria,0,1);dg.setColumnStretch(0,4);dg.setColumnStretch(1,7)
    w.diagnostic_grid=dg;layout.addWidget(diagnostics)
    footer=panel();w.footer=footer;fl=QVBoxLayout(footer);fl.setContentsMargins(14,9,14,9);fl.setSpacing(5)
    fr=QHBoxLayout();w.lbl_cycle_status.setWordWrap(True);fr.addWidget(w.lbl_cycle_status,1)
    w.cycle_progress.setMaximumWidth(180);fr.addWidget(w.cycle_progress)
    w.btn_console=QPushButton('Console de telemetria');w.btn_console.setCheckable(True)
    w.btn_console.toggled.connect(w.txt_console.setVisible);fr.addWidget(w.btn_console)
    fr.addWidget(institutional_signature());fl.addLayout(fr);w.txt_console.hide();fl.addWidget(w.txt_console)
    layout.addWidget(footer)
    def style(p):
        return f'''QWidget#centralWidget {{background:{p['canvas']};color:{p['text']};font-family:Segoe UI;}}
QFrame#scadaPanel {{background:{p['surface']};border:1px solid {p['border']};border-radius:12px;}}
QFrame#scadaResult {{background:{p['soft']};border:0;border-radius:12px;}}
QPushButton {{background:{p['surface']};color:{p['text']};border:1px solid {p['border']};border-radius:7px;padding:8px 12px;font-size:11px;font-weight:400;}}
QPushButton:hover {{background:{p['soft']};}}
QPushButton:disabled {{color:{p['disabled']};background:{p['canvas']};}}
QPushButton#scadaPrimary {{background:{p['accent']};color:{'#FFFFFF' if w.theme_manager.theme=='light' else '#102D31'};border:0;}}
QPushButton#scadaPrimary:disabled {{background:{p['soft']};color:{p['disabled']};}}
QPushButton#scadaEmergency {{color:{p['danger']};border:1px solid {p['danger']};}}
QComboBox,QLineEdit {{background:{p['canvas']};color:{p['text']};border:1px solid {p['border']};border-radius:7px;padding:7px 10px;font-size:11px;}}
QComboBox QAbstractItemView {{background:{p['surface']};color:{p['text']};selection-background-color:{p['soft']};}}
QProgressBar {{background:{p['soft']};border:0;border-radius:4px;color:{p['muted']};font-size:10px;}}
QProgressBar::chunk {{background:{p['accent']};border-radius:4px;}}
QTextEdit {{background:{p['canvas']};color:{p['muted']};border:0;font-family:Consolas;font-size:11px;}}'''
    root._scada_style_factory=style
    w.canvas_view=ScaledCanvasView(root,QSize(1600,1000),w);w.setCentralWidget(w.canvas_view)
    w._scada_refresh_timer=QTimer(w)
    def refresh():
        w.card_esp32.refresh(w)
        w.btn_login.setText('Sair · '+w.authenticated_user.get('username','Operador') if w.authenticated_user else 'Login')
        card=w.card_telemetria
        card.refresh_freshness(busy=w.equipment.busy())
    w._scada_refresh_timer.timeout.connect(refresh);w._scada_refresh_timer.start(1000);refresh()
    w._responsive_ready=True
    # As páginas manuais e o badge são os únicos controles ocultos necessários.
    # Descarta os containers de construção depois de transferir seus filhos ativos.
    w.control_tabs.setParent(root);w.control_tabs.hide()
    w.badge_calib.setParent(root);w.badge_calib.hide()
    w.btn_emergency_auto=w.btn_top_emergency
    for seed in (seeds[0],seeds[2],seeds[3],seeds[4]):
        seed.setParent(None);seed.deleteLater()
    w._ui_seed_widgets=[w.kpi_bar]
    for widget in (w,root,*root.findChildren(QWidget)):w.theme_manager.apply_widget(widget)
    QTimer.singleShot(0,w._adapt_interface)
