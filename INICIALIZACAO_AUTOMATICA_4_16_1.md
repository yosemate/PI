# Inicialização automática dos dados — 4.16.1

Ao abrir `SpectrumLabPro_4_16_1.exe`, o programa cria os arquivos de dados ausentes. Os que já existem são preservados; arquivos inválidos não são apagados e substituídos silenciosamente.

| Arquivo | Quando não existe |
|---|---|
| usuarios.db | Cria usuários, tabelas de histórico e acesso inicial admin/admin; histórico começa vazio |
| calibracao.json | Cria perfis pendentes, sem branco/escuro medidos nem calibração válida |
| interface.json | Cria preferência inicial de tema claro |
| banco_materiais.json | Cria uma cópia editável da base que acompanha o executável |

A calibração inicial permanece pendente até medir branco e escuro. Criar um banco novo não recupera os cadastros ou ensaios de um arquivo removido; para transportar os dados existentes, copie o banco original.

## Onde ficam

- Usuários e histórico: `usuarios.db` ao lado do executável, como nas versões anteriores. Se o banco ainda não existir e a pasta do programa não permitir gravação, cria em `%LOCALAPPDATA%\SpectrumLabPro\usuarios.db`. Um banco já existente não é trocado por outro vazio em uma pasta diferente.
- Calibração: `%LOCALAPPDATA%\SpectrumLabPro\calibracao.json`.
- Preferências: `%LOCALAPPDATA%\SpectrumLabPro\interface.json`.
- Materiais editáveis: `%LOCALAPPDATA%\SpectrumLabPro\banco_materiais.json`. A base deixa de ser editada na pasta temporária de extração do executável, garantindo persistência. Na primeira criação, se houver `banco_materiais.json` ao lado do executável, usa esse arquivo como base inicial.

O ambiente de testes continua permitindo `SPECTRUM_LAB_DATA_DIR` para isolar todos os arquivos. Ao executar o código Python, o banco, a calibração e os materiais continuam na pasta de código, salvo essa substituição explícita.

Os controles, servos e protocolo permanecem compatíveis com o firmware 4.16.0. Esta revisão altera apenas armazenamento e inicialização do supervisório. Bibliotecas do programa seguem empacotadas no executável; esta criação automática se refere aos arquivos locais de dados e configurações.

Validação: 13 testes de criação/preservação/portabilidade, 30 de regressão, 47 de controles e 6 de tema passaram com dados e hardware simulados. O banco real de usuários e ensaios não foi usado nos testes.

O executável final também passou por duas inicializações com pasta de dados temporária: a primeira criou os quatro arquivos; na segunda, recriou a preferência removida e preservou senha alterada, histórico, material personalizado e calibração existente.
