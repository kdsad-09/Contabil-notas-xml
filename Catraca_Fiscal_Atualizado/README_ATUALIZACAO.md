# Catraca Fiscal — atualização de triagem e contas

Esta pasta parte do ZIP do projeto recebido em 25/11/2026. A aplicação principal está em `modulo_fiscal_v1-20260929T104928Z-1-001/modulo_fiscal_v1/app.py`.

## Como testar no Windows

1. Extraia o ZIP em uma pasta nova, sem substituir sua versão atual. Mantenha um backup do projeto e dos dados.
2. Instale Python 3.11 ou 3.12 com a opção de adicionar ao PATH. Conexão com a internet é necessária para instalar os pacotes.
3. Na pasta extraída, dê dois cliques em `instalar_e_iniciar.bat`. Na primeira execução, ele cria um ambiente virtual e instala os pacotes; nas próximas, inicia o aplicativo. A instalação não foi testada neste computador com Windows.
4. Selecione **HIKARI CONSTRUÇÕES LTDA EPP — ORIGINAL** na barra lateral. Importe um ZIP pequeno com XMLs e confira cada nota antes de aprovar.
5. Na triagem, confira a razão social e o CNPJ do fornecedor no XML, selecione a conta correspondente, revise categoria, obra, pagamento e valores. Um fornecedor não localizado precisa ser cadastrado no sistema contábil e incluído no cadastro do projeto; não é substituído automaticamente por outra conta.
6. Em Exportação, escolha **Somente Aprovados** e gere o Modelo Domínio. Se alguma conta não for localizada ou divergir da obra/categoria, corrija na triagem. Antes de importar no Domínio, revise o arquivo e teste em um lote pequeno.

## GitHub e Streamlit Cloud

Este ZIP não atualiza o GitHub automaticamente. Após testar localmente, atualize os arquivos mantendo a estrutura de pastas. No Streamlit Cloud, o arquivo principal é `modulo_fiscal_v1-20260929T104928Z-1-001/modulo_fiscal_v1/app.py` e o `requirements.txt` da raiz aponta para as dependências do módulo. Faça backup antes de substituir arquivos no repositório.

O projeto contém cadastros de fornecedores e planos de contas do escritório. Verifique se o repositório e as permissões são adequados antes de enviar esses dados ao GitHub ou a serviços de IA. Não inclua XMLs de clientes nem arquivos de credenciais em um repositório público.

## O que foi alterado

- O cadastro Hikari original foi atualizado a partir de `data/Contas_novas_origem.xls`: 798 linhas de fornecedores, 25 obras e 436 linhas analíticas. O arquivo não traz CNPJ do fornecedor nem classificação contábil hierárquica; esses campos não foram inventados. Algumas descrições aparecem truncadas na origem.
- O código de fornecedor só é sugerido automaticamente se a razão social inteira for igual após normalizar acentos, pontuação e espaços. Nome parecido ou repetido com códigos diferentes fica para seleção manual. Confira também o CNPJ do XML.
- O material é classificado item a item. O aplicativo soma o valor líquido por categoria e sugere a de maior valor, mostrando a composição. Os descontos dos itens e o desconto adicional do cabeçalho são considerados. Empates, itens não identificados e valores ausentes geram aviso de revisão.
- A obra é associada por CNO completo cadastrado. Sem CNO, é sugerida a obra geral. CNO não encontrado exige escolha manual. As contas são procuradas apenas na obra e empresa selecionadas, com correspondência exata ou por família inequívoca; sem correspondência, ficam para revisão.
- O arquivo do Domínio exige aprovação e conta de despesa válida para cada NF/CFOP; uma nota a prazo exige fornecedor do cadastro ativo. Não utiliza código 1027 ou 5 como substituto automático para informação desconhecida. Pela regra anterior do projeto, pagamento à vista continua usando crédito 5: confirme se esse código é adequado ao plano da empresa.
- Para múltiplos CFOPs, o valor total da NF e cada parcela são rateados proporcionalmente pelos valores líquidos dos itens, com ajuste de centavos. O critério de rateio deve ser conferido pelo responsável, especialmente em notas com frete, impostos e CFOPs de naturezas diferentes.

## Limites desta versão

O arquivo Domínio existente gera um lançamento por NF/CFOP pelo valor total; os boletos aparecem em relatório separado, não geram automaticamente um lançamento por boleto. A saída e devolução continuam usando as regras anteriores do projeto e precisam de conferência fiscal e contábil. A aprovação pelo usuário registra a revisão da sugestão, não prova a correção do lançamento. Cadastros novos precisam ser incluídos no sistema contábil e na base do projeto; a interface ainda não grava cadastros novos de fornecedores.

Testes automatizados podem ser executados na pasta do módulo com `python -m unittest discover -s tests -v`. Foram testados os exemplos de fornecedores da planilha, categorias por valor, contas não encontradas, bloqueios de exportação e um XML sintético com dois CFOPs. Não foram fornecidos XMLs reais do caso e o aplicativo não foi testado visualmente no Windows.
