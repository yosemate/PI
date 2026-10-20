#include <Wire.h>
#include <Adafruit_AS726x.h>
#include <ESP32Servo.h>
#include <WiFi.h>
#include "BluetoothSerial.h"

// -------------------------------------------------------------------
// INSTÂNCIAS DE COMUNICAÇÃO
// -------------------------------------------------------------------
BluetoothSerial SerialBT;
WiFiServer tcpServer(8080);
WiFiClient tcpClient;

// -------------------------------------------------------------------
// INSTÂNCIAS DE HARDWARE
// -------------------------------------------------------------------
Servo servoGaveta;
Servo servoCarrinho;
Adafruit_AS726x sensor;

// Mapeamento de Pinos
const int PINO_SERVO_GAVETA   = 18;
const int PINO_SERVO_CARRINHO = 19;
const int PINO_SDA            = 21;
const int PINO_SCL            = 22;

// Limites Angulares Mecânicos
const int GAVETA_FECHADA   = 5;   
const int GAVETA_ABERTA    = 175;
const int CARRINHO_RECUADO = 180;
const int CARRINHO_LEITURA = 5;

// Parâmetros Nominais de Operação Óptica
const uint8_t GANHO_CONFIG      = GAIN_64X;
const uint8_t INTEGRACAO_CONFIG = 50;           // 50 * 2.8ms = 140ms
const uint8_t CORRENTE_LED      = LIMIT_50MA;   // 50mA

// Rastreamento Dinâmico de Posição
int posAtualGaveta   = GAVETA_FECHADA;
int posAtualCarrinho = CARRINHO_RECUADO;

bool sensorConectado = false;
volatile bool abortarMovimento = false;
uint16_t bufferCanais[AS726x_NUM_CHANNELS];
float bufferCalibrado[AS726x_NUM_CHANNELS];

// -------------------------------------------------------------------
// ENVIO UNIFICADO DE MENSAGENS (BROADCAST)
// -------------------------------------------------------------------
void responder(String msg) {
  Serial.println(msg);
  if (SerialBT.hasClient()) SerialBT.println(msg);
  if (tcpClient && tcpClient.connected()) tcpClient.println(msg);
}

// -------------------------------------------------------------------
// TELEMETRIA E DIAGNÓSTICO DO SENSOR AS7263
// -------------------------------------------------------------------
void enviarDiagnosticoSensor() {
  if (!sensorConectado) {
    responder("DIAG:TEMP:0|GAIN:OFF|INT:0|LED:OFF|HW:DESCONECTADO|STATUS:ERRO");
    return;
  }

  // Leitura da temperatura interna integrada no chip (graus Celsius)
  uint8_t tempC = sensor.readTemperature();

  // Montagem da linha estruturada de telemetria
  String diag = "DIAG:";
  diag += "TEMP:" + String(tempC) + "|";
  diag += "GAIN:64x|";
  diag += "INT:140.0ms|";
  diag += "LED:50mA|";
  diag += "HW:AS7263_NIR|";
  diag += "STATUS:READY";

  responder(diag);
}

// -------------------------------------------------------------------
// VERIFICAÇÃO INSTANTÂNEA DE COMANDO DE EMERGÊNCIA DURANTE RAMPA
// -------------------------------------------------------------------
bool checarInterrupcaoEmergencia() {
  if (Serial.available()) {
    String c = Serial.readStringUntil('\n');
    c.trim();
    if (c.indexOf("EMERGENCIA") >= 0) { 
      abortarMovimento = true; 
      return true; 
    }
  }
  if (SerialBT.available()) {
    String c = SerialBT.readStringUntil('\n');
    c.trim();
    if (c.indexOf("EMERGENCIA") >= 0) { 
      abortarMovimento = true; 
      return true; 
    }
  }
  if (tcpClient && tcpClient.connected() && tcpClient.available()) {
    String c = tcpClient.readStringUntil('\n');
    c.trim();
    if (c.indexOf("EMERGENCIA") >= 0) { 
      abortarMovimento = true; 
      return true; 
    }
  }
  return false;
}

