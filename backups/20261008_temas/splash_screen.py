from PyQt5.QtWidgets import QSplashScreen, QWidget, QVBoxLayout, QLabel, QProgressBar, QGraphicsOpacityEffect, QApplication
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QPixmap, QPainter, QLinearGradient, QBrush, QPen
try:
    from version import __version__, __build__
except ImportError:
    __version__ = "4.9.14"
    __build__ = "1250"

class AnimatedSplashScreen(QWidget):
    """
    Tela de Splash/Load Animada sem bordas, com Dark Slate #0F172A, Glassmorphism,
    QProgressBar animada de 0 a 100% em ~3s e transição suave de Fade-Out.
    """
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()

        # Frameless window, stays on top, translucent background setup
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(560, 320)
        self.center_on_screen()

        # Layout Setup
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)

        # Title / Brand Label
        title_label = QLabel("SPECTRUM-LAB")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            color: #F8FAFC;
            font-size: 28px;
            font-weight: bold;
            font-family: 'Segoe UI', Arial;
            letter-spacing: 3px;
        """)

        subtitle_label = QLabel(f"ANALISADOR ESPECTROMÉTRICO NIR/VIS • v{__version__} (Build {__build__})")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("""
            color: #06B6D4;
            font-size: 11px;
            font-weight: bold;
            font-family: 'Segoe UI', Arial;
            letter-spacing: 3px;
        """)

        desc_label = QLabel("Sistema Supervisório Industrial de Controle de Qualidade")
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setStyleSheet("""
            color: #94A3B8;
            font-size: 11px;
            font-family: 'Segoe UI', Arial;
        """)

        # Status Message Label
        self.status_label = QLabel("Inicializando subsistemas do Kernel Python...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            color: #38BDF8;
            font-size: 11px;
            font-family: 'Segoe UI', Arial;
            font-weight: bold;
        """)

        # Animated QProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
                text-align: center;
                color: #F8FAFC;
                font-size: 10px;
                font-weight: bold;
                font-family: 'Segoe UI';
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06B6D4, stop:1 #3B82F6);
                border-radius: 7px;
            }
        """)

        # Footer Version Text
        footer_label = QLabel("© 2026 SPECTRUM-LAB Industrial Technologies")
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setStyleSheet("color: #64748B; font-size: 9px; font-family: 'Segoe UI';")

        layout.addSpacing(10)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(desc_label)
        layout.addStretch()
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addSpacing(10)
        layout.addWidget(footer_label)

        # Opacity Effect for Fade-Out
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        # Step Timer (30ms interval * 100 steps = 3000ms = 3.0 seconds)
        self.progress_val = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance_progress)

    def center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def start_animation(self):
        self.show()
        self.timer.start(30)

    def advance_progress(self):
        self.progress_val += 1
        self.progress_bar.setValue(self.progress_val)

        # Update dynamic text at specific progress milestones
        if self.progress_val == 25:
            self.status_label.setText("Carregando banco de dados de assinaturas espectrais (JSON)...")
        elif self.progress_val == 55:
            self.status_label.setText("Verificando drivers e mapeando portas COM...")
        elif self.progress_val == 85:
            self.status_label.setText("Sistema Pronto! Abrindo interface do analisador...")

        if self.progress_val >= 100:
            self.timer.stop()
            self.start_fade_out()

    def start_fade_out(self):
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(500)  # 500ms fade-out
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.setEasingCurve(QEasingCurve.OutQuad)
        self.fade_anim.finished.connect(self.on_fade_finished)
        self.fade_anim.start()

    def on_fade_finished(self):
        self.hide()
        self.finished.emit()

    def paintEvent(self, event):
        # Custom Dark Slate #0F172A background with cyan rounded borders
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()

        # Dark Slate Background
        painter.setPen(QPen(QColor("#06B6D4"), 1.5))
        painter.setBrush(QBrush(QColor("#0F172A")))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 16, 16)
