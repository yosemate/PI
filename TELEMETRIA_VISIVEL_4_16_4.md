# Telemetria visível durante operações — 4.16.4

Abra dist/SpectrumLabPro_4_16_4.exe. Não requer alteração de firmware.

O painel do sensor conserva os últimos valores recebidos quando a consulta de diagnóstico fica pausada durante movimentos e leituras. O aviso mostra atualização pausada e o tempo desde o diagnóstico. Em repouso, diagnósticos com mais de dez segundos são marcados como desatualizados, sem apagar os campos. Os valores são limpos na desconexão ou erro de diagnóstico, como anteriormente. Valores preservados não representam medições em tempo real.

A consulta de diagnóstico continua ocorrendo a cada cinco segundos quando a bancada está livre. A aquisição espectral, o heartbeat, os controles e os intertravamentos não foram modificados.

Validação: retenção de temperatura/ganho após vinte segundos, mensagens de pausa/desatualização e limpeza por desconexão conferidas em ambiente simulado. Trinta testes de estabilidade passaram.