// -------------------------------------------------------------------
// MOVIMENTAÇÃO SUAVE (RAMPA GRAU A GRAU)
// -------------------------------------------------------------------
void moverPara(Servo &s, int pino, int &posAtual, int posDestino, int passoDelay = 15, bool monitorarEmergencia = false) {
  if (posAtual == posDestino) return;

  s.attach(pino, 500, 2400);

  if (posDestino > posAtual) {
    for (int a = posAtual; a <= posDestino; a++) {
      if (monitorarEmergencia && checarInterrupcaoEmergencia()) {
        posAtual = a;
        break; // Interrompe na posição exata para evitar colisão
      }
      s.write(a);
      delay(passoDelay);
      posAtual = a;
    }
  } else {
    for (int a = posAtual; a >= posDestino; a--) {
      if (monitorarEmergencia && checarInterrupcaoEmergencia()) {
        posAtual = a;
        break;
      }
      s.write(a);
      delay(passoDelay);
      posAtual = a;
    }
  }

  s.write(posAtual);
  delay(80);
  s.detach(); // Desliga o sinal PWM para eliminar ruído, aquecimento e vibração
}

// -------------------------------------------------------------------
// ROTINAS DE SEGURANÇA E MOVIMENTAÇÃO MECÂNICA
// -------------------------------------------------------------------
void paradaEmergencia() {
  abortarMovimento = true;

  // 1. Corta imediatamente o emissor óptico NIR
  if (sensorConectado) sensor.drvOff();

  // 2. RECUA O SENSOR PRIMEIRO para evitar colisão com a gaveta
  if (posAtualCarrinho != CARRINHO_RECUADO) {
    moverPara(servoCarrinho, PINO_SERVO_CARRINHO, posAtualCarrinho, CARRINHO_RECUADO, 12, false);
  }

  // 3. FECHA A GAVETA DEPOIS
  if (posAtualGaveta != GAVETA_FECHADA) {
    moverPara(servoGaveta, PINO_SERVO_GAVETA, posAtualGaveta, GAVETA_FECHADA, 14, false);
  }

  abortarMovimento = false;
  responder("STATUS:EMERGENCIA_ACIONADA");
}

void abrirGaveta() {
  responder("STATUS:ABRINDO_GAVETA");
  moverPara(servoGaveta, PINO_SERVO_GAVETA, posAtualGaveta, GAVETA_ABERTA, 18, true);
  responder("STATUS:GAVETA_ABERTA");
}

void fecharGaveta() {
  responder("STATUS:FECHANDO_GAVETA");
  moverPara(servoGaveta, PINO_SERVO_GAVETA, posAtualGaveta, GAVETA_FECHADA, 18, true);
  responder("STATUS:GAVETA_FECHADA");
}

void avancarSensor() {
  responder("STATUS:POSICIONANDO_SENSOR");
  moverPara(servoCarrinho, PINO_SERVO_CARRINHO, posAtualCarrinho, CARRINHO_LEITURA, 15, true);
  
  if (abortarMovimento) {
    paradaEmergencia();
    return;
  }
  responder("STATUS:SENSOR_AVANCADO");
}

void recuarSensor() {
  responder("STATUS:RECUANDO_SENSOR");
  moverPara(servoCarrinho, PINO_SERVO_CARRINHO, posAtualCarrinho, CARRINHO_RECUADO, 15, false);
  responder("STATUS:SENSOR_RECUADO");
}

void realizarLeituraEspectral() {
  if (sensorConectado) {
    // 1. Liga o LED NIR de excitação
    sensor.drvOn();
    delay(150); // Estabilização térmica e óptica do feixe

    sensor.startMeasurement();
    
    // 2. Aguarda conclusão da integração espectral (timeout de segurança: 1000ms)
    unsigned long timeout = millis();
    while (!sensor.dataReady() && (millis() - timeout < 1000)) { 
      delay(5); 
    }

    // 3. Coleta os valores brutos de contagem ADC
    sensor.readRawValues(bufferCanais);
    
    // 4. Desliga o emissor óptico para evitar aquecimento na câmara
    sensor.drvOff();

    // 5. Envia o pacote DATA compatível com o supervisório atual
    String payload = "DATA:";
    for (int i = 0; i < 6; i++) {
      payload += String(bufferCanais[i]);
      if (i < 5) payload += ",";
    }
    responder(payload);

    // 6. Envia automaticamente a linha de diagnóstico do sensor
    enviarDiagnosticoSensor();

  } else {
    responder("DATA:0,0,0,0,0,0");
  }
  responder("STATUS:LEITURA_CONCLUIDA");
}

