#include <Wire.h>
#include "src/Adafruit_AS726x.h"
#include <ESP32Servo.h>
#include <WiFi.h>
#include "BluetoothSerial.h"

// SpectrumLabPro 4.14.0 / protocolo 2 + porta protocolo 1.
// Gaveta e carrinho mantem posicoes estimadas; porta possui dois fins de curso.
BluetoothSerial SerialBT;
WiFiServer tcpServer(8080);
WiFiClient tcpClient;
Servo servoGaveta, servoCarrinho, servoPorta;
Adafruit_AS726x sensor;
const int PINO_SERVO_GAVETA=18, PINO_SERVO_CARRINHO=19, PINO_SDA=21, PINO_SCL=22;
// Contatos NA entre GPIO e GND. Carcaca: pressionado quando FECHADA.
const int PINO_SERVO_PORTA=23, PINO_FC_PORTA_ABERTA=25;
const int PINO_FC_PORTA_FECHADA=26, PINO_FC_CARCACA_FECHADA=27;
// Calibrar o neutro e o sentido no servo real antes de operar a porta.
const int PORTA_PARAR_US=1500, PORTA_ABRIR_US=1600, PORTA_FECHAR_US=1400;
const unsigned long PORTA_TIMEOUT_MS=10000, FC_DEBOUNCE_MS=30;
bool portaMovendo=false, falhaCarcaca=false, leituraEmCurso=false, avancandoSensor=false, movendoGaveta=false;
bool carcacaAutorizada=false, carcacaFisicaAnterior=false;
int canalAutorizado=-1;
unsigned long renovacaoCarcaca=0;
const unsigned long CARCACA_AUTORIZACAO_TIMEOUT_MS=6000;
bool gavetaConfirmadaFechada=false;
bool ultimoFcAberta=false, ultimoFcFechada=false, ultimoFcCarcaca=false;
struct FimCurso {
  int pino;
  bool bruto=false, ativo=false;
  unsigned long mudouEm=0;
  void atualizar() {
    bool novo=digitalRead(pino)==LOW;
    if (novo!=bruto) { bruto=novo; mudouEm=millis(); }
    if (millis()-mudouEm>=FC_DEBOUNCE_MS) ativo=bruto;
  }
};
FimCurso fcPortaAberta{PINO_FC_PORTA_ABERTA};
FimCurso fcPortaFechada{PINO_FC_PORTA_FECHADA};
FimCurso fcCarcacaFechada{PINO_FC_CARCACA_FECHADA};
const int GAVETA_FECHADA=5, GAVETA_ABERTA=175, CARRINHO_RECUADO=180, CARRINHO_LEITURA=5;
int posAtualGaveta=GAVETA_FECHADA, posAtualCarrinho=CARRINHO_RECUADO;
bool sensorConectado=false, ocupado=false, abortarMovimento=false, emRepouso=false;
String buffers[3];
unsigned long ultimaAtividade=0;
uint16_t bufferCanais[6];

void responder(const String &msg) {
  Serial.println(msg);
  if (SerialBT.hasClient()) SerialBT.println(msg);
  if (tcpClient && tcpClient.connected()) tcpClient.println(msg);
}

bool ledLigado=false;
void driverOff() { sensor.drvOff(); ledLigado=false; }
void driverOn() { sensor.drvOn(); ledLigado=true; }

