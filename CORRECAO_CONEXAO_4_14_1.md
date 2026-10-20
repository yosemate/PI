# Correção de conexão — 4.14.1

O código anterior podia descartar PONG enquanto estava em FALHA/EMERGENCIA e enviar emergências repetidas ao receber SENSOR_ERRO. Isso podia gerar comandos repetidos de recolhimento e desconexão por timeout, mesmo com o ESP32 respondendo.

A versão 4.14.1 aceita PONG em todos os estados, mantém a conexão quando o sensor espectral está indisponível em repouso e interrompe apenas uma vez uma operação ativa que perde o sensor. O firmware não reenvia movimento de recolhimento se a posição estimada do carrinho já é a posição recuada.

Use `dist/SpectrumLabPro_4_14_1.exe` com o sketch atualizado. O pacote `dist/Firmware_ESP32_4_14_1.zip` inclui esse sketch e os drivers locais. A versão 4.14.0 foi preservada.

O sensor ainda recebe um comando de recuo uma vez ao ligar, com a carcaça fechada, conforme a sequência de inicialização já informada. Movimento repetido após reinicializações do ESP32 ainda precisa de diagnóstico físico; esta correção não elimina problemas de alimentação.

O negativo da fonte dos servos deve compartilhar GND com o ESP32. Os positivos dos servos devem receber a tensão correta da fonte externa; a corrente dos servos deve voltar diretamente ao negativo dessa fonte.

Teste primeiro a conexão USB com os servos sem alimentação. Feche o Monitor Serial antes de conectar o supervisório. Se ocorrer desconexão, copie as últimas linhas do Console de telemetria. Se aparecer SENSOR_ERRO, verificar AS7263 e I2C (SDA 21, SCL 22). Se houver mensagens de boot repetidas ou brownout, investigar alimentação, cabos e conexões.

Não foi feita gravação nem teste físico. As alterações passaram em 26 testes de intertravamentos e 30 testes de regressão com hardware simulado.

O sensor espectral pode permanecer desconectado durante testes das partes móveis. Nesse caso, a conexão USB e os controles manuais autenticados permanecem disponíveis; leitura e calibração não são liberadas. O watchdog do firmware executa apenas uma parada por perda de comunicação, até chegar um novo comando.
