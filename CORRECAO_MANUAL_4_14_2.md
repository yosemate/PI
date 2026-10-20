# Teste de atuadores sem sensor espectral — 4.14.2

O relato de ABRINDO_PORTA seguido por EMERGENCIA_ACIONADA após aproximadamente um segundo foi explicado por uma condição ainda incorreta do supervisório 4.14.1: o SENSOR_ERRO do heartbeat provocava parada durante qualquer comando manual pendente, mesmo que fosse apenas movimento mecânico.

A versão 4.14.2 só interrompe por SENSOR_ERRO uma operação que precisa do sensor espectral (aquisição, calibração, ensaio automático). Comandos manuais de porta, gaveta e carrinho continuam funcionando com o sensor espectral desconectado. O servo contínuo segue o comando de giro até seu fim de curso, emergência, intertravamento ou timeout do firmware.

Use `dist/SpectrumLabPro_4_14_2.exe` com o firmware 4.14.1. Nenhuma alteração de firmware foi necessária nesta correção. Feche o supervisório anterior antes de abrir a nova versão.

O fechamento da porta exige fechamento confirmado da gaveta. Para testar, abra a porta, confirme a chave de porta aberta, abra/feche a gaveta pelo painel e confirme a posição da amostra ou berço vazio. Após GAVETA_FECHADA, a porta fecha automaticamente até sua chave. Pedir fechamento da porta antes disso mostra o motivo no console do painel manual. As falhas também são registradas nesse console.

Os fins de curso e a autenticação da carcaça aberta permanecem ativos. O timeout da porta continua em dez segundos. Os valores de giro e neutro do servo continuam configuráveis no sketch; não foram alterados sem identificação do modelo.

Validação: 29 testes de intertravamentos, incluindo SENSOR_ERRO recebido durante movimento manual da porta, da gaveta e durante espera de porta aberta; 30 testes de regressão. Hardware simulado; não foi feito teste físico.
