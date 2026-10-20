# SpectrumLabPro 4.11.0 — bancada demonstrativa de TCC

Esta versão corrige integridade de calibração, aquisição e comunicação. O Kappa continua sendo uma estimativa demonstrativa por equações fixas, sem treinamento ou validação analítica. Uma referência branca melhor não valida o modelo de Kappa.

## Como colocar em uso

1. Abra o sketch atualizado na segunda pasta de trabalho, mantendo a subpasta src/ junto dele, e envie-o à mesma placa ESP32 usada pela bancada. Para ESP32 com 4 MB de flash, selecione a partição No OTA (2MB APP/2MB SPIFFS); a partição padrão de 1,3 MB não comporta as três conexões. Confirme a capacidade da sua placa antes de gravar. Os pinos, ângulos, ganho 64x, integração nominal de 140 ms e corrente de LED de 50 mA foram mantidos. A aquisição dos seis canais em one-shot pode consumir dois períodos de integração.
2. Execute dist/SpectrumLabPro_4_11_0.exe. O executável anterior foi preservado.
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
Novo executável: dist/SpectrumLabPro_4_11_0.exe. A versão 4.10.0 também foi preservada.

O executável guarda a calibração em %LOCALAPPDATA%/SpectrumLabPro/calibracao.json, evitando a pasta temporária do PyInstaller. O banco do executável continua ao lado do executável, preservando o histórico em dist/usuarios.db. Ao executar o código Python, os arquivos ficam na pasta principal. Para testes, SPECTRUM_LAB_DATA_DIR permite uma pasta isolada.

Originais, calibrações e cópias consistentes dos bancos: backups/20261008_estabilidade/.

## Verificação

Execute python -B tests/test_stability_regression.py. A suíte de 30 testes passou em 08/10/2026. O executável foi gerado e permaneceu ativo em teste de inicialização isolado por 15 segundos, sem erro registrado.
Os testes usam hardware simulado e diretórios temporários. Não escrever nos arquivos reais de calibração durante testes. Os antigos scripts de teste encaminham à suíte isolada.

Compilar o supervisório: python -m PyInstaller --noconfirm SpectrumLabPro_4_11_0.spec.

Firmware compilado com sucesso: esp32:esp32:esp32:PartitionScheme=no_ota, core ESP32 3.3.12. Uso de flash: 1.665.459 bytes (79% do aplicativo de 2 MB); RAM estática: 65.056 bytes (19%). O pacote dist/Firmware_ESP32_4_10_0.zip contém o sketch e o driver local necessários. Não foi feito upload à placa nem ensaio físico nesta revisão.

A compilação e os testes de software não substituem ensaios na bancada. Após trocar o procedimento de referência, os valores demonstrativos podem mudar; não ajustar coeficientes apenas para recuperar resultados anteriores.

A documentação técnica antiga descreve versões anteriores. Este documento prevalece quanto aos fluxos corrigidos.

## Interface adaptativa — versão 4.11.0

A interface usa a área útil e a escala nativa do Qt/Windows. A janela é limitada à tela ao trocar de monitor ou alterar a área disponível. Não multiplica a escala do Windows novamente.

- Barra de conexão e ações quebram automaticamente em linhas, conforme o tamanho real dos textos.
- KPIs usam quatro, duas ou uma coluna conforme a largura disponível.
- Controles e gráfico ficam lado a lado em janelas largas e empilhados em janelas menores.
- Cards de calibração e diagnóstico também se reorganizam.
- Seletores do gráfico e ações de exportação quebram linha.
- Rolagem vertical preserva textos e botões legíveis quando a altura é insuficiente. A emergência superior permanece fora da área de rolagem.
- Diálogos maiores que a área disponível são limitados à tela e ganham rolagem.
- Tamanhos e posições se atualizam ao redimensionar a janela. Não é necessário informar polegadas, resolução ou escala.

Verificação adicional: python -B tests/test_responsive_interface.py. Quatro testes verificam sete tamanhos de janela (480×320 a 1920×1080), ausência de corte horizontal no painel principal, emergência visível, reorganização sem perda do resultado, ajuste à área menor de notebook e diálogos. Foram verificadas escalas de 100%, 125% e 150% em ambiente simulado; o notebook físico não foi acessado. Imagens de conferência ficam em validation/. Cópias anteriores desta revisão ficam em backups/20261008_interface/.
