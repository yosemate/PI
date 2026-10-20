# Porta sem limite de duração — 4.14.3

Use `dist/SpectrumLabPro_4_14_3.exe` com o sketch atualizado ou o pacote `dist/Firmware_ESP32_4_14_3.zip`. Feche o supervisório anterior antes de abrir a nova versão e grave o sketch no ESP32 antes de retomar os testes.

O giro da porta não tem mais limite de duração no firmware nem no supervisório. O comando permanece ativo até a chave do destino ser acionada. A confirmação exige estabilidade de 30 ms, e a parada é enviada no primeiro contato da chave.

As paradas por emergência, carcaça sem autorização, chaves contraditórias e perda de comunicação permanecem ativas. O heartbeat continua obrigatório enquanto a porta gira; seis segundos sem comandos interrompem o movimento. Esse prazo monitora a comunicação, não a duração do percurso. Ao usar o Monitor Serial diretamente, é necessário manter o heartbeat; o supervisório o envia automaticamente.

Velocidade e sentidos confirmados na bancada mantidos:

| Comando | Pulso |
|---|---:|
| Abrir porta | 1400 µs |
| Fechar porta | 1600 µs |
| Parar | 1500 µs |

O fechamento da porta exige gaveta fechada e confirmada. Abrir a gaveta exige porta aberta confirmada. Gaveta só fecha depois da confirmação do operador; sensor só avança depois de gaveta e porta fechadas. Os prazos dos servos posicionais e da aquisição permanecem ativos.

Os testes manuais dos atuadores permitem sensor espectral desconectado; leituras e calibrações continuam bloqueadas nessa situação. Autenticação do painel manual e da operação com carcaça aberta permanece igual.

| Ligação | GPIO |
|---|---:|
| Servo da gaveta | 18 |
| Servo do carrinho | 19 |
| Servo contínuo da porta | 23 |
| Fim de curso de porta aberta | 25 |
| Fim de curso de porta fechada | 26 |
| Fim de curso de carcaça fechada | 27 |

Fins de curso NA entre GPIO e GND. A chave da carcaça permanece pressionada com a carcaça fechada. Gaveta e carrinho continuam com servos posicionais de 180°, sem fins de curso próprios, confirmados pelo término do movimento comandado.

Validação: 32 testes de intertravamentos e 30 de regressão passaram com hardware simulado. Não foi feita gravação na placa nem teste físico desta revisão. A estrutura física da porta será ajustada pelo usuário antes de retomar os testes.
