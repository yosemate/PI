# Porta e carcaça — ESP32

Mantidos: servo da gaveta GPIO 18, servo do carrinho GPIO 19, I2C 21/22 e os ângulos existentes.

| Ligação | GPIO |
|---|---:|
| Sinal do servo contínuo da porta | 23 |
| Fim de curso da porta aberta | 25 |
| Fim de curso da porta fechada | 26 |
| Fim de curso da carcaça fechada | 27 |

Em cada fim de curso, ligar COM ao GND e NA ao GPIO. O firmware usa INPUT_PULLUP; contato pressionado é LOW. O da carcaça deve permanecer pressionado com a carcaça fechada. Não aplicar 5 V aos GPIOs. Alimentar os servos por fonte adequada, com GND comum ao ESP32.

## Calibração antes de acoplar a porta

Com o mecanismo desacoplado e a carcaça fechada, ajustar PORTA_PARAR_US (inicialmente 1500) até o servo parar. Os valores iniciais PORTA_ABRIR_US=1600 e PORTA_FECHAR_US=1400 são provisórios: inverter se o sentido estiver errado e ajustar a velocidade. PORTA_TIMEOUT_MS=10000 limita cada comando a 10 segundos. Ajustar ao percurso real.

A parada mantém o pulso de neutro. Desligar o sinal ou detach não substitui a calibração do neutro, nem representa corte de alimentação.

## Comandos no monitor serial (115200, final de linha)

- CMD:ESTADO_PORTA: informa os três contatos, 1=pressionado.
- CMD:ABRIR_PORTA: abre até o contato de porta aberta.
- CMD:FECHAR_PORTA: fecha até o contato de porta fechada.
- CMD:EMERGENCIA: para a porta e executa o recolhimento já existente, somente com a carcaça fechada.

Os comandos também estão disponíveis por Bluetooth e TCP. A interface do computador ainda não foi alterada. Não há fechamento automático da porta ao receber os comandos antigos.

A porta só se movimenta com o carrinho recuado. Avançar o sensor e iniciar leituras exige porta fechada. Abrir a carcaça interrompe movimentos e leitura, desliga o LED e bloqueia novos comandos de movimento. Abrir a porta durante leitura aborta a aquisição. Fechar a carcaça não retoma o movimento interrompido.

Os contatos têm confirmação de estabilidade de 30 ms; a porta para no primeiro contato bruto do destino. Dois contatos da porta pressionados simultaneamente geram falha. Sem chegada ao destino, a porta para por timeout.

## Verificação na bancada

1. Conferir CMD:ESTADO_PORTA pressionando cada contato separadamente.
2. Calibrar neutro e sentidos com o mecanismo desacoplado.
3. Testar abertura e fechamento: cada contato deve parar o sentido correspondente; é possível sair do contato no sentido contrário.
4. Testar parada por timeout sem pressionar o contato de destino.
5. Testar emergência durante movimento e abertura da carcaça durante movimento e leitura.
6. Confirmar bloqueio de avanço/leitura com a porta aberta e recuperação apenas por novo comando.

Os dois servos de posição continuam sem confirmação física. Após interrupção, a posição estimada pode não corresponder à posição mecânica: verificar a bancada antes de retomar. O contato NA da carcaça permite bloquear também se seu fio abrir, mas curto ao GND pode simular carcaça fechada. Este intertravamento por software não corta eletricamente a alimentação dos servos.

O arquivo .before_door.bak preserva o firmware anterior. Não foi feita gravação na placa nem teste físico.
