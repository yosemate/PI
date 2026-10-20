"""
Gerador Profissional de Documentação Técnica em PDF
SPECTRUM-LAB PRO v4.9.14 (Build 1250)
"""

import os
import sys
import re
import json
import subprocess
import shutil
import urllib.request
import base64
import markdown

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(WORKSPACE_DIR, "DOCUMENTACAO_TECNICA_SUPERVISORIO.md")
LOCAL_PDF_PATH = os.path.join(WORKSPACE_DIR, "SPECTRUM-LAB_PRO_Documentacao_Tecnica.pdf")
DOWNLOADS_PDF_PATH = os.path.expanduser(r"~\Downloads\SPECTRUM-LAB_PRO_Documentacao_Tecnica.pdf")
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
KATEX_JS = os.path.join(WORKSPACE_DIR, "katex.min.js")
KATEX_CSS = os.path.join(WORKSPACE_DIR, "katex.min.css")

def get_mermaid_svg(index, graph_code):
    svg_filename = os.path.join(WORKSPACE_DIR, f"diagram_mermaid_{index}.svg")
    if os.path.exists(svg_filename) and os.path.getsize(svg_filename) > 1000:
        with open(svg_filename, "r", encoding="utf-8") as f:
            return f.read()

    print(f"Baixando diagrama Mermaid {index}...")
    graph_bytes = graph_code.encode("utf-8")
    b64_str = base64.b64encode(graph_bytes).decode("ascii")
    url = "https://mermaid.ink/svg/" + b64_str
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        svg_data = resp.read().decode("utf-8")
    with open(svg_filename, "w", encoding="utf-8") as f:
        f.write(svg_data)
    return svg_data

def batch_render_katex(math_items):
    """Renderiza todas as expressões KaTeX de uma única vez via Node.js."""
    if not math_items:
        return []

    node_script = f"""
    const katex = require({json.dumps(KATEX_JS)});
    const fs = require('fs');
    try {{
        const raw = fs.readFileSync(0, 'utf-8');
        const items = JSON.parse(raw);
        const results = items.map(entry => {{
            try {{
                return katex.renderToString(entry.expr, {{
                    throwOnError: false,
                    displayMode: entry.display
                }});
            }} catch (err) {{
                return '<code>' + entry.expr + '</code>';
            }}
        }});
        process.stdout.write(JSON.stringify(results));
    }} catch (e) {{
        console.error(e);
        process.exit(1);
    }}
    """

    payload = json.dumps(math_items, ensure_ascii=False)
    proc = subprocess.run(
        ["node", "-e", node_script],
        input=payload,
        capture_output=True,
        encoding="utf-8",
        cwd=WORKSPACE_DIR
    )

    if proc.returncode != 0:
        print("Erro ao processar KaTeX em lote:", proc.stderr)
        return [f"<code>{x['expr']}</code>" for x in math_items]

    return json.loads(proc.stdout)

