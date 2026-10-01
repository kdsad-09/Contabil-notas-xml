import os
import pprint
from xml_processor import parse_nfe

target_xml = r"C:\Users\Usuario\Downloads\teste xml\teste xml\xml da hikari\qRNb1Oq8-part-1\17260100085446000166550010002683231774638236.xml"

if __name__ == "__main__":
    if os.path.exists(target_xml):
        with open(target_xml, "rb") as f:
            data = parse_nfe(f.read())
        
        record = data[0] if data else {}
        print("Fornecedor:", record.get("fornecedor"))
        print("Entrega:", record.get("endereco_entrega"))
        print("Frete/Modalidade:", record.get("modalidade_frete"))
        print("IBS/CBS:", record.get("imposto_ibscbs"))
        print("Parcelas Encontradas:", record.get("qtd_parcelas"))
    else:
        print("Arquivo nao encontrado:", target_xml)
