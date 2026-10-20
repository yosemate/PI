#include <Wire.h>
#include "src/Adafruit_AS726x.h"
#include <ESP32Servo.h>
#include <WiFi.h>
#include "BluetoothSerial.h"

// SpectrumLabPro 4.10.0 / protocolo 2.
// Posicoes sao estimadas por comando; este hardware nao possui fim de curso.
BluetoothSerial SerialBT;
WiFiServer tcpServer(8080);
WiFiClient tcpClient;
Servo servoGaveta, servoCarrinho;
Adafruit_AS726x sensor;
const int PINO_SERVO_GAVETA=18, PINO_SERVO_CARRINHO=19, PINO_SDA=21, PINO_SCL=22;
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

void enviarDiagnosticoSensor() {
  if (!sensorConectado) {
    responder("DIAG:TEMP:0|GAIN:OFF|INT:0|LED:OFF|HW:DESCONECTADO|STATUS:ERRO");
    return;
  }
  responder("DIAG:TEMP:"+String(sensor.readTemperature())+
            "|GAIN:64x|INT:140.0ms|LED:50mA|HW:AS7263_NIR|STATUS:READY");
}

void processarComando(String cmd);
void paradaEmergencia();
void pollInputs();

void consumir(Stream &stream, int canal) {
  while (stream.available()) {
    char c=(char)stream.read();
    if (c=='\r') continue;
    if (c=='\n') {
      String command=buffers[canal];
      buffers[canal]="";
      if (command.length()) processarComando(command);
    } else {
      buffers[canal]+=c;
      if (buffers[canal].length()>160) {
        buffers[canal]="";
        responder("STATUS:COMANDO_ERRO:LINHA_LONGA");
      }
    }
  }
}

void pollInputs() {
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
    if (interrompivel && abortarMovimento) return false;
    delay(2);
  }
  return true;
}

bool moverPara(Servo &servo,int pino,int &pos,int destino,int intervalo=15,bool interrompivel=true) {
  if (pos==destino) return true;
  servo.attach(pino,500,2400);
  int step=destino>pos ? 1 : -1;
  bool ok=true;
  while (pos!=destino) {
    pollInputs();
    if (interrompivel && abortarMovimento) { ok=false; break; }
    pos+=step;
    servo.write(pos);
    if (!aguardar(intervalo,interrompivel)) { ok=false; break; }
  }
  if (ok) ok=aguardar(80,interrompivel);
  servo.detach();
  return ok;
}

void paradaEmergencia() {
  ocupado=true;
  emRepouso=true;
  if (sensorConectado) sensor.drvOff();
  // A recolha e uma sequencia controlada, nao um corte eletrico de emergencia.
  moverPara(servoCarrinho,PINO_SERVO_CARRINHO,posAtualCarrinho,CARRINHO_RECUADO,12,false);
  moverPara(servoGaveta,PINO_SERVO_GAVETA,posAtualGaveta,GAVETA_FECHADA,14,false);
  abortarMovimento=false;
  ocupado=false;
  emRepouso=false;
  responder("STATUS:EMERGENCIA_ACIONADA");
}

bool realizarLeituraEspectral(bool escuro,const String &id) {
  if (!sensorConectado || spectrumSensorIoError) {
    responder("STATUS:LEITURA_ERRO:"+id+":SENSOR_DESCONECTADO");
    return false;
  }
  if (posAtualGaveta!=GAVETA_FECHADA || posAtualCarrinho!=CARRINHO_LEITURA) {
    responder("STATUS:LEITURA_ERRO:"+id+":POSICAO_INVALIDA");
    return false;
  }
  if (escuro) sensor.drvOff(); else sensor.drvOn();
  if (!aguardar(150)) { sensor.drvOff(); return false; }
  sensor.startMeasurement();
  unsigned long inicio=millis();
  while (!sensor.dataReady()) {
    if (!aguardar(5)) { sensor.drvOff(); return false; }
    if (millis()-inicio>=1500) {
      sensor.drvOff();
      responder("STATUS:LEITURA_ERRO:"+id+":TIMEOUT");
      return false;
    }
  }
  sensor.readRawValues(bufferCanais);
  sensor.drvOff();
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

void processarComando(String cmd) {
  cmd.trim();
  ultimaAtividade=millis();
  if (cmd=="CMD:PING" || cmd=="PING") {
    responder("STATUS:PROTOCOLO_2");
    responder(sensorConectado ? "STATUS:SENSOR_OK" : "STATUS:SENSOR_ERRO");
    responder("STATUS:PONG");
    return;
  }
  if (cmd=="CMD:EMERGENCIA" || cmd=="CMD:REPOUSO_SUAVE") {
    abortarMovimento=true;
    if (sensorConectado) sensor.drvOff();
    if (!ocupado) paradaEmergencia();
    return;
  }
  if (ocupado) {
    responder("STATUS:COMANDO_ERRO:OCUPADO");
    return;
  }
  ocupado=true;
  bool ok=true;
  if (cmd=="CMD:ABRIR_GAVETA" || cmd=="CMD:FECHAR_GAVETA") {
    if (posAtualCarrinho!=CARRINHO_RECUADO) {
      responder("STATUS:COMANDO_ERRO:SENSOR_NAO_RECUADO");
      ok=false;
    } else {
      bool abrir=cmd=="CMD:ABRIR_GAVETA";
      responder(abrir ? "STATUS:ABRINDO_GAVETA" : "STATUS:FECHANDO_GAVETA");
      ok=moverPara(servoGaveta,PINO_SERVO_GAVETA,posAtualGaveta,
                   abrir ? GAVETA_ABERTA : GAVETA_FECHADA,18);
      if (ok) responder(abrir ? "STATUS:GAVETA_ABERTA" : "STATUS:GAVETA_FECHADA");
    }
  } else if (cmd=="CMD:AVANCAR_SENSOR") {
    if (posAtualGaveta!=GAVETA_FECHADA) {
      responder("STATUS:COMANDO_ERRO:GAVETA_NAO_FECHADA");
      ok=false;
    } else {
      responder("STATUS:POSICIONANDO_SENSOR");
      ok=moverPara(servoCarrinho,PINO_SERVO_CARRINHO,posAtualCarrinho,CARRINHO_LEITURA);
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
    else ok=realizarLeituraEspectral(escuro,id);
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
  // Posicionamento inicial sequencial para reduzir risco de colisao.
  servoCarrinho.attach(PINO_SERVO_CARRINHO,500,2400);
  servoCarrinho.write(CARRINHO_RECUADO);
  delay(1000);
  servoCarrinho.detach();
  servoGaveta.attach(PINO_SERVO_GAVETA,500,2400);
  servoGaveta.write(GAVETA_FECHADA);
  delay(1000);
  servoGaveta.detach();
  spectrumSensorIoError=false;
  sensorConectado=sensor.begin() && !spectrumSensorIoError;
  if (sensorConectado) {
    sensor.setGain(GAIN_64X);
    sensor.setIntegrationTime(50);
    sensor.setDrvCurrent(LIMIT_50MA);
    sensor.setConversionType(MODE_2);
    sensor.drvOff();
    if (spectrumSensorIoError) sensorConectado=false;
  }
  responder("STATUS:PROTOCOLO_2");
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