void enviarDiagnosticoSensor() {
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

void processarComando(String cmd,int canal);
void enviarEstadoPorta();
void paradaEmergencia();
void pollInputs();

void consumir(Stream &stream, int canal) {
  while (stream.available()) {
    char c=(char)stream.read();
    if (c=='\r') continue;
    if (c=='\n') {
      String command=buffers[canal];
      buffers[canal]="";
      if (command.length()) processarComando(command,canal);
    } else {
      buffers[canal]+=c;
      if (buffers[canal].length()>160) {
        buffers[canal]="";
        responder("STATUS:COMANDO_ERRO:LINHA_LONGA");
      }
    }
  }
}

void pararPorta() {
  if (servoPorta.attached()) servoPorta.writeMicroseconds(PORTA_PARAR_US);
  portaMovendo=false;
}

bool carcacaFisicamenteFechada() {
  return fcCarcacaFechada.bruto && fcCarcacaFechada.ativo;
}

bool carcacaSegura() {
  return carcacaFisicamenteFechada() ||
         (carcacaAutorizada && millis()-renovacaoCarcaca<CARCACA_AUTORIZACAO_TIMEOUT_MS);
}

void revogarCarcaca() {
  bool estavaAutorizada=carcacaAutorizada;
  carcacaAutorizada=false;
  canalAutorizado=-1;
  if (estavaAutorizada) responder(carcacaFisicamenteFechada() ? "STATUS:CARCACA_AUTORIZACAO_REVOGADA:CARCACA_FECHADA" : "STATUS:CARCACA_AUTORIZACAO_REVOGADA");
}

void atualizarFinsCurso() {
  fcPortaAberta.atualizar();
  fcPortaFechada.atualizar();
  fcCarcacaFechada.atualizar();
  bool fisicamenteFechada=carcacaFisicamenteFechada();
  if (carcacaFisicaAnterior && !fisicamenteFechada) {
    revogarCarcaca();
    if (ocupado) abortarMovimento=true;
    gavetaConfirmadaFechada=false;
  }
  carcacaFisicaAnterior=fisicamenteFechada;
  if (carcacaAutorizada && (fisicamenteFechada ||
      millis()-renovacaoCarcaca>=CARCACA_AUTORIZACAO_TIMEOUT_MS ||
      (canalAutorizado==1 && !SerialBT.hasClient()) ||
      (canalAutorizado==2 && (!tcpClient || !tcpClient.connected())))) revogarCarcaca();
  if (!carcacaSegura()) {
    pararPorta();
    servoGaveta.detach();
    servoCarrinho.detach();
    if (sensorConectado && ledLigado) driverOff();
    if (ocupado) abortarMovimento=true;
  }
  if (!fisicamenteFechada && !falhaCarcaca) responder("STATUS:CARCACA_ABERTA");
  if (fisicamenteFechada && falhaCarcaca) responder("STATUS:CARCACA_FECHADA");
  falhaCarcaca=!fisicamenteFechada;
  if ((leituraEmCurso || avancandoSensor) &&
      (!fcPortaFechada.bruto || fcPortaAberta.bruto)) {
    abortarMovimento=true;
    if (sensorConectado && ledLigado) driverOff();
    servoCarrinho.detach();
  }
  if (portaMovendo && fcPortaAberta.bruto && fcPortaFechada.bruto) {
    pararPorta();
    abortarMovimento=true;
    responder("STATUS:PORTA_ERRO:FINS_CONTRADITORIOS");
  }
  if (ultimoFcAberta!=fcPortaAberta.ativo || ultimoFcFechada!=fcPortaFechada.ativo ||
      ultimoFcCarcaca!=fisicamenteFechada) {
    ultimoFcAberta=fcPortaAberta.ativo;
    ultimoFcFechada=fcPortaFechada.ativo;
    ultimoFcCarcaca=fisicamenteFechada;
    enviarEstadoPorta();
  }
}

void enviarEstadoPorta() {
  responder("PORTA:ABERTA:"+String(fcPortaAberta.ativo ? 1 : 0)+
            "|FECHADA:"+String(fcPortaFechada.ativo ? 1 : 0)+
            "|CARCACA_FECHADA:"+String(carcacaFisicamenteFechada() ? 1 : 0));
}

void pollInputs() {
  atualizarFinsCurso();
  consumir(Serial,0);
  consumir(SerialBT,1);
  if (tcpServer.hasClient()) {
    WiFiClient novo=tcpServer.available();
    if (!tcpClient || !tcpClient.connected()) {
      if (tcpClient) tcpClient.stop();
      tcpClient=novo;
      buffers[2]="";
    } else novo.stop();
  }
  if (tcpClient && tcpClient.connected()) consumir(tcpClient,2);
}

// Mantem recepcao de emergencia e heartbeat durante esperas.
bool aguardar(unsigned long intervalo,bool interrompivel=true) {
  unsigned long inicio=millis();
  while (millis()-inicio<intervalo) {
    pollInputs();
    if (!carcacaSegura() || (interrompivel && abortarMovimento) ||
        (movendoGaveta && (!fcPortaAberta.bruto || fcPortaFechada.bruto))) return false;
    delay(2);
  }
  return true;
}

bool moverPara(Servo &servo,int pino,int &pos,int destino,int intervalo=15,bool interrompivel=true) {
  if (!carcacaSegura()) return false;
  if (pos==destino) {
    servo.attach(pino,500,2400);
    servo.write(destino);
    bool ok=aguardar(1000,interrompivel);
    servo.detach();
    return ok;
  }
  servo.attach(pino,500,2400);
  int step=destino>pos ? 1 : -1;
  bool ok=true;
  while (pos!=destino) {
    pollInputs();
    if (!carcacaSegura() || (interrompivel && abortarMovimento)) { ok=false; break; }
    if (pino==PINO_SERVO_GAVETA &&
        (!fcPortaAberta.bruto || !fcPortaAberta.ativo || fcPortaFechada.bruto)) {
      abortarMovimento=true;
      ok=false;
      break;
    }
    pos+=step;
    servo.write(pos);
    if (!aguardar(intervalo,interrompivel)) { ok=false; break; }
  }
  if (ok) ok=aguardar(80,interrompivel);
  servo.detach();
  return ok;
}

bool moverPorta(bool abrir) {
  if (!carcacaSegura()) return false;
  if (fcPortaAberta.bruto && fcPortaFechada.bruto) {
    responder("STATUS:PORTA_ERRO:FINS_CONTRADITORIOS");
    return false;
  }
  FimCurso &destino=abrir ? fcPortaAberta : fcPortaFechada;
  unsigned long inicio=millis();
  responder(abrir ? "STATUS:ABRINDO_PORTA" : "STATUS:FECHANDO_PORTA");
  while (millis()-inicio<PORTA_TIMEOUT_MS) {
    pollInputs();
    if (abortarMovimento || !carcacaSegura()) { pararPorta(); return false; }
    if (fcPortaAberta.bruto && fcPortaFechada.bruto) {
      pararPorta();
      responder("STATUS:PORTA_ERRO:FINS_CONTRADITORIOS");
      return false;
    }
    if (destino.bruto) {
      // Para no primeiro contato; confirma a chegada apos debounce.
      pararPorta();
      if (destino.ativo) {
        enviarEstadoPorta();
        responder(abrir ? "STATUS:PORTA_ABERTA" : "STATUS:PORTA_FECHADA");
        return true;
      }
    } else {
      servoPorta.writeMicroseconds(abrir ? PORTA_ABRIR_US : PORTA_FECHAR_US);
      portaMovendo=true;
    }
    delay(2);
  }
  pararPorta();
  responder("STATUS:PORTA_ERRO:TIMEOUT");
  return false;
}

void paradaEmergencia() {
  pararPorta();
  revogarCarcaca();
  ocupado=true;
  emRepouso=true;
  gavetaConfirmadaFechada=false;
  servoGaveta.detach();
  if (sensorConectado) driverOff();
  // Emergencia nao inicia fechamento da gaveta: exige confirmacao do operador.
  // Com carcaca aberta, apenas interrompe; nao inicia recolhimento.
  if (carcacaFisicamenteFechada()) {
    moverPara(servoCarrinho,PINO_SERVO_CARRINHO,posAtualCarrinho,CARRINHO_RECUADO,12,false);
  }
  abortarMovimento=false;
  ocupado=false;
  emRepouso=false;
  enviarEstadoPorta();
  responder("STATUS:EMERGENCIA_ACIONADA");
}

bool realizarLeituraEspectral(bool escuro,const String &id) {
  if (!sensorConectado || spectrumSensorIoError) {
    responder("STATUS:LEITURA_ERRO:"+id+":SENSOR_DESCONECTADO");
    return false;
  }
  if (!carcacaSegura() || !gavetaConfirmadaFechada || !fcPortaFechada.ativo || !fcPortaFechada.bruto || fcPortaAberta.bruto ||
      posAtualGaveta!=GAVETA_FECHADA || posAtualCarrinho!=CARRINHO_LEITURA) {
    responder("STATUS:LEITURA_ERRO:"+id+":POSICAO_INVALIDA");
    return false;
  }
  if (escuro) driverOff(); else driverOn();
  if (!aguardar(150)) { driverOff(); return false; }
  sensor.startMeasurement();
  unsigned long inicio=millis();
  while (!sensor.dataReady()) {
    if (!aguardar(5)) { driverOff(); return false; }
    if (millis()-inicio>=1500) {
      driverOff();
      responder("STATUS:LEITURA_ERRO:"+id+":TIMEOUT");
      return false;
    }
  }
  sensor.readRawValues(bufferCanais);
  driverOff();
  if (abortarMovimento) return false;
  if (spectrumSensorIoError) {
    sensorConectado=false;
    responder("STATUS:LEITURA_ERRO:"+id+":FALHA_I2C");
    return false;
  }
  String payload="SCAN:"+id+"|DATA:";
  for (int i=0;i<6;i++) {
    if (bufferCanais[i]>=65500) {
      responder("STATUS:LEITURA_ERRO:"+id+":SATURACAO");
      return false;
    }
    payload+=String(bufferCanais[i]);
    if (i<5) payload+=",";
  }
  responder(payload);
  responder("STATUS:LEITURA_CONCLUIDA:"+id);
  return true;
}

void processarComando(String cmd,int canal) {
  cmd.trim();
  ultimaAtividade=millis();
  if (cmd=="CMD:PING" || cmd=="PING") {
    responder("STATUS:PROTOCOLO_2");
    responder("STATUS:PORTA_PROTOCOLO_1");
    enviarEstadoPorta();
    responder(sensorConectado ? "STATUS:SENSOR_OK" : "STATUS:SENSOR_ERRO");
    responder("STATUS:PONG");
    return;
  }
  if (cmd=="CMD:EMERGENCIA" || cmd=="CMD:REPOUSO_SUAVE") {
    abortarMovimento=true;
    pararPorta();
    if (sensorConectado) driverOff();
    if (!ocupado) paradaEmergencia();
    return;
  }
  // O supervisório valida usuário/senha; nenhuma senha trafega no protocolo.
  // A autorização fica restrita ao transporte de origem e requer renovação.
  if (cmd=="CMD:AUTORIZAR_CARCACA") {
    if (ocupado || carcacaFisicamenteFechada() || (carcacaAutorizada && canal!=canalAutorizado)) {
      responder("STATUS:COMANDO_ERRO:AUTORIZACAO_INDISPONIVEL");
    } else {
      carcacaAutorizada=true;
      canalAutorizado=canal;
      renovacaoCarcaca=millis();
      responder("STATUS:CARCACA_AUTORIZADA");
    }
    return;
  }
  if (cmd=="CMD:RENOVAR_CARCACA") {
    if (carcacaAutorizada && canal==canalAutorizado) renovacaoCarcaca=millis();
    return;
  }
  if (cmd=="CMD:REVOGAR_CARCACA") {
    if (canal==canalAutorizado) {
      revogarCarcaca();
      if (ocupado && !carcacaFisicamenteFechada()) abortarMovimento=true;
    }
    return;
  }
  if (cmd=="CMD:ESTADO_PORTA") {
    enviarEstadoPorta();
    return;
  }
  if ((!carcacaSegura() || (!carcacaFisicamenteFechada() && canal!=canalAutorizado)) && cmd!="CMD:DIAG_SENSOR") {
    responder("STATUS:COMANDO_ERRO:CARCACA_ABERTA");
    return;
  }
  if (ocupado) {
    responder("STATUS:COMANDO_ERRO:OCUPADO");
    return;
  }
  ocupado=true;
  bool ok=true;
  if (cmd=="CMD:ABRIR_PORTA" || cmd=="CMD:FECHAR_PORTA") {
    if (posAtualCarrinho!=CARRINHO_RECUADO) {
      responder("STATUS:COMANDO_ERRO:SENSOR_NAO_RECUADO");
      ok=false;
    } else if (cmd=="CMD:FECHAR_PORTA" && !gavetaConfirmadaFechada) {
      responder("STATUS:COMANDO_ERRO:GAVETA_NAO_FECHADA");
      ok=false;
    } else ok=moverPorta(cmd=="CMD:ABRIR_PORTA");
  } else if (cmd=="CMD:ABRIR_GAVETA" || cmd=="CMD:FECHAR_GAVETA") {
    if (posAtualCarrinho!=CARRINHO_RECUADO) {
      responder("STATUS:COMANDO_ERRO:SENSOR_NAO_RECUADO");
      ok=false;
    } else if (!fcPortaAberta.ativo || !fcPortaAberta.bruto || fcPortaFechada.bruto) {
      responder("STATUS:COMANDO_ERRO:PORTA_NAO_ABERTA");
      ok=false;
    } else {
      bool abrir=cmd=="CMD:ABRIR_GAVETA";
      gavetaConfirmadaFechada=false;
      responder(abrir ? "STATUS:ABRINDO_GAVETA" : "STATUS:FECHANDO_GAVETA");
      movendoGaveta=true;
      ok=moverPara(servoGaveta,PINO_SERVO_GAVETA,posAtualGaveta,
                   abrir ? GAVETA_ABERTA : GAVETA_FECHADA,18);
      movendoGaveta=false;
      gavetaConfirmadaFechada=ok && !abrir;
      if (ok) responder(abrir ? "STATUS:GAVETA_ABERTA" : "STATUS:GAVETA_FECHADA");
    }
  } else if (cmd=="CMD:AVANCAR_SENSOR") {
    if (!fcPortaFechada.ativo || !fcPortaFechada.bruto || fcPortaAberta.bruto) {
      responder("STATUS:COMANDO_ERRO:PORTA_NAO_FECHADA");
      ok=false;
    } else if (!gavetaConfirmadaFechada || posAtualGaveta!=GAVETA_FECHADA) {
      responder("STATUS:COMANDO_ERRO:GAVETA_NAO_FECHADA");
      ok=false;
    } else {
      responder("STATUS:POSICIONANDO_SENSOR");
      avancandoSensor=true;
      ok=moverPara(servoCarrinho,PINO_SERVO_CARRINHO,posAtualCarrinho,CARRINHO_LEITURA);
      avancandoSensor=false;
      if (ok) responder("STATUS:SENSOR_AVANCADO");
    }
  } else if (cmd=="CMD:RECUAR_SENSOR") {
    responder("STATUS:RECUANDO_SENSOR");
    ok=moverPara(servoCarrinho,PINO_SERVO_CARRINHO,posAtualCarrinho,CARRINHO_RECUADO);
    if (ok) responder("STATUS:SENSOR_RECUADO");
  } else if (cmd.startsWith("CMD:LER_ESPECTRO:") || cmd.startsWith("CMD:LER_ESCURO:")) {
    bool escuro=cmd.startsWith("CMD:LER_ESCURO:");
    String id=cmd.substring(cmd.lastIndexOf(':')+1);
    bool valido=id.length()>0 && id.length()<=64;
    for (unsigned int i=0;i<id.length();i++)
      valido=valido && (isAlphaNumeric(id[i]) || id[i]=='_' || id[i]=='-');
    if (!valido) responder("STATUS:COMANDO_ERRO:ID_INVALIDO");
    else {
      leituraEmCurso=true;
      ok=realizarLeituraEspectral(escuro,id);
      leituraEmCurso=false;
    }
  } else if (cmd=="CMD:DIAG_SENSOR") {
    enviarDiagnosticoSensor();
  } else {
    responder("STATUS:COMANDO_ERRO:COMANDO_DESCONHECIDO");
    ok=false;
  }
  ocupado=false;
  if (abortarMovimento) paradaEmergencia();
}

void setup() {
  Serial.begin(115200);
  SerialBT.begin("Bancada_NIR_ESP32");
  WiFi.softAP("Bancada_NIR_AP");
  tcpServer.begin();
  Wire.begin(PINO_SDA,PINO_SCL);
  Wire.setTimeOut(50);
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  servoGaveta.setPeriodHertz(50);
  servoCarrinho.setPeriodHertz(50);
  servoPorta.setPeriodHertz(50);
  pinMode(PINO_FC_PORTA_ABERTA,INPUT_PULLUP);
  pinMode(PINO_FC_PORTA_FECHADA,INPUT_PULLUP);
  pinMode(PINO_FC_CARCACA_FECHADA,INPUT_PULLUP);
  servoPorta.attach(PINO_SERVO_PORTA,500,2400);
  pararPorta();
  fcPortaAberta.atualizar();
  fcPortaFechada.atualizar();
  fcCarcacaFechada.atualizar();
  delay(FC_DEBOUNCE_MS);
  atualizarFinsCurso();
  // Nao movimenta gaveta nem porta ao ligar. Aguarda comando confirmado.
  ocupado=true;
  if (carcacaFisicamenteFechada()) {
    servoCarrinho.attach(PINO_SERVO_CARRINHO,500,2400);
    servoCarrinho.write(CARRINHO_RECUADO);
    aguardar(1000);
    servoCarrinho.detach();
  }
  ocupado=false;
  abortarMovimento=false;
  spectrumSensorIoError=false;
  sensorConectado=sensor.begin() && !spectrumSensorIoError;
  if (sensorConectado) {
    sensor.setGain(GAIN_64X);
    sensor.setIntegrationTime(50);
    sensor.setDrvCurrent(LIMIT_50MA);
    sensor.setConversionType(MODE_2);
    driverOff();
    if (spectrumSensorIoError) sensorConectado=false;
  }
  responder("STATUS:PROTOCOLO_2");
  responder("STATUS:PORTA_PROTOCOLO_1");
  enviarEstadoPorta();
  responder(sensorConectado ? "STATUS:SENSOR_OK" : "STATUS:SENSOR_ERRO");
  ultimaAtividade=millis();
}

void loop() {
  pollInputs();
  if (!ocupado && millis()-ultimaAtividade>6000 &&
      (posAtualGaveta!=GAVETA_FECHADA || posAtualCarrinho!=CARRINHO_RECUADO)) {
    paradaEmergencia();
  }
  delay(2);
}
