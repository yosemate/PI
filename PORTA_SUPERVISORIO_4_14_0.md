# SpectrumLabPro 4.14.0 — porta e carcaça

Use o executável `dist/SpectrumLabPro_4_14_0.exe` junto ao sketch atualizado da pasta `sketch_sep4a_copy_20261008183551`. O supervisório exige a identificação `PORTA_PROTOCOLO_1` e estados atuais dos três fins de curso. Firmware anterior permite conexão, mas não libera estas operações.

## Sequência das rotinas

1. Abre a porta e aguarda fim de curso de porta aberta e confirmação do ESP32.
2. Abre a gaveta e aguarda confirmação de movimento concluído.
3. Exibe o diálogo para posicionar amostra/referência. Cancelar mantém a gaveta aberta.
4. Após confirmação do operador, fecha a gaveta e aguarda confirmação do ESP32.
5. Fecha a porta e aguarda fim de curso de porta fechada e confirmação do ESP32.
6. Libera o avanço do sensor e a aquisição.
7. Para retirada, recua o sensor, abre a porta e depois a gaveta. O fechamento ao finalizar também exige confirmação do operador e fecha a porta após a gaveta.

Essa sequência vale para leitura simples, repetibilidade, branco/escuro e transições para nova amostra. Dados, médias, referência e repetibilidade permanecem sob os controles de integridade existentes.

## Controles manuais

O botão “Modo manual” mantém a autenticação por usuário e senha. O painel inclui “Abrir Porta” e “Fechar Porta”. Abrir a gaveta com porta fechada abre primeiro a porta e espera seu fim de curso. Fechar a gaveta exige confirmação de amostra posicionada ou berço vazio. Só depois a porta fecha. O avanço manual fica bloqueado até gaveta e porta fechadas.

A emergência para a porta e a gaveta sem iniciar fechamento automático; o recolhimento do sensor só ocorre com a carcaça fechada. Durante movimento ou espera por confirmação, os controles ficam bloqueados. Falha ou emergência descarta continuações pendentes; uma resposta atrasada não retoma a rotina.

## Carcaça

O quadro no painel principal e no painel manual mostra a chave da carcaça: fechada, aberta ou sem confirmação. A chave NA está pressionada com a carcaça fechada, ligada entre GPIO 27 e GND.

Ao iniciar uma operação com carcaça aberta, há uma nova autenticação mesmo que o modo manual já tenha sido liberado. Nenhum movimento segue até o ESP32 confirmar a autorização. Ela vale para aquela operação/rotina e termina na conclusão, cancelamento, logout, emergência ou desconexão. O supervisório renova a autorização durante a rotina; o ESP32 a expira após seis segundos sem renovação, também verificando a conexão Bluetooth/TCP. Fechar a carcaça devolve a operação ao intertravamento normal. Abri-la durante uma operação interrompe a rotina; é necessário iniciar novamente e autenticar.

As credenciais são validadas no banco do supervisório e não são enviadas ao ESP32. O protocolo local confia no supervisório autenticado e vincula a autorização ao transporte USB/Bluetooth/TCP de origem; ele não implementa autenticação criptográfica de clientes que enviem comandos diretamente.

## Pinos e limites físicos

| Ligação | GPIO |
|---|---:|
| Servo da gaveta | 18 |
| Servo do carrinho | 19 |
| Servo contínuo da porta | 23 |
| Porta aberta: COM ao GND, NA ao GPIO | 25 |
| Porta fechada: COM ao GND, NA ao GPIO | 26 |
| Carcaça fechada: COM ao GND, NA ao GPIO | 27 |

Ângulos dos dois servos de posição mantidos. Calibrar os pulsos do servo contínuo no sketch: neutro inicial 1500 µs, abrir 1600 µs, fechar 1400 µs; são valores provisórios. O timeout de porta é de dez segundos.

Não há fim de curso na gaveta: “gaveta fechada” significa conclusão do comando ao servo, sem confirmação de obstrução ou posição física real. Na inicialização, o firmware não fecha automaticamente gaveta nem porta; aguarda comandos intertravados. Após interrupção, conferir as posições na bancada.

## Antes de usar

1. Grave o sketch atualizado no ESP32 (partição No OTA para a configuração existente de 4 MB).
2. Calibre neutro e sentidos com a porta desacoplada.
3. Confirme a leitura de cada chave pelo comando `CMD:ESTADO_PORTA`.
4. Abra o novo executável e confira o quadro da carcaça.
5. Teste cancelamento da confirmação de amostra, os dois limites da porta, timeout, emergência e autenticação com carcaça aberta antes de iniciar medições.

Os arquivos anteriores foram preservados em `backups/20261014_porta/`. Não foi feita gravação na placa nem validação física.

## Validação desta revisão

30 testes de regressão, 23 de intertravamentos e 4 de adaptação de tela passaram com comunicação e hardware simulados. Firmware compilado para ESP32 3.3.12 / No OTA: 1.669.783 bytes de flash (79%) e 65.184 bytes de RAM estática (19%). A interface foi renderizada para conferir o quadro da carcaça e os botões da porta.

O novo executável foi gerado e iniciou por 15 segundos com banco isolado, sem erro de inicialização. O pacote foi inspecionado para confirmar que contém o código final de intertravamento.