def build_html_document():
    with open(MD_PATH, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 1. Extrair diagramas Mermaid
    mermaid_blocks = []
    def replace_mermaid(match):
        code = match.group(1).strip()
        idx = len(mermaid_blocks) + 1
        svg = get_mermaid_svg(idx, code)
        mermaid_blocks.append(svg)
        return f"<!--MERMAID_PLACEHOLDER_{idx}-->"

    md_text = re.sub(r"```mermaid\s*\n(.*?)\n```", replace_mermaid, md_text, flags=re.DOTALL)

    # 2. Coletar fórmulas matemáticas para processamento em lote
    math_queue = []
    
    # Blocos de fórmula $$...$$
    def collect_math_block(match):
        expr = match.group(1).strip()
        idx = len(math_queue)
        math_queue.append({"expr": expr, "display": True})
        return f"<!--MATH_BLOCK_PLACEHOLDER_{idx}-->"

    md_text = re.sub(r"\$\$(.*?)\$\$", collect_math_block, md_text, flags=re.DOTALL)

    # Fórmulas inline $...$
    def collect_inline_math(match):
        expr = match.group(1).strip()
        idx = len(math_queue)
        math_queue.append({"expr": expr, "display": False})
        return f"INLINEMATHID{idx}ENDID"

    md_text = re.sub(r"(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)", collect_inline_math, md_text)

    # 3. Executar KaTeX em lote
    print(f"Renderizando {len(math_queue)} expressões matemáticas via KaTeX...")
    rendered_math = batch_render_katex(math_queue)

    # 4. Converter Markdown para HTML
    html_body = markdown.markdown(
        md_text,
        extensions=[
            "tables",
            "fenced_code",
            "nl2br",
            "sane_lists",
            "toc"
        ]
    )

    # 5. Re-injetar fórmulas renderizadas
    for idx, rendered in enumerate(rendered_math):
        # Substituir blocos
        block_tag = f"<!--MATH_BLOCK_PLACEHOLDER_{idx}-->"
        escaped_block_tag = f"&lt;!--MATH_BLOCK_PLACEHOLDER_{idx}--&gt;"
        wrapper = f'<div class="math-block-container">{rendered}</div>'
        html_body = html_body.replace(block_tag, wrapper)
        html_body = html_body.replace(escaped_block_tag, wrapper)

        # Substituir inline
        inline_tag = f"INLINEMATHID{idx}ENDID"
        html_body = html_body.replace(inline_tag, rendered)

    # 6. Re-injetar Diagramas Mermaid
    captions = [
        "Figura 1: Arquitetura Multicamada do Sistema Supervisório Industrial Spectrum-Lab Pro.",
        "Figura 2: Grafo de Transições da Máquina de Estados Finita (FSM) e Timeouts Operacionais.",
        "Figura 3: Diagrama de Sequência Temporal — Ciclo de Calibração e Aquisição Óptica.",
        "Figura 4: Fluxo de Intertravamento Operacional e Verificação Estanque de Perfis de Calibração."
    ]

    for idx, svg in enumerate(mermaid_blocks, 1):
        cap = captions[idx - 1] if idx <= len(captions) else f"Figura {idx}: Diagrama Técnico."
        clean_svg = re.sub(r'style="max-width:\s*[^;"]+;"', 'style="width: 100%; height: auto; max-height: 480px;"', svg)
        wrapper = f"""
        <div class="diagram-container">
            <div class="diagram-svg">{clean_svg}</div>
            <div class="diagram-caption">{cap}</div>
        </div>
        """
        html_body = html_body.replace(f"<!--MERMAID_PLACEHOLDER_{idx}-->", wrapper)
        html_body = html_body.replace(f"&lt;!--MERMAID_PLACEHOLDER_{idx}--&gt;", wrapper)

    # 7. Ler KaTeX CSS
    katex_css_content = ""
    if os.path.exists(KATEX_CSS):
        with open(KATEX_CSS, "r", encoding="utf-8") as f:
            katex_css_content = f.read()

    # 8. Template HTML Completo
    full_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>SPECTRUM-LAB PRO v4.9.14 (Build 1250) — Documentação Técnica</title>
<style>
/* Reset e Base */
*, *::before, *::after {{
    box-sizing: border-box;
}}

@page {{
    size: A4 portrait;
    margin: 18mm 14mm 18mm 14mm;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 9pt;
    line-height: 1.55;
    color: #1e293b;
    background-color: #ffffff;
    margin: 0;
    padding: 0;
}}

/* KaTeX Estilos Embutidos */
{katex_css_content}

/* Tipografia */
h1, h2, h3, h4 {{
    color: #0f172a;
    font-weight: 700;
    line-height: 1.25;
    margin-top: 1.6em;
    margin-bottom: 0.6em;
    page-break-after: avoid;
    break-after: avoid;
}}

h1 {{
    font-size: 18pt;
    letter-spacing: -0.02em;
    color: #0f172a;
    border-bottom: 3px solid #2563eb;
    padding-bottom: 8px;
    margin-top: 0;
}}

h2 {{
    font-size: 13pt;
    border-bottom: 1.5px solid #cbd5e1;
    padding-bottom: 4px;
    margin-top: 1.8em;
    color: #1e3a8a;
    page-break-after: avoid;
    break-after: avoid;
}}

h3 {{
    font-size: 10.5pt;
    color: #1e293b;
    margin-top: 1.3em;
    page-break-after: avoid;
    break-after: avoid;
}}

h4 {{
    font-size: 9.5pt;
    color: #334155;
    margin-top: 1.1em;
    page-break-after: avoid;
    break-after: avoid;
}}

p {{
    margin-top: 0;
    margin-bottom: 0.8em;
    text-align: justify;
}}

strong {{
    font-weight: 600;
    color: #0f172a;
}}

hr {{
    border: none;
    height: 1px;
    background: #e2e8f0;
    margin: 18px 0;
}}

/* Listas */
ul, ol {{
    margin-top: 0;
    margin-bottom: 0.8em;
    padding-left: 20px;
}}

li {{
    margin-bottom: 0.3em;
}}

/* Tabelas */
table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 0.8em;
    margin-bottom: 1.3em;
    font-size: 8.2pt;
    background-color: #ffffff;
    page-break-inside: auto;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
}}

tr {{
    page-break-inside: avoid;
    break-inside: avoid;
}}

thead {{
    display: table-header-group;
}}

th {{
    background: #1e293b;
    color: #ffffff;
    font-weight: 600;
    text-align: left;
    padding: 6px 8px;
    font-size: 8.2pt;
    border: 1px solid #334155;
}}

td {{
    padding: 5px 8px;
    border: 1px solid #e2e8f0;
    color: #334155;
    vertical-align: top;
}}

tbody tr:nth-child(even) {{
    background-color: #f8fafc;
}}

tbody tr:hover {{
    background-color: #f1f5f9;
}}

