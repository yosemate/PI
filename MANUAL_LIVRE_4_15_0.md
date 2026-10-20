# Manual independente e porta mais rápida — 4.15.0

Use `dist/SpectrumLabPro_4_15_0.exe` junto ao sketch atualizado ou `dist/Firmware_ESP32_4_15_0.zip`. É necessário atualizar ambos: esta revisão introduz `MANUAL_PROTOCOLO_1` e comandos de movimento `CMD:MANUAL:...`.

## Modo manual autenticado

Após usuário e senha, cada botão movimenta somente seu próprio atuador:

- Abrir/fechar porta não exige gaveta fechada nem carrinho recuado.
- Abrir/fechar gaveta não exige porta aberta nem carrinho recuado.
- Fechar gaveta não pede confirmação de amostra e não fecha a porta depois.
- Avançar/recuar sensor não exige posições dos outros atuadores.
- Não há encadeamento automático desses comandos nem diálogos de posicionamento de amostra no manual.

Um movimento é executado por vez, com confirmação de conclusão do ESP32. O operador controla a ordem das ações no modo manual. O logout durante um movimento manual envia emergência e bloqueia o painel.

Continuam ativos: fins de curso de abertura/fechamento da própria porta, detecção de chaves contraditórias, emergência, proteção por perda de comunicação e autenticação de operação com carcaça aberta. Leituras ópticas continuam exigindo sensor espectral, calibração e câmara fechada; o teste manual dos atuadores funciona sem sensor espectral conectado.

## Rotinas automáticas

As confirmações e os intertravamentos anteriores continuam ativos: porta aberta antes de abrir gaveta, confirmação do operador antes de fechar gaveta, porta e gaveta fechadas antes de avançar o sensor. Os comandos automáticos não recebem a liberação manual.

## Velocidade da porta

Comando ajustado para 400 µs de diferença em relação ao neutro, mantendo os sentidos confirmados:

| Comando | Pulso |
|---|---:|
| Abrir | 1100 µs |
| Fechar | 1900 µs |
| Parar | 1500 µs |

O ganho real de velocidade depende do servo e da carga; não se presume velocidade em dobro. O movimento permanece sem limite de duração de percurso e para no fim de curso do destino. Seis segundos sem comunicação continuam provocando parada.

Os GPIOs e ângulos dos dois servos posicionais permanecem iguais. Porta: sinal 23, fim de curso aberta 25, fechada 26, carcaça fechada 27. Contatos NA entre GPIO e GND; carcaça pressiona a chave quando fechada.

Não foi feita gravação na placa nem teste físico nesta revisão. Os arquivos anteriores e os executáveis anteriores foram preservados.

Validação final: 37 testes de intertravamentos/modo manual e 30 de regressão passaram. Firmware compilado: 1.670.391 bytes de flash (79%) e 65.192 bytes de RAM estática (19%). O executável iniciou por 15 segundos com banco isolado, e o pacote contém a capacidade MANUAL_PROTOCOLO_1.

Ajuste de 16/10/2026: comando da porta aumentado de 1300/1700 para 1100/1900 µs, mantendo neutro de 1500 µs, sentidos, fins de curso e movimento sem limite de duração. Conferir a velocidade real na bancada.
