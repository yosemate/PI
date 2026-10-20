from pathlib import Path
ROOT=Path.cwd()
def region(text,start,end,new):
 a=text.index(start);b=text.index(end,a);return text[:a]+new+text[b:]
p=ROOT/'main.py';s=p.read_text(encoding='utf-8')
s=region(s,'class CardDiagnosticoAS7263(QFrame):','# =====================================================================\n# 3. DIÁLOGO','from diagnostics import SensorDiagnosticsCard as CardDiagnosticoAS7263\n\n\n')
s=region(s,'    def init_ui(self):','    def showEvent(self,event):','    def init_ui(self):\n        self._create_menu_bar()\n        from scada_ui import build_dashboard\n        build_dashboard(self)\n\n\n')
s=region(s,'    def _handle_telemetry_line(self, line: str):','    def _execute_atomic_manual_button(','''    def _handle_telemetry_line(self, line: str):
        """Configuração, valores recebidos e medições calculadas permanecem distintos."""
        card=getattr(self,"card_telemetria",None)
        if card is None:return
        text=line.strip();data={}
        if text.startswith("DIAG:"):
            for i,part in enumerate(text[5:].split("|")):
                if ":" in part:
                    key,value=part.split(":",1);data[key.upper()]=value
                elif i==0:data["TEMP"]=part
        elif text.startswith("TELEM:"):
            for part in text[6:].replace(",",";").split(";"):
                sep="=" if "=" in part else ":"
                if sep in part:
                    key,value=part.split(sep,1);data[key.upper()]=value
        elif text.startswith("{"):
            try:
                parsed=json.loads(text)
                if isinstance(parsed,dict):data={k.upper():v for k,v in parsed.items()}
            except (ValueError,TypeError):return
        if not data:return
        def value(*keys):
            return next((data[key] for key in keys if key in data),None)
        status=value("STATUS","STATE","SENSOR_STATUS")
        if str(status).upper() in ("ERRO","ERROR","FAIL"):
            card.reset("Erro reportado pelo sensor");return
        card.atualizar_telemetria(die_temp=value("TEMP","DIE_TEMP","TEMPERATURA"),
            gain=value("GAINCFG","GAIN","PGA_GAIN"),integration=value("INTCFG","INT","INTEGRATION"),
            led=value("LEDCFG","LED_CURRENT","LED"),led_state=value("LEDSTATE","LED_STATE"),
            hw_id=value("HW","HARDWARE"),status=status,saturation=value("SAT","SATURACAO","SATURATION"),received=True)
        if "LEDCFG" not in data and "LEDSTATE" not in data and str(data.get("LED","")).upper() not in ("ON","OFF","LIGADO","DESLIGADO"):
            card.lbl_led_state.setText("Não informado")

''')
s=s.replace('        self._refresh_controls()\n        if self._manual_dialog:\n            self._manual_dialog.update_interlocks_and_leds()','        self.card_telemetria.reset("Aguardando telemetria" if connected else "Desconectado")\n        self.card_esp32.refresh(self)\n        self._refresh_controls()\n        if self._manual_dialog:\n            self._manual_dialog.update_interlocks_and_leds()',1)
s=s.replace('self.card_telemetria.atualizar_telemetria(status="Normal")','self.card_telemetria.atualizar_telemetria(status="Sensor inicializado")')
s=s.replace('status="Saturação" if is_sat else "Normal"','status="Saturação detectada" if is_sat else "Leitura válida"')
s=s.replace('    splash = AnimatedSplashScreen()\n    main_win = SpectrumLabMainWindow()\n\n    def show_main():','    splash = AnimatedSplashScreen()\n    main_win = None\n\n    def show_main():')
s=s.replace('    splash.finished.connect(show_main)\n    splash.start_animation()\n','''    splash.finished.connect(show_main)
    splash.start_animation()
    def initialize():
        nonlocal main_win
        splash.set_stage(15,"Carregando configurações e dados")
        main_win=SpectrumLabMainWindow()
        splash.set_stage(90,"Painel e controles preparados")
        splash.mark_ready()
    QTimer.singleShot(0,initialize)
''')
p.write_text(s,encoding='utf-8')
(ROOT/'splash_screen.py').write_text('from modern_splash import AnimatedSplashScreen\n',encoding='utf-8')
p=ROOT/'appearance.py';s=p.read_text(encoding='utf-8')
for old,new in [('#F3F6FA','#F2F5F7'),('#EDF2F7','#E5F3F0'),('#182B43','#192F39'),('#60738A','#62747E'),('#2563EB','#087D7B'),('#101827','#111B24'),('#182438','#1B2934'),('#202F46','#223C40'),('#8DB4FF','#76D8D0')]:s=s.replace('"'+old+'"','"'+new+'"')
s=s.replace('        rendered=transform_stylesheet(scoped,self.theme)','        factory=getattr(widget,"_scada_style_factory",None)\n        rendered=factory(palette_for(self.theme)) if factory else transform_stylesheet(scoped,self.theme)')
p.write_text(s,encoding='utf-8')
p=ROOT/'animated_chart.py';s=p.read_text(encoding='utf-8')
for color in ['#EF4444','#DC2626','#C084FC','#A855F7','#9333EA','#7E22CE']:s=s.replace("'"+color+"'","'#087D7B'")
s=s.replace('bar_width = min(40.0, max(18.0, w * 0.55))','bar_width = min(95.0, max(18.0, w * 0.62))')
s=s.replace('painter.setPen(QPen(QColor(theme_color("#383838","border")), 1))','painter.setPen(Qt.NoPen)',1)
s=s.replace('gradient.setColorAt(0.0, base_col)','base_col.setAlpha(75)\n            light_col.setAlpha(75)\n            gradient.setColorAt(0.0, base_col)',1)
s=s.replace('QColor(56, 189, 248, 45)','QColor(8, 125, 123, 0)').replace('QColor(56, 189, 248, 5)','QColor(8, 125, 123, 0)').replace('QColor(56, 189, 248, 70)','QColor(8, 125, 123, 0)')
s=s.replace('PERFIL ESPECTRAL NIR (610nm - 860nm)','Bandas espectrais · 610–860 nm')
p.write_text(s,encoding='utf-8')
p=ROOT/'version.py';s=p.read_text(encoding='utf-8').replace('"4.12.0"','"4.13.0"').replace('"1254"','"1255"');p.write_text(s,encoding='utf-8')
firm=Path('C:/Users/mateu/OneDrive/Área de Trabalho/sketch_sep4a_copy_20261008183551/sketch_sep4a_copy_20261008183551.ino')
s=firm.read_text(encoding='utf-8').replace('SpectrumLabPro 4.10.0','SpectrumLabPro 4.13.0')
s=s.replace('sensor.drvOff()','driverOff()').replace('sensor.drvOn()','driverOn()')
s=s.replace('void enviarDiagnosticoSensor() {','bool ledLigado=false;\nvoid driverOff() { sensor.drvOff(); ledLigado=false; }\nvoid driverOn() { sensor.drvOn(); ledLigado=true; }\n\nvoid enviarDiagnosticoSensor() {')
s=region(s,'void enviarDiagnosticoSensor() {','void processarComando(String cmd);','''void enviarDiagnosticoSensor() {
  if (!sensorConectado || spectrumSensorIoError) {
    responder("DIAG:TEMP:NA|HW:DESCONECTADO|STATUS:ERRO");
    return;
  }
  uint8_t temperatura=sensor.readTemperature();
  if (spectrumSensorIoError) {
    responder("DIAG:TEMP:NA|STATUS:ERRO");
    return;
  }
  responder("DIAG:TEMP:"+String(temperatura)+
            "|GAINCFG:64x|INTCFG:140.0ms|LEDCFG:50mA|LEDSTATE:"+
            String(ledLigado ? "ON" : "OFF")+"|HW:AS7263_NIR|STATUS:OK");
}

''')
firm.write_text(s,encoding='utf-8')
s=(ROOT/'SpectrumLabPro_4_12_0.spec').read_text(encoding='utf-8').replace('SpectrumLabPro_4_12_0','SpectrumLabPro_4_13_0')
s=s.replace("datas=[('banco_materiais.json', '.')],","datas=[('banco_materiais.json', '.'), ('assets/brands', 'assets/brands')],")
(ROOT/'SpectrumLabPro_4_13_0.spec').write_text(s,encoding='utf-8')
print('SCADA 4.13: apresentação, diagnósticos e firmware atualizados.')

