"""
Módulo de Geração de Laudos Técnicos em PDF (ReportLab + Matplotlib Headless)
SPECTRUM-LAB PRO (Fluent Edition)

Método Espectrométrico Experimental VIS-NIR | Modelo Parametrizado de Bancada
Arquitetura Headless Pura: Utiliza matplotlib.figure.Figure e FigureCanvasAgg
diretamente, sem qualquer uso do módulo pyplot, eliminando conflitos de thread,
interferências no backend Qt5Agg e fechamento inesperado da janela principal.
"""

import os
import sys
import tempfile
import datetime
from typing import Optional, List, Union

# Configuração mandatória de backend headless não interativo antes de qualquer chamada
import matplotlib
matplotlib.use('Agg', force=True)
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

try:
    from version import __version__, __build__
except ImportError:
    __version__ = "4.9.14"
    __build__ = "1250"


class WatermarkCanvas(canvas.Canvas):
    """
    Canvas customizado do ReportLab para renderização de marca d'água
    diagonal translúcida em todas as páginas do laudo experimental.
    """
    def showPage(self):
        self.draw_watermark()
        super().showPage()

    def draw_watermark(self):
        self.saveState()
        # Fonte grande Helvetica-Bold calibrada (~30-32 pt) para abranger a folha sem cortes nas bordas
        self.setFont("Helvetica-Bold", 30)
        # Vermelho suave com transparência atenuada (alpha 0.10)
        self.setFillColor(colors.Color(0.85, 0.20, 0.20, alpha=0.10))
        page_w, page_h = self._pagesize
        self.translate(page_w / 2.0, page_h / 2.0)
        self.rotate(45)
        self.drawCentredString(0, 0, "PROTÓTIPO EXPERIMENTAL — SEM VALIDADE OFICIAL")
        self.restoreState()


