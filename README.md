# SpectrumLabPro 4.11.1 — bancada demonstrativa de TCC

Esta versão corrige integridade de calibração, aquisição e comunicação. O Kappa continua sendo uma estimativa demonstrativa por equações fixas, sem treinamento ou validação analítica. Uma referência branca melhor não valida o modelo de Kappa.

## Como colocar em uso

1. Abra o sketch atualizado na segunda pasta de trabalho, mantendo a subpasta src/ junto dele, e envie-o à mesma placa ESP32 usada pela bancada. Para ESP32 com 4 MB de flash, selecione a partição No OTA (2MB APP/2MB SPIFFS); a partição padrão de 1,3 MB não comporta as três conexões. Confirme a capacidade da sua placa antes de gravar. Os pinos, ângulos, ganho 64x, integração nominal de 140 ms e corrente de LED de 50 mA foram mantidos. A aquisição dos seis canais em one-shot pode consumir dois períodos de integração.
2. Execute dist/SpectrumLabPro_4_11_1.exe. O executável anterior foi preservado.
3. Conecte a bancada. O supervisório exige a identificação PROTOCOLO_2 e um sensor disponível; firmware antigo permite conectar mas não medir.
4. No modo seco, use o mesmo cartão branco fosco, mesma face, plano e distância da amostra. Evite marcas, transparência do suporte e entrada de luz externa.
5. Inicie a calibração. São feitas dez aquisições do branco e depois dez aquisições de escuro com LED desligado e gaveta fechada. Retire o cartão quando o assistente solicitar.
6. Complete ambas as etapas. Cancelar após o branco descarta a tentativa inteira e preserva a referência anterior.
7. Faça o primeiro ensaio e o teste de repetibilidade. Confirme na bancada o funcionamento dos movimentos e da emergência antes de uma sessão completa.

A pintura preta permanece como parte da câmara. Ela não é usada como substituto da leitura de escuro do detector. O cartão define a referência de trabalho, sem certificação de refletância; os resultados são relativos a ele. Para modo úmido, mantenha o mesmo suporte/solvente na referência, mas a geometria e a interpretação analítica precisam de avaliação experimental.

## O que mudou

- Perfis começam não calibrados. Dados antigos são preservados, mas não passam automaticamente como referências medidas pelo procedimento novo.
- Pacotes ópticos possuem identificadores únicos. Dados antigos, duplicados ou conclusões sem pacote novo são descartados.
- Leituras comuns usam a média de cinco aquisições no mesmo posicionamento, com intervalo de 300 ms entre solicitações. Isso reduz parte do ruído aleatório; não garante ausência de deriva.
- Repetibilidade mantém cinco aquisições individuais, sem movimentações intermediárias. Os valores individuais ficam no histórico.
- Calibração só se torna válida depois de validar referências e confirmar a gravação atômica.
- R² e RMSE fixos foram retirados. O cartão de calibração mostra CV máximo do branco, ruído máximo do escuro e quantidade de aquisições.
- Vetores completos, estatísticas, aquisições individuais, configurações, operador e identificador de cada nova calibração ficam no histórico do JSON.
- Cada nova leitura guarda uma cópia da referência usada e as aquisições brutas. Leituras antigas não ganham metadados que não existiam.
- Mudança de modo não reprocessa nem registra a amostra antiga como um novo ensaio.
- A escala de entrada do modelo seco é explicitamente uma fração, eliminando a mudança de unidade ao ultrapassar 1.0.
- O fundo e a resposta corrigida não são convertidos silenciosamente em zeros para gerar Kappa.
- Controles permanecem bloqueados enquanto existe rotina, aquisição, comando manual ou emergência não confirmada.
- Heartbeat monitora comunicação; o firmware recolhe a bancada após perda prolongada dos comandos.
- O firmware trata emergência durante movimentos e aquisição, não envia confirmação de posição após movimento interrompido e rejeita movimentos incompatíveis com a posição estimada.
- Driver Adafruit local em src/ do sketch tem limites de espera e verificação de falha I2C. Bibliotecas instaladas globalmente não foram alteradas.

## Limites operacionais iniciais

Os limites abaixo são parâmetros de engenharia para este protótipo, não critérios metrológicos certificados. Devem ser revistos com ensaios físicos:

- ADC: seis números finitos, não negativos e abaixo de 65500.
- Branco: CV máximo de 5% por canal.
- Branco menos escuro: maior que 10 contagens e maior que cinco vezes o ruído combinado das referências.
- Amostra menos escuro: maior que duas contagens e maior que três vezes o desvio do escuro em todos os canais; sinal insuficiente pede repetir ou ajustar a montagem.
- Prazo operacional da referência: configurável até 24 horas. Trocar iluminação, geometria, referência ou configurações exige nova calibração, mesmo dentro do prazo.
- Resposta relativa acima de 100% não é cortada: uma amostra pode devolver mais sinal que o cartão.
- Os servos não têm confirmação física de posição. Os intertravamentos utilizam posições estimadas pelos comandos. A sequência de emergência faz recolhimento controlado; não constitui corte elétrico certificado.

## Arquivos e preservação

Código canônico: arquivos da pasta principal. A entrada spectrum_lab/main.py encaminha para ela.

