# Carrinho com servo contínuo e eixo roscado — 4.16.0

Atualize ambos: `dist/SpectrumLabPro_4_16_0.exe` e o sketch da pasta `sketch_sep4a_copy_20261008183551`, também incluído em `dist/Firmware_ESP32_4_16_0.zip`.

## Ligações

| Componente | Ligação |
|---|---|
| Sinal do servo contínuo do carrinho | GPIO 19, mantido |
| Fim de curso do carrinho recuado | COM ao GND, NA ao GPIO 32 |
| Fim de curso do carrinho avançado/leitura | COM ao GND, NA ao GPIO 33 |

São cinco chaves no total. As da porta continuam em 25/26 e a da carcaça em 27. O servo da porta continua em 23 e o da gaveta em 18. Os negativos da fonte dos servos e do ESP32 compartilham GND. A alimentação dos servos continua na fonte externa apropriada.

## Controle do carrinho

O firmware não envia mais ângulos ao servo do carrinho. Em `CMD:AVANCAR_SENSOR`, gira até a chave de avanço e só então confirma `STATUS:SENSOR_AVANCADO`. Em `CMD:RECUAR_SENSOR`, gira até a chave de recuo e só então confirma `STATUS:SENSOR_RECUADO`. A leitura espectral exige que a chave de avanço permaneça acionada. A gaveta continua sendo o único servo posicional de 180°.

Pulsos iniciais configuráveis: parar 1500 µs, avançar 1300 µs, recuar 1700 µs. A montagem do servo e o sentido da rosca podem inverter os movimentos: conferir com o eixo desacoplado antes do primeiro percurso e inverter apenas SENSOR_AVANCAR_US/SENSOR_RECUAR_US se necessário. O neutro permanece 1500 µs, conforme teste informado pelo usuário.

A porta mantém os valores confirmados anteriormente: abrir 1100 µs, fechar 1900 µs e parar 1500 µs.

## Inicialização, emergência e rotinas

Ao ligar, porta e carrinho recebem somente neutro; não há recuo automático nem movimento da gaveta. A posição do carrinho vem das chaves, sem posição presumida. Se nenhuma chave estiver ativa, o painel mostra “entre posições”.

Nas rotinas automáticas, se não houver confirmação de recuo, primeiro recolhe o carrinho até a chave antes de abrir a porta/gaveta. O avanço continua exigindo porta e gaveta fechadas. A leitura só inicia após confirmação física de avanço; perder essa chave durante aquisição invalida a leitura. Perder o repouso durante movimento automático da porta/gaveta interrompe a operação.

O manual autenticado permanece independente e sem confirmação de amostra ou encadeamentos. Os próprios fins de curso do carrinho e da porta continuam limitando seus percursos. Duas chaves opostas ativas simultaneamente geram falha.

Porta e carrinho não têm limite de duração de percurso. Mantêm parada por emergência, carcaça sem autorização e perda de comunicação. Seis segundos sem comandos de manutenção da comunicação interrompem o movimento; o supervisório envia o heartbeat automaticamente. A emergência para os eixos, sem iniciar recolhimento automático.

## Primeiro teste após montar

1. Grave o sketch atualizado e abra o novo supervisório.
2. Com o carrinho desacoplado, confira o neutro e os sentidos no modo manual.
3. Verifique cada chave separadamente usando `CMD:ESTADO_CARRINHO` ou `CMD:ESTADO_PORTA`: o retorno inclui SENSOR_RECUADO e SENSOR_AVANCADO, 1 quando pressionado.
4. Confira parada por cada chave, saída do contato no sentido contrário e emergência.
5. Só depois acople o eixo e teste o percurso completo.

O firmware antigo de servo posicional não deve ser usado com o novo carrinho. O supervisório exige a capacidade `CARRINHO_PROTOCOLO_1` e os estados das novas chaves para liberar comandos.

Validação de software: 47 testes de controle/intertravamentos, 30 de regressão e 4 de adaptação de tela passaram com hardware simulado. Os painéis foram renderizados e conferidos visualmente. Não foi feita gravação na placa nem teste físico nesta revisão.

Compilação concluída para ESP32 3.3.12 / No OTA: 1.671.675 bytes de flash (79%) e 65.224 bytes de RAM estática (19%). Executável gerado, capacidade CARRINHO_PROTOCOLO_1 conferida no pacote e inicialização validada por 15 segundos com banco isolado.