void realizarLeituraCalibrada() {
  if (sensorConectado) {
    sensor.drvOn();
    delay(150);

    sensor.startMeasurement();
    unsigned long timeout = millis();
    while (!sensor.dataReady() && (millis() - timeout < 1000)) { 
      delay(5); 
    }

    sensor.readCalibratedValues(bufferCalibrado);
    sensor.drvOff();

    String payload = "CAL_DATA:";
    for (int i = 0; i < 6; i++) {
      payload += String(bufferCalibrado[i], 2);
      if (i < 5) payload += ",";
    }
    responder(payload);
  } else {
    responder("CAL_DATA:0,0,0,0,0,0");
  }
}

// -------------------------------------------------------------------
// PROCESSADOR CENTRAL DE COMANDOS
// -------------------------------------------------------------------
void processarComando(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd == "CMD:PING" || cmd == "PING") {
    responder("STATUS:PONG");
  } else if (cmd.indexOf("EMERGENCIA") >= 0) {
    paradaEmergencia();
  } else if (cmd == "CMD:ABRIR_GAVETA") {
    abrirGaveta();
  } else if (cmd == "CMD:FECHAR_GAVETA") {
    fecharGaveta();
  } else if (cmd == "CMD:AVANCAR_SENSOR") {
    avancarSensor();
  } else if (cmd == "CMD:RECUAR_SENSOR") {
    recuarSensor();
  } else if (cmd == "CMD:LER_ESPECTRO") {
    realizarLeituraEspectral();
  } else if (cmd == "CMD:DIAG_SENSOR") {
    enviarDiagnosticoSensor();
  } else if (cmd == "CMD:LER_CALIBRADO") {
    realizarLeituraCalibrada();
  }
}

// -------------------------------------------------------------------
// SETUP
// -------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(50);
  SerialBT.begin("Bancada_NIR_ESP32");
  SerialBT.setTimeout(50);
  WiFi.softAP("Bancada_NIR_AP");
  tcpServer.begin();

  Wire.begin(PINO_SDA, PINO_SCL);
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  servoGaveta.setPeriodHertz(50);
  servoCarrinho.setPeriodHertz(50);

  // Posição inicial estável no boot
  posAtualGaveta   = GAVETA_FECHADA;
  posAtualCarrinho = CARRINHO_RECUADO;

  servoCarrinho.attach(PINO_SERVO_CARRINHO, 500, 2400);
  servoCarrinho.write(CARRINHO_RECUADO);
  servoGaveta.attach(PINO_SERVO_GAVETA, 500, 2400);
  servoGaveta.write(GAVETA_FECHADA);

  delay(250);
  servoCarrinho.detach();
  servoGaveta.detach();

  if (sensor.begin()) {
    sensorConectado = true;
    
    // Configurações do AS7263
    sensor.setGain(GANHO_CONFIG);               // 64x
    sensor.setIntegrationTime(INTEGRACAO_CONFIG); // 140ms
    sensor.setDrvCurrent(CORRENTE_LED);           // 50mA
    sensor.setConversionType(MODE_2);             // Modo de 6 canais completos
    sensor.drvOff();                             // Mantém LED desligado
    
    responder("STATUS:SENSOR_OK");
    enviarDiagnosticoSensor();                   // Envia estado inicial no boot
  } else {
    sensorConectado = false;
    responder("STATUS:SENSOR_ERRO");
  }
}

// -------------------------------------------------------------------
// LOOP PRINCIPAL
// -------------------------------------------------------------------
void loop() {
  if (Serial.available()) {
    processarComando(Serial.readStringUntil('\n'));
  }

  if (SerialBT.available()) {
    processarComando(SerialBT.readStringUntil('\n'));
  }

  if (tcpServer.hasClient()) {
    WiFiClient novoCliente = tcpServer.available();
    if (!tcpClient || !tcpClient.connected()) {
      if (tcpClient) tcpClient.stop();
      tcpClient = novoCliente;
      tcpClient.setTimeout(50);
    } else {
      novoCliente.stop();
    }
  }

  if (tcpClient && tcpClient.connected()) {
    if (tcpClient.available()) {
      processarComando(tcpClient.readStringUntil('\n'));
    }
  } else if (tcpClient) {
    tcpClient.stop();
  }
}