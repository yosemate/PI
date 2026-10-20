# Correção de comunicação e telemetria — 4.16.2

Abra dist/SpectrumLabPro_4_16_2.exe. O executável anterior e os dados existentes foram preservados.

O programa solicita CMD:DIAG_SENSOR a cada cinco segundos quando conectado, com protocolo e sensor reconhecidos, sem rotina, movimento, comando pendente ou emergência. Com o firmware 4.16.0, já recebe temperatura interna do AS7263, configurações de ganho/integração/corrente e estado do LED.

Linhas com UTF-8 inválido são descartadas integralmente e registradas como RX DESCARTADO. Seus fragmentos nunca são interpretados como comandos ou medições. O heartbeat continua desconectando após seis segundos sem resposta válida; erros reais de transporte continuam encerrando a conexão.

Para temperatura interna do ESP32, frequência da CPU e RAM livre/total, grave o sketch completo de dist/Firmware_ESP32_4_16_2/sketch_sep4a_copy_20261008183551, mantendo src junto dele. CPU é frequência em MHz, não porcentagem de utilização. Temperatura interna não representa temperatura ambiente. Irradiância absoluta e versão do firmware interno do sensor permanecem indisponíveis/não consultadas.

O firmware novo mantém movimentos, pinos e intertravamentos do 4.16.0. O pacote inclui fontes para compilar no Arduino IDE; não foi compilado nem gravado na placa nesta revisão, pois o compilador ESP32 não está disponível neste ambiente.

Validação: suíte de recuperação/telemetria (42 testes, incluindo regressões de interface herdadas) suíte de estabilidade (30 testes) e controles/intertravamentos (47 testes) passaram com hardware simulado e dados temporários. Teste físico permanece necessário.

## Carcaça durante sessão admin

Com o firmware 4.16.2 e usuário admin autenticado, o estado do fim de curso da carcaça continua visível, mas não bloqueia operações nem solicita novos logins. A autorização é confirmada pelo ESP32, renovada durante a sessão inclusive em repouso e removida por logout, emergência ou perda de comunicação. Usuários sem perfil admin mantêm o fluxo de autorização anterior. As chaves de percurso da porta/carrinho e os demais intertravamentos não foram alterados. Atualizar o firmware é necessário para manter a autorização ao abrir/fechar a carcaça.
