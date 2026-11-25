import unittest
from decimal import Decimal
import contas_db, fornecedor_db, categorizer
from dominio_exporter import build_dominio_dataframe, export_to_dominio_excel
from xml_processor import parse_nfe

class RevisaoContabil(unittest.TestCase):
    def setUp(self):
        contas_db.set_empresa('hikari_construcoes_original')
        self.obra=contas_db.get_obra_geral_label()
    def test_fornecedores_hikari_e_similaridade(self):
        for nome,cod in [('M C BARREIRO E CIA LTDA',1358),('ENCANEL COM. DE MAT. DE CONST. LTDA',519),('RH DISTRIBUIDORA LTDA',1306)]:
            self.assertEqual(fornecedor_db.lookup_fornecedor_por_nome(nome)['codigo_contabil'],cod)
        self.assertIsNone(fornecedor_db.lookup_fornecedor_por_nome('M C COMERCIO DE MATERIAL DE CONSTRUCAO LTDA'))
        self.assertIsNone(fornecedor_db.lookup_fornecedor_por_nome('ENCANEL COMERCIO DE MATERIAIS'))
    def test_maior_valor_por_categoria_nao_uma_ocorrencia(self):
        cat,msg=categorizer.categorize_invoice([{'descricao':'tijolo','valor_total':10},{'descricao':'tubo pvc','valor_total':900}])
        self.assertEqual(cat,'DESPESAS COM MATERIAL HIDRAULICO'); self.assertIn('900.00',msg)
        cat,_=categorizer.categorize_invoice([{'descricao':'cimento','valor_total':200,'valor_desconto':150},{'descricao':'tubo pvc','valor_total':100}]);self.assertEqual(cat,'DESPESAS COM MATERIAL HIDRAULICO')
        cat,msg=categorizer.categorize_invoice([{'descricao':'produto sem regra','valor_total':10}]);self.assertIn('REVISAR',msg)
        cat,msg=categorizer.categorize_invoice([{'descricao':'cimento','valor_total':10},{'descricao':'tijolo','valor_total':10}]);self.assertIn('empate',msg)
    def test_codigo_por_obra_e_sem_fallback(self):
        self.assertEqual(contas_db.get_codigo_para_obra_e_categoria(self.obra,'DESPESAS COM MATERIAL HIDRAULICO'),1647)
        self.assertEqual(contas_db.get_codigo_para_obra_e_categoria(self.obra,'DESPESAS COM CIMENTO'),2044)
        self.assertIsNone(contas_db.get_codigo_para_obra_e_categoria(self.obra,'DESPESAS COM COISA INEXISTENTE'))
        self.assertIsNone(contas_db.get_codigo_para_obra_e_categoria('OBRA QUE NAO EXISTE','DESPESAS COM MATERIAL HIDRAULICO'))
    def test_exportacao_segura(self):
        doc={'uid':'x','nNF':'123','valor_total':100,'data_emissao':'2026-11-01','fornecedor':'M C BARREIRO E CIA LTDA','is_a_vista':False}
        cat={'x':'DESPESAS COM MATERIAL HIDRAULICO'}; obras={'x':self.obra}; cod={'x':'1647'}; apro={'x':'Aprovado'}
        with self.assertRaises(ValueError):build_dominio_dataframe([doc],cat,obras,cod,apro,{})
        forn={'x':{'codigo_contabil':1358}}
        with self.assertRaises(ValueError):build_dominio_dataframe([doc],cat,obras,{'x':'1027'},apro,forn)
        with self.assertRaises(ValueError):build_dominio_dataframe([doc],cat,obras,cod,{'x':'Pendente'},forn)
        df=build_dominio_dataframe([doc],cat,obras,cod,apro,forn)
        self.assertEqual(df.iloc[0]['Cod. Conta Credito'],1358);self.assertEqual(df.iloc[0]['Cod. Conta Debito'],1647)
        self.assertGreater(len(export_to_dominio_excel([doc],cat,obras,cod,apro,forn).getvalue()),1000)
        doc['is_a_vista']=True
        self.assertEqual(build_dominio_dataframe([doc],cat,obras,cod,apro,{}).iloc[0]['Cod. Conta Credito'],5)
    def test_xml_rateio_e_desconto(self):
        xml='''<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe><ide><nNF>42</nNF><serie>1</serie><dhEmi>2026-11-01T10:00:00-03:00</dhEmi><natOp>VENDA</natOp><tpNF>1</tpNF></ide><emit><xNome>M C BARREIRO E CIA LTDA</xNome></emit><dest><xNome>HIKARI</xNome></dest>
        <det><prod><xProd>TUBO PVC</xProd><CFOP>5102</CFOP><vProd>100.00</vProd><vDesc>10.00</vDesc></prod></det>
        <det><prod><xProd>TIJOLO</xProd><CFOP>5405</CFOP><vProd>50.00</vProd><vDesc>0</vDesc></prod></det>
        <total><ICMSTot><vProd>150.00</vProd><vDesc>15.00</vDesc><vFrete>10</vFrete><vNF>145.00</vNF></ICMSTot></total><cobr><dup><nDup>1</nDup><dVenc>2026-12-01</dVenc><vDup>145.00</vDup></dup></cobr></infNFe></NFe></nfeProc>'''
        rows=parse_nfe(xml);self.assertEqual(len(rows),2,rows)
        self.assertEqual(sum(Decimal(str(r['valor_total'])) for r in rows),Decimal('145.0'))
        self.assertEqual(sum(Decimal(str(r['parcela_valor'])) for r in rows),Decimal('145.0'))
        self.assertEqual(categorizer.categorize_invoice(rows[0]['itens'])[0],'DESPESAS COM MATERIAL HIDRAULICO')
        items=[i for row in rows for i in row['itens']]
        self.assertAlmostEqual(sum(i['valor_liquido_categorizacao'] for i in items),135)
        self.assertTrue(all(not row['is_a_vista'] for row in rows))

if __name__=='__main__':unittest.main()