def generate_pdf_report(
    filename: str,
    sample_id: Optional[str] = "AM-0001",
    operator: Optional[str] = "Operador Técnico",
    kappa_value: Optional[float] = None,
    operational_mode: str = "seco",
    kappa_status: Optional[str] = None,
    values: Optional[List[float]] = None,
    raw_adc_values: Optional[List[float]] = None,
    ratio_celulose: Optional[float] = None,
    ratio_agua: Optional[float] = None,
    global_intensity_adc: Optional[Union[int, float]] = None,
    peak_wavelength_nm: Optional[Union[int, str]] = None,
    peak_intensity_adc: Optional[Union[int, float]] = None,
    com_port: str = "COM3",
    timestamp: Optional[str] = None,
    # Parâmetros legados ignorados para compatibilidade reversa estrita
    material_name: Optional[str] = None,
    match_percentage: Optional[float] = None,
) -> str:
    """
    Gera laudo técnico experimental em formato PDF diagramado pelo ReportLab.
    Totalmente quantitativo: sem menção a biblioteca, % match ou nomes comerciais.
    """
    clean_sample_id = str(sample_id) if sample_id is not None else "AM-0001"
    clean_operator = str(operator) if operator is not None else "Operador Técnico"
    clean_com_port = str(com_port) if com_port is not None else "COM3"

    clean_values = [float(v) if v is not None else 0.0 for v in (values or [0.0] * 6)]
    while len(clean_values) < 6:
        clean_values.append(0.0)
    clean_values = clean_values[:6]

    clean_raw_adc = None
    if raw_adc_values:
        clean_raw_adc = [float(v) if v is not None else 0.0 for v in raw_adc_values[:6]]
        while len(clean_raw_adc) < 6:
            clean_raw_adc.append(0.0)

    # Identificação do Método Operacional
    if operational_mode == "seco":
        mode_display = "Amostra Seca (Reflectância Difusa)"
    else:
        mode_display = "Suspensão Aquosa (Lâmina / Água)"

    # Número Kappa e Classificação Industrial Neutra
    k_val = float(kappa_value) if kappa_value is not None else 0.0
    if not kappa_status or kappa_status in ("Indeterminado", "Standby (Aguardando Leitura)"):
        if operational_mode == "seco":
            if k_val < 1.5:
                status_desc = "Polpa Branqueada de Alta Alvura"
                badge_hex = "#10B981"
                card_bg = "#ECFDF5"
            elif k_val < 12.0:
                status_desc = "Polpa Branqueada Padrão"
                badge_hex = "#34D399"
                card_bg = "#F0FDF4"
            elif k_val < 25.0:
                status_desc = "Polpa Semi-Branqueada"
                badge_hex = "#38BDF8"
                card_bg = "#F0F9FF"
            elif k_val < 35.0:
                status_desc = "Polpa Kraft Não Branqueada / Marrom"
                badge_hex = "#F59E0B"
                card_bg = "#FFFBEB"
            else:
                status_desc = "Massa Celulósica Crua"
                badge_hex = "#EF4444"
                card_bg = "#FEF2F2"
        else:
            if k_val < 12.0:
                status_desc = "Polpa Branqueada de Alta Alvura"
                badge_hex = "#10B981"
                card_bg = "#ECFDF5"
            elif k_val < 22.0:
                status_desc = "Polpa Semi-Branqueada"
                badge_hex = "#38BDF8"
                card_bg = "#F0F9FF"
            elif k_val < 32.0:
                status_desc = "Polpa Kraft Não Branqueada / Marrom"
                badge_hex = "#F59E0B"
                card_bg = "#FFFBEB"
            else:
                status_desc = "Massa Celulósica Crua"
                badge_hex = "#EF4444"
                card_bg = "#FEF2F2"
    else:
        status_desc = kappa_status
        if "Alta Alvura" in status_desc or k_val < 1.5:
            badge_hex = "#10B981"
            card_bg = "#ECFDF5"
        elif "Padrão" in status_desc or k_val < 12.0:
            badge_hex = "#34D399"
            card_bg = "#F0FDF4"
        elif "Semi" in status_desc or k_val < 25.0:
            badge_hex = "#38BDF8"
            card_bg = "#F0F9FF"
        elif "Kraft" in status_desc or k_val < 35.0:
            badge_hex = "#F59E0B"
            card_bg = "#FFFBEB"
        else:
            badge_hex = "#EF4444"
            card_bg = "#FEF2F2"

    badge_color = colors.HexColor(badge_hex)

    # Parâmetros Ópticos e Analíticos
    r_cel_str = f"{ratio_celulose:.2f}" if ratio_celulose is not None else "--"
    r_water_str = f"{ratio_agua:.2f}" if ratio_agua is not None else "--"
    
    if global_intensity_adc is not None:
        int_global_str = f"{int(global_intensity_adc):,} ADC".replace(",", ".")
    elif clean_raw_adc:
        int_global_str = f"{int(sum(clean_raw_adc)):,} ADC".replace(",", ".")
    else:
        int_global_str = "--"

    if peak_wavelength_nm is not None:
        pico_nm_str = f"{peak_wavelength_nm} nm"
        if peak_intensity_adc is not None:
            pico_nm_str += f" ({int(peak_intensity_adc):,} ADC)".replace(",", ".")
    elif clean_raw_adc:
        wls_std = [610, 680, 730, 760, 810, 860]
        max_idx = clean_raw_adc.index(max(clean_raw_adc))
        pico_nm_str = f"{wls_std[max_idx]} nm ({int(clean_raw_adc[max_idx]):,} ADC)".replace(",", ".")
    else:
        pico_nm_str = "--"

    # Configuração do Documento ReportLab
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=32,
        leftMargin=32,
        topMargin=28,
        bottomMargin=28
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        textColor=colors.HexColor('#0F172A'),
        alignment=0,
        spaceAfter=2
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#475569'),
        alignment=0,
        spaceAfter=8
    )

    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=5,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        textColor=colors.HexColor('#1E293B'),
        leading=11.5
    )

    story = []

    # --- Header Principal ---
    story.append(Paragraph(f"SPECTRUM-LAB PRO v{__version__} | Sistema Supervisório NIR/VIS", title_style))
    story.append(Paragraph(f"LAUDO TÉCNICO EXPERIMENTAL DE CARACTERIZAÇÃO ESPECTRAL E NÚMERO KAPPA (Build {__build__})", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#10B981'), spaceAfter=8))

    # --- Metadados e Rastreabilidade ---
    now_str = timestamp if timestamp else datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    meta_data = [
        [Paragraph("<b>Código da Amostra:</b>", body_style), Paragraph(clean_sample_id, body_style),
         Paragraph("<b>Data / Hora da Leitura:</b>", body_style), Paragraph(now_str, body_style)],
        [Paragraph("<b>Operador Responsável:</b>", body_style), Paragraph(clean_operator, body_style),
         Paragraph("<b>Interface / Porta COM:</b>", body_style), Paragraph(clean_com_port, body_style)],
        [Paragraph("<b>Hardware / Sensor:</b>", body_style), Paragraph("ESP32 + GY-AS7263 (NIR 6-CH)", body_style),
         Paragraph("<b>Método Operacional:</b>", body_style), Paragraph(f"<b>{mode_display}</b>", body_style)]
    ]

    t_meta = Table(meta_data, colWidths=[137, 137, 137, 137])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 6))

    # --- Bloco de Caracterização Quantitativa NIR (Número Kappa) ---
    story.append(Paragraph("Caracterização Quantitativa NIR (Número Kappa)", section_style))

    kappa_str = f"{k_val:.2f}"
    status_badge_html = f"<font size=11 color='{badge_hex}'><b>{status_desc.upper()}</b></font>"

    res_card_data = [
        [
            Paragraph("<font size=8.5 color='#FFFFFF'><b>NÚMERO KAPPA ESTIMADO (NIR)</b></font>", body_style),
            Paragraph("<font size=8.5 color='#FFFFFF'><b>CLASSIFICAÇÃO ESTIMADA DA POLPA</b></font>", body_style)
        ],
        [
            Paragraph(f"<font size=20 color='{badge_hex}'><b>Kappa {kappa_str}</b></font>", body_style),
            Paragraph(f"{status_badge_html}<br/><font size=7.5 color='#475569'>Método Espectrométrico Experimental VIS-NIR | Modelo Parametrizado de Bancada</font>", body_style)
        ]
    ]

    t_res = Table(res_card_data, colWidths=[240, 308])
    t_res.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor(card_bg)),
        ('BOX', (0, 0), (-1, -1), 1.5, badge_color),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t_res)
    story.append(Spacer(1, 6))

    # --- Tabela Completa de Parâmetros Analíticos e Ópticos ---
    param_data = [
        [
            Paragraph("<b>Intensidade Global (ADC Total):</b>", body_style), Paragraph(int_global_str, body_style),
            Paragraph("<b>Pico Espectral Dominante:</b>", body_style), Paragraph(pico_nm_str, body_style)
        ],
        [
            Paragraph("<b>Razão Celulose (R680/R730):</b>", body_style), Paragraph(r_cel_str, body_style),
            Paragraph("<b>Razão Matriz / Umidade (R860/R760):</b>", body_style), Paragraph(r_water_str, body_style)
        ],
        [
            Paragraph("<b>Método Analítico Ativo:</b>", body_style), Paragraph(mode_display, body_style),
            Paragraph("<b>Status de Calibração:</b>", body_style), Paragraph("<font color='#10B981'><b>Calibrado e Válido</b></font>", body_style)
        ]
    ]
    t_param = Table(param_data, colWidths=[150, 124, 150, 124])
    t_param.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t_param)
    story.append(Spacer(1, 6))

    # --- Gráfico Espectral GY-AS7263 (Barras Dinâmicas Proporcionais com Headless Puro) ---
    chart_unique_id = f"{os.getpid()}_{int(datetime.datetime.now().timestamp() * 1000)}"
    chart_image_path = os.path.join(tempfile.gettempdir(), f"temp_spectral_chart_{chart_unique_id}.png")
    wavelengths = ['610nm', '680nm', '730nm', '760nm', '810nm', '860nm']
    bar_colors = ['#EF4444', '#DC2626', '#C084FC', '#A855F7', '#9333EA', '#7E22CE']

    try:
        fig = Figure(figsize=(6.8, 2.05), dpi=150)
        canvas_fig = FigureCanvasAgg(fig)
        fig.patch.set_facecolor('#FFFFFF')

        ax = fig.add_subplot(111)
        ax.set_facecolor('#F8FAFC')

        # Vinculação direta às alturas das 6 barras
        heights = [float(v) for v in clean_values]
        max_height = max(heights) if heights else 100.0
        y_lim = max(max_height * 1.18, 10.0)

        bars = ax.bar(wavelengths, heights, color=bar_colors, edgecolor='#334155', linewidth=0.8, width=0.52)
        ax.set_ylabel("Refletância (%)", fontsize=8, fontweight='bold', color='#1E293B')
        ax.set_title(f"Perfil Espectral GY-AS7263 — {mode_display}", fontsize=8.5, fontweight='bold', color='#0F172A')
        ax.set_ylim(0, y_lim)
        ax.grid(axis='y', linestyle='--', alpha=0.5, color='#CBD5E1')
        ax.tick_params(colors='#1E293B', labelsize=8)

        for spine in ax.spines.values():
            spine.set_color('#CBD5E1')

        # Anotação dinâmica em cada barra
        for bar, h in zip(bars, heights):
            ax.annotate(
                f'{h:.1f}%',
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 2),
                textcoords="offset points",
                ha='center', va='bottom',
                fontsize=7.5, fontweight='bold', color='#0F172A'
            )

        fig.tight_layout()
        canvas_fig.print_figure(chart_image_path, format='png', dpi=150)

        story.append(Paragraph("Perfil Espectrométrico Medido", section_style))
        story.append(Image(chart_image_path, width=548, height=152))
        story.append(Spacer(1, 5))
    except Exception as chart_err:
        print(f"[PDF GENERATOR] Aviso: Falha ao gerar gráfico com FigureCanvasAgg: {chart_err}", flush=True)

    # --- Tabela Detalhada de Leituras Multicanais ---
    story.append(Paragraph("Tabela Detalhada de Leituras Multicanais", section_style))
    table_head = [
        Paragraph("<b>Canal (Comprimento de Onda)</b>", body_style),
        Paragraph("<b>Faixa Espectral</b>", body_style),
        Paragraph("<b>Sinal ADC Bruto</b>", body_style),
        Paragraph("<b>Refletância Calibrada</b>", body_style)
    ]

    color_names = [
        'Vermelho (610 nm)', 'Vermelho Profundo (680 nm)', 'NIR 730 (730 nm)',
        'NIR 760 (760 nm)', 'NIR 810 (810 nm)', 'NIR 860 (860 nm)'
    ]
    ranges = [
        'Visível (Banda Laranja/Vermelha)', 'Visível / Absorção Lignina', 'Banda Celulose / Lignina',
        'Banda Matriz Celulose', 'Absorção Polpa / Umidade', 'Banda Água / Espessura Gota'
    ]

    table_rows = [table_head]
    for i in range(6):
        adc_val_str = f"{int(clean_raw_adc[i]):,} ADC".replace(",", ".") if clean_raw_adc else "--"
        ref_val_str = f"{clean_values[i]:.2f}%"
        table_rows.append([
            Paragraph(color_names[i], body_style),
            Paragraph(ranges[i], body_style),
            Paragraph(adc_val_str, body_style),
            Paragraph(f"<b>{ref_val_str}</b>", body_style)
        ])

    t_val = Table(table_rows, colWidths=[142, 154, 122, 130])
    t_val.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 2.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    for i in range(4):
        t_val.setStyle(TableStyle([('TEXTCOLOR', (i, 0), (i, 0), colors.white)]))

    story.append(t_val)
    story.append(Spacer(1, 8))

    # --- Assinaturas Técnicas ---
    sig_data = [
        [Paragraph("__________________________________________", body_style),
         Paragraph("__________________________________________", body_style)],
        [Paragraph(f"<b>{clean_operator}</b><br/>Operador Técnico Responsável", body_style),
         Paragraph("<b>Pesquisa & Desenvolvimento / Qualidade</b><br/>Supervisão Analítica Experimental", body_style)]
    ]
    t_sig = Table(sig_data, colWidths=[274, 274])
    t_sig.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 1.5)
    ]))
    story.append(t_sig)
    story.append(Spacer(1, 6))

    # --- Rodapé Institucional e Legal ---
    footer_text = (
        f"<font size=7 color='#64748B'>"
        f"SPECTRUM-LAB PRO v{__version__} (Build {__build__}) — "
        f"Método Espectrométrico Experimental VIS-NIR | Modelo Parametrizado de Bancada. "
        f"Documento gerado eletronicamente em {now_str}."
        f"</font>"
    )
    story.append(Paragraph(footer_text, ParagraphStyle('FooterLegal', parent=body_style, alignment=1)))

    # Construção do Documento PDF
    try:
        doc.build(story, canvasmaker=WatermarkCanvas)
    finally:
        # Remoção segura da imagem temporária do disco
        if os.path.exists(chart_image_path):
            try:
                os.remove(chart_image_path)
            except Exception:
                pass

    return filename