/* Blocos de Código */
pre {{
    background-color: #0f172a;
    color: #f1f5f9;
    padding: 10px 12px;
    border-radius: 6px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 7.8pt;
    line-height: 1.45;
    overflow-x: auto;
    margin-top: 0.5em;
    margin-bottom: 1em;
    border: 1px solid #334155;
    page-break-inside: avoid;
    break-inside: avoid;
}}

code {{
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 8pt;
    background-color: #f1f5f9;
    color: #0f172a;
    padding: 1px 4px;
    border-radius: 3px;
    border: 1px solid #e2e8f0;
}}

pre code {{
    background-color: transparent;
    color: #f1f5f9;
    padding: 0;
    border: none;
    font-size: 7.8pt;
}}

/* Diagramas SVG */
.diagram-container {{
    margin: 14px 0;
    padding: 10px;
    background-color: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    text-align: center;
    page-break-inside: avoid;
    break-inside: avoid;
}}

.diagram-svg {{
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
    overflow: hidden;
}}

.diagram-svg svg {{
    max-width: 100%;
    height: auto;
    max-height: 460px;
}}

.diagram-caption {{
    margin-top: 6px;
    font-size: 7.8pt;
    font-weight: 600;
    color: #475569;
    font-style: italic;
}}

/* Fórmulas Matemáticas */
.math-block-container {{
    margin: 10px 0;
    padding: 8px 12px;
    background-color: #f8fafc;
    border-left: 3.5px solid #2563eb;
    border-radius: 0 4px 4px 0;
    text-align: center;
    page-break-inside: avoid;
    break-inside: avoid;
    overflow-x: auto;
}}

.katex {{
    font-size: 1.02em !important;
}}

.katex-display {{
    margin: 0.3em 0 !important;
}}

/* Citações e Caixas de Alerta */
blockquote {{
    margin: 10px 0;
    padding: 8px 12px;
    background-color: #eff6ff;
    border-left: 4px solid #2563eb;
    color: #1e40af;
    border-radius: 0 4px 4px 0;
    font-size: 8.5pt;
}}

@media print {{
    body {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }}
    .diagram-container, pre, table {{
        page-break-inside: avoid;
    }}
}}
</style>
</head>
<body>

<div class="content-wrapper">
{html_body}
</div>

</body>
</html>
"""

    html_path = os.path.join(WORKSPACE_DIR, "documentacao_tecnica_compiled.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Documento HTML compilado: {html_path} ({len(full_html):,} bytes)")
    return html_path

def compile_pdf(html_path):
    print("Compilando PDF via Chrome Headless...")
    
    header_html = """
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 7pt; color: #64748b; width: 100%; padding: 0 14mm; display: flex; justify-content: space-between; border-bottom: 0.5px solid #e2e8f0; padding-bottom: 2px;">
        <span><strong>SPECTRUM-LAB PRO</strong> v4.9.14 (Build 1250)</span>
        <span>Documentação Técnica do Sistema Supervisório Industrial</span>
    </div>
    """
    
    footer_html = """
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 7pt; color: #64748b; width: 100%; padding: 0 14mm; display: flex; justify-content: space-between; border-top: 0.5px solid #e2e8f0; padding-top: 2px;">
        <span>Confidencial &bull; Engenharia & Instrumentação &bull; 04/09/2026</span>
        <span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span>
    </div>
    """

    cmd = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--enable-local-file-accesses",
        "--run-all-compositor-stages-before-draw",
        "--display-header-footer",
        f"--header-template={header_html}",
        f"--footer-template={footer_html}",
        f"--print-to-pdf={LOCAL_PDF_PATH}",
        os.path.abspath(html_path)
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("Erro no Chrome:", res.stderr)
        sys.exit(1)

    size = os.path.getsize(LOCAL_PDF_PATH)
    print(f"PDF local gerado com sucesso: {LOCAL_PDF_PATH} ({size:,} bytes)")

    # Sincronizar cópia na pasta Downloads
    try:
        shutil.copy2(LOCAL_PDF_PATH, DOWNLOADS_PDF_PATH)
        print(f"PDF atualizado em Downloads: {DOWNLOADS_PDF_PATH}")
    except Exception as e:
        print(f"Erro ao copiar para Downloads: {e}")

    # Gerar screenshot da primeira página para inspeção visual
    screenshot_path = os.path.join(WORKSPACE_DIR, "preview_documentacao_pagina_1.png")
    cmd_shot = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        f"--screenshot={screenshot_path}",
        "--window-size=1200,1600",
        os.path.abspath(html_path)
    ]
    subprocess.run(cmd_shot, capture_output=True)
    if os.path.exists(screenshot_path):
        print(f"Preview da documentação gerado: {screenshot_path}")

if __name__ == "__main__":
    html_path = build_html_document()
    compile_pdf(html_path)
    print("Concluído com sucesso absoluto!")
