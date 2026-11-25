# Catraca Fiscal — Triagem de NF-e

Sistema de triagem e classificação de Notas Fiscais Eletrônicas (NF-e) para a **Hikari Construções LTDA EPP**.

## Funcionalidades

- **Upload de XMLs** via arquivo ZIP
- **Classificação automática** por palavras-chave usando os códigos de despesa do plano de contas Hikari
- **Classificação com IA** (Gemini) para maior precisão
- **17 categorias de despesa** do balancete oficial
- **14 centros de custo/obra** extraídos do plano de contas
- **Código contábil** de cada despesa visível e exportável
- **Exportação** para Excel e CSV com código contábil para copiar/colar

## Como usar

1. Faça upload de um ZIP contendo XMLs de NF-e na barra lateral
2. Revise as categorias e obras sugeridas
3. (Opcional) Use a classificação com IA inserindo sua chave Gemini
4. Aprove ou rejeite cada nota
5. Exporte os dados triados

## Deploy no Streamlit Cloud

1. Faça push deste repositório para o GitHub
2. Acesse [share.streamlit.io](https://share.streamlit.io)
3. Conecte o repositório e selecione `app.py` como arquivo principal
4. (Opcional) Configure a chave API DeepSeek AIem **Secrets**:
   ```toml
   GEMINI_API_KEY = "sua-chave-aqui"
   ```