Executável anterior: dist/SpectrumLabPro.exe.
Novo executável: dist/SpectrumLabPro_4_11_1.exe. A versão 4.10.0 também foi preservada.

O executável guarda a calibração em %LOCALAPPDATA%/SpectrumLabPro/calibracao.json, evitando a pasta temporária do PyInstaller. O banco do executável continua ao lado do executável, preservando o histórico em dist/usuarios.db. Ao executar o código Python, os arquivos ficam na pasta principal. Para testes, SPECTRUM_LAB_DATA_DIR permite uma pasta isolada.

Originais, calibrações e cópias consistentes dos bancos: backups/20261008_estabilidade/.

## Verificação

Execute python -B tests/test_stability_regression.py. A suíte de 30 testes passou em 08/10/2026. O executável foi gerado e permaneceu ativo em teste de inicialização isolado por 15 segundos, sem erro registrado.
Os testes usam hardware simulado e diretórios temporários. Não escrever nos arquivos reais de calibração durante testes. Os antigos scripts de teste encaminham à suíte isolada.

Compilar o supervisório: python -m PyInstaller --noconfirm SpectrumLabPro_4_11_1.spec.

Firmware compilado com sucesso: esp32:esp32:esp32:PartitionScheme=no_ota, core ESP32 3.3.12. Uso de flash: 1.665.459 bytes (79% do aplicativo de 2 MB); RAM estática: 65.056 bytes (19%). O pacote dist/Firmware_ESP32_4_10_0.zip contém o sketch e o driver local necessários. Não foi feito upload à placa nem ensaio físico nesta revisão.

A compilação e os testes de software não substituem ensaios na bancada. Após trocar o procedimento de referência, os valores demonstrativos podem mudar; não ajustar coeficientes apenas para recuperar resultados anteriores.

A documentação técnica antiga descreve versões anteriores. Este documento prevalece quanto aos fluxos corrigidos.

## Interface com escala proporcional — versão 4.11.1

O painel mantém uma única disposição. A área de referência é de 1600×900 unidades lógicas, ampliada apenas se algum conteúdo exigir um mínimo maior. A janela calcula automaticamente um único fator a partir da largura e da altura disponíveis e transforma todo o painel, incluindo textos, botões, gráficos, KPIs, espaçamentos e regiões de clique. Não há rolagem do painel nem empilhamento dos cards em telas pequenas.

Os quatro KPIs permanecem na mesma linha e os controles e gráficos continuam lado a lado. A proporção original é preservada; telas de outra proporção podem deixar pequenas margens. Quanto menor a área disponível, menores ficam também os textos e botões. A escala nativa do Windows é aplicada pelo Qt; o ajuste adicional usa unidades lógicas e não duplica o DPI.

A escala se atualiza ao redimensionar a janela, trocar de monitor ou alterar a área útil. Diálogos maiores que a tela também são reduzidos proporcionalmente. Históricos e listas conservam os controles próprios de navegação dos dados.

Verificação: python -B tests/test_responsive_interface.py. Quatro testes verificam o painel inteiro visível em sete tamanhos (480×320 a 1920×1080), manutenção da disposição e do resultado, cliques após transformação, ajuste ao monitor menor e diálogos sem rolagem do formulário. Escalas de 100%, 125% e 150% foram verificadas em ambiente simulado. Os 30 testes funcionais também passaram. Não foi acessado o notebook físico.

Imagens atuais: validation/interface_4_11_1_1366.png e validation/interface_4_11_1_911.png. As imagens 4.11.0 registram a proposta anterior com reorganização e rolagem, substituída a pedido do usuário. Cópias anteriores desta revisão: backups/20261008_escala_proporcional/.

A transformação e o encaminhamento de eventos usam QGraphicsProxyWidget do Qt: https://doc.qt.io/archives/qt-5.15/qgraphicsproxywidget.html.


## Porta e carcaça — versão 4.14.0

A versão com servo contínuo de porta e três fins de curso está descrita em [PORTA_SUPERVISORIO_4_14_0.md](PORTA_SUPERVISORIO_4_14_0.md). Use `dist/SpectrumLabPro_4_14_0.exe` com o sketch atualizado. A porta deve confirmar abertura antes da gaveta, e fechamento antes do avanço do sensor. Gaveta e carrinho mantêm seus servos de posição de 180°, com confirmação por movimento concluído. O quadro da carcaça exige nova autenticação para operação com equipamento aberto.


## Carrinho contínuo — versão 4.16.0

A adaptação para eixo roscado com servo contínuo e fins de curso de recuo/avanço nos GPIOs 32/33 está documentada em [CARRINHO_CONTINUO_4_16_0.md](CARRINHO_CONTINUO_4_16_0.md). Atualizar supervisório e firmware juntos. Ao ligar, o carrinho recebe neutro, sem movimento automático.


## Criação automática de dados — versão 4.16.1

Use `dist/SpectrumLabPro_4_16_1.exe`. Os arquivos de dados ausentes são criados ao iniciar, sem substituir os existentes. A base de materiais editável passa a ser persistente. Veja [INICIALIZACAO_AUTOMATICA_4_16_1.md](INICIALIZACAO_AUTOMATICA_4_16_1.md) para locais e acesso inicial. Compatível com firmware 4.16.0.
