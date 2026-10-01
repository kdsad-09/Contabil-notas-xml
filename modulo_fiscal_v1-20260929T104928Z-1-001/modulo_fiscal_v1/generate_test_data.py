"""
generate_test_data.py — Creates realistic test XMLs by cloning REAL NF-e structure
and injecting construction-related items, emitters, and CNO in infAdic.

This ensures the generated XMLs are structurally identical to real ones,
but with construction civil scenarios for testing the Catraca Fiscal app.
"""
import zipfile
import xml.etree.ElementTree as ET
import random
import io
import copy
import re

# ═══════════════════════════════════════════════════════════════════
# CONSTRUCTION SCENARIOS
# Each scenario represents a different supplier selling construction
# materials, with CNO references in infAdic for obra tracking.
# ═══════════════════════════════════════════════════════════════════

OBRAS = [
    {"cno": "25060512345601", "nome": "Residencial Parque das Aguas - Bloco A", "endereco": "Quadra 108 Sul, Lote 12"},
    {"cno": "25060598765402", "nome": "Galpao Comercial BR-153 Km 12",          "endereco": "BR-153 Km 12, Zona Industrial"},
    {"cno": "25060567890103", "nome": "Escola Municipal Novo Horizonte",        "endereco": "Quadra 405 Norte, Av. LO-09"},
]

FORNECEDORES = [
    {"cnpj": "12345678000190", "xNome": "DEPOSITO CONSTRULAR LTDA",         "xFant": "CONSTRULAR MATERIAIS",    "ie": "290001001", "xLgr": "Av. JK", "nro": "1500", "xBairro": "Centro", "xMun": "Palmas", "UF": "TO", "CEP": "77001000"},
    {"cnpj": "23456789000181", "xNome": "ELETRICA E ILUMINACAO RAIO LTDA",  "xFant": "RAIO ELETRICA",           "ie": "290002002", "xLgr": "Rua 10",  "nro": "300",  "xBairro": "Taquaralto", "xMun": "Palmas", "UF": "TO", "CEP": "77060000"},
    {"cnpj": "34567890000172", "xNome": "HIDRAULICA PALMAS EIRELI",         "xFant": "HIDROTINS",               "ie": "290003003", "xLgr": "Av. NS-02","nro": "80",   "xBairro": "Plano Dir. Norte", "xMun": "Palmas", "UF": "TO", "CEP": "77006000"},
    {"cnpj": "45678901000163", "xNome": "TINTAS E CORES DO TOCANTINS LTDA", "xFant": "MUNDO DAS TINTAS",        "ie": "290004004", "xLgr": "Rua 03",  "nro": "45",   "xBairro": "Setor Comercial", "xMun": "Palmas", "UF": "TO", "CEP": "77015000"},
    {"cnpj": "56789012000154", "xNome": "PISOS E ACABAMENTOS CENTER LTDA",  "xFant": "PISO CENTER",             "ie": "290005005", "xLgr": "Av. LO-14","nro": "200",  "xBairro": "Plano Dir. Sul", "xMun": "Palmas", "UF": "TO", "CEP": "77020000"},
    {"cnpj": "67890123000145", "xNome": "LOCAMAQ EQUIPAMENTOS E SERVICOS",  "xFant": "LOCAMAQ",                 "ie": "290006006", "xLgr": "Rod TO-010","nro": "Km 5", "xBairro": "Zona Rural", "xMun": "Palmas", "UF": "TO", "CEP": "77000000"},
    {"cnpj": "78901234000136", "xNome": "MGA SERVICOS DE ENGENHARIA LTDA",  "xFant": "MGA ENGENHARIA",          "ie": "290007007", "xLgr": "Quadra 104 Sul","nro": "10","xBairro": "Plano Dir. Sul", "xMun": "Palmas", "UF": "TO", "CEP": "77100000"},
]

# Items grouped by category — each item dict has all prod fields
ITEMS_POR_CATEGORIA = {
    "Material de Construcao": [
        {"cProd": "MC001", "cEAN": "7891234560010", "xProd": "Cimento CP II-E 50kg Itambe",           "NCM": "25232100", "CFOP": "5102", "uCom": "SC", "qCom": "50.0000", "vUnCom": "38.50", "vProd": "1925.00"},
        {"cProd": "MC002", "cEAN": "7891234560027", "xProd": "Areia Media Lavada",                     "NCM": "25051000", "CFOP": "5102", "uCom": "M3", "qCom": "8.0000",  "vUnCom": "135.00","vProd": "1080.00"},
        {"cProd": "MC003", "cEAN": "7891234560034", "xProd": "Brita 01 Pedra Britada",                 "NCM": "25171000", "CFOP": "5102", "uCom": "M3", "qCom": "6.0000",  "vUnCom": "148.00","vProd": "888.00"},
        {"cProd": "MC004", "cEAN": "7891234560041", "xProd": "Argamassa AC-III Cinza 20kg Quartzolit", "NCM": "38160090", "CFOP": "5102", "uCom": "SC", "qCom": "25.0000", "vUnCom": "32.00", "vProd": "800.00"},
        {"cProd": "MC005", "cEAN": "7891234560058", "xProd": "Tijolo Ceramico 8 Furos 9x19x19",       "NCM": "69041000", "CFOP": "5102", "uCom": "MIL","qCom": "3.0000",  "vUnCom": "980.00","vProd": "2940.00"},
        {"cProd": "MC006", "cEAN": "7891234560065", "xProd": "Bloco de Concreto Estrutural 14x19x39",  "NCM": "68101900", "CFOP": "5102", "uCom": "UN", "qCom": "150.0000","vUnCom": "5.90",  "vProd": "885.00"},
    ],
    "Eletrica": [
        {"cProd": "EL001", "cEAN": "7892345670010", "xProd": "Cabo Flexivel 2.5mm 750V Preto 100m Cobrecom",  "NCM": "85444900", "CFOP": "5102", "uCom": "RL", "qCom": "8.0000",  "vUnCom": "98.00", "vProd": "784.00"},
        {"cProd": "EL002", "cEAN": "7892345670027", "xProd": "Cabo Flexivel 4.0mm 750V Azul 100m Cobrecom",   "NCM": "85444900", "CFOP": "5102", "uCom": "RL", "qCom": "5.0000",  "vUnCom": "152.00","vProd": "760.00"},
        {"cProd": "EL003", "cEAN": "7892345670034", "xProd": "Disjuntor DIN Bipolar 40A Schneider",           "NCM": "85362000", "CFOP": "5102", "uCom": "UN", "qCom": "12.0000", "vUnCom": "32.00", "vProd": "384.00"},
        {"cProd": "EL004", "cEAN": "7892345670041", "xProd": "Luminaria LED Sobrepor 36W 120cm",              "NCM": "94054090", "CFOP": "5102", "uCom": "UN", "qCom": "20.0000", "vUnCom": "68.00", "vProd": "1360.00"},
        {"cProd": "EL005", "cEAN": "7892345670058", "xProd": "Tomada 2P+T 20A Branca Tramontina",             "NCM": "85366990", "CFOP": "5102", "uCom": "UN", "qCom": "40.0000", "vUnCom": "14.50", "vProd": "580.00"},
        {"cProd": "EL006", "cEAN": "7892345670065", "xProd": "Eletroduto Corrugado Flexivel 3/4 pol 50m",     "NCM": "39172190", "CFOP": "5102", "uCom": "RL", "qCom": "6.0000",  "vUnCom": "62.00", "vProd": "372.00"},
    ],
    "Hidraulica": [
        {"cProd": "HI001", "cEAN": "7893456780010", "xProd": "Tubo PVC Soldavel Marrom 50mm 6m Tigre",   "NCM": "39172190", "CFOP": "5102", "uCom": "BR", "qCom": "15.0000", "vUnCom": "34.00", "vProd": "510.00"},
        {"cProd": "HI002", "cEAN": "7893456780027", "xProd": "Tubo PVC Esgoto Branco 100mm 6m",          "NCM": "39172190", "CFOP": "5102", "uCom": "BR", "qCom": "10.0000", "vUnCom": "72.00", "vProd": "720.00"},
        {"cProd": "HI003", "cEAN": "7893456780034", "xProd": "Joelho 90 graus PVC Soldavel 50mm Tigre",   "NCM": "39174000", "CFOP": "5102", "uCom": "UN", "qCom": "25.0000", "vUnCom": "4.80",  "vProd": "120.00"},
        {"cProd": "HI004", "cEAN": "7893456780041", "xProd": "Registro Esfera PVC Soldavel 50mm",         "NCM": "84818019", "CFOP": "5102", "uCom": "UN", "qCom": "6.0000",  "vUnCom": "48.00", "vProd": "288.00"},
        {"cProd": "HI005", "cEAN": "7893456780058", "xProd": "Caixa d Agua Polietileno 1000L Fortlev",    "NCM": "39251000", "CFOP": "5102", "uCom": "UN", "qCom": "2.0000",  "vUnCom": "480.00","vProd": "960.00"},
    ],
    "Pintura": [
        {"cProd": "PI001", "cEAN": "7894567890010", "xProd": "Tinta Acrilica Premium Branco Neve 18L Suvinil", "NCM": "32091000", "CFOP": "5102", "uCom": "LT", "qCom": "12.0000", "vUnCom": "395.00", "vProd": "4740.00"},
        {"cProd": "PI002", "cEAN": "7894567890027", "xProd": "Tinta Acrilica Premium Cinza Urbano 18L Coral",  "NCM": "32091000", "CFOP": "5102", "uCom": "LT", "qCom": "6.0000",  "vUnCom": "420.00", "vProd": "2520.00"},
        {"cProd": "PI003", "cEAN": "7894567890034", "xProd": "Massa Corrida PVA 25kg Suvinil",                 "NCM": "32141010", "CFOP": "5102", "uCom": "LT", "qCom": "10.0000", "vUnCom": "68.00",  "vProd": "680.00"},
        {"cProd": "PI004", "cEAN": "7894567890041", "xProd": "Rolo de La 23cm Anti-respingo Atlas",            "NCM": "96033000", "CFOP": "5102", "uCom": "UN", "qCom": "8.0000",  "vUnCom": "35.00",  "vProd": "280.00"},
        {"cProd": "PI005", "cEAN": "7894567890058", "xProd": "Lixa d Agua 220 Norton",                         "NCM": "68052000", "CFOP": "5102", "uCom": "UN", "qCom": "30.0000", "vUnCom": "3.80",   "vProd": "114.00"},
    ],
    "Acabamento": [
        {"cProd": "AC001", "cEAN": "7895678900010", "xProd": "Porcelanato Polido 60x60 Bege Biancogres CX",  "NCM": "69072300", "CFOP": "5102", "uCom": "CX", "qCom": "45.0000", "vUnCom": "92.00",  "vProd": "4140.00"},
        {"cProd": "AC002", "cEAN": "7895678900027", "xProd": "Azulejo Branco Acetinado 30x60 Eliane CX",     "NCM": "69072100", "CFOP": "5102", "uCom": "CX", "qCom": "30.0000", "vUnCom": "58.00",  "vProd": "1740.00"},
        {"cProd": "AC003", "cEAN": "7895678900034", "xProd": "Rejunte Flexivel Cinza Platina 5kg Quartzolit","NCM": "38160090", "CFOP": "5102", "uCom": "SC", "qCom": "12.0000", "vUnCom": "30.00",  "vProd": "360.00"},
    ],
    "Locacao": [
        {"cProd": "LO001", "cEAN": "SEM GTIN", "xProd": "Locacao Betoneira 400L - Mensal Fev/2026",       "NCM": "84743100", "CFOP": "5949", "uCom": "MES", "qCom": "1.0000", "vUnCom": "900.00", "vProd": "900.00"},
        {"cProd": "LO002", "cEAN": "SEM GTIN", "xProd": "Locacao Andaime Fachadeiro 50m2 - Mensal",       "NCM": "73089090", "CFOP": "5949", "uCom": "MES", "qCom": "1.0000", "vUnCom": "1350.00","vProd": "1350.00"},
        {"cProd": "LO003", "cEAN": "SEM GTIN", "xProd": "Locacao Vibrador de Concreto - Mensal",          "NCM": "84797900", "CFOP": "5949", "uCom": "MES", "qCom": "1.0000", "vUnCom": "480.00", "vProd": "480.00"},
    ],
    "Servicos": [
        {"cProd": "SV001", "cEAN": "SEM GTIN", "xProd": "Servico de Instalacao Eletrica Predial - 120h",  "NCM": "00000000", "CFOP": "5933", "uCom": "HR", "qCom": "120.0000","vUnCom": "88.00", "vProd": "10560.00"},
        {"cProd": "SV002", "cEAN": "SEM GTIN", "xProd": "Servico de Instalacao Hidraulica - 80h",         "NCM": "00000000", "CFOP": "5933", "uCom": "HR", "qCom": "80.0000", "vUnCom": "78.00", "vProd": "6240.00"},
    ],
}

# 10 INVOICES to generate
INVOICES = [
    # 1. Material de Construção → Obra 0 (Residencial)
    {"nNF": "8001", "forn_idx": 0, "cat": "Material de Construcao", "item_indices": [0, 1, 2, 4],    "obra_idx": 0, "tPag": "15", "natOp": "Venda de mercadorias"},
    # 2. Elétrica → Obra 0 (Residencial) — mesma obra
    {"nNF": "8002", "forn_idx": 1, "cat": "Eletrica",              "item_indices": [0, 1, 2, 3, 4], "obra_idx": 0, "tPag": "03", "natOp": "Venda de mercadorias"},
    # 3. Hidráulica → Obra 1 (Galpão Comercial)
    {"nNF": "8003", "forn_idx": 2, "cat": "Hidraulica",            "item_indices": [0, 1, 2, 3, 4], "obra_idx": 1, "tPag": "17", "natOp": "Venda de mercadorias"},
    # 4. Pintura → Obra 0 (Residencial) — mesma obra que NF 8001/8002
    {"nNF": "8004", "forn_idx": 3, "cat": "Pintura",               "item_indices": [0, 1, 2, 3, 4], "obra_idx": 0, "tPag": "01", "natOp": "Venda de mercadorias"},
    # 5. Acabamento → Obra 2 (Escola)
    {"nNF": "8005", "forn_idx": 4, "cat": "Acabamento",            "item_indices": [0, 1, 2],        "obra_idx": 2, "tPag": "15", "natOp": "Venda de mercadorias"},
    # 6. Material Construção → Obra 1 (Galpão) — mesma obra que NF 8003
    {"nNF": "8006", "forn_idx": 0, "cat": "Material de Construcao", "item_indices": [3, 5],          "obra_idx": 1, "tPag": "17", "natOp": "Venda de mercadorias"},
    # 7. Locação → Obra 2 (Escola) — mesma obra que NF 8005
    {"nNF": "8007", "forn_idx": 5, "cat": "Locacao",               "item_indices": [0, 1, 2],        "obra_idx": 2, "tPag": "15", "natOp": "Locacao de bens"},
    # 8. Serviços → Obra 0 (Residencial)
    {"nNF": "8008", "forn_idx": 6, "cat": "Servicos",              "item_indices": [0, 1],           "obra_idx": 0, "tPag": "18", "natOp": "Prestacao de servico"},
    # 9. Elétrica → Obra 1 (Galpão) — elétrica para outra obra
    {"nNF": "8009", "forn_idx": 1, "cat": "Eletrica",              "item_indices": [3, 5],           "obra_idx": 1, "tPag": "04", "natOp": "Venda de mercadorias"},
    # 10. Material misto → SEM CNO (nota sem info de obra para testar alerta)
    {"nNF": "8010", "forn_idx": 0, "cat": "Material de Construcao", "item_indices": [0, 3],          "obra_idx": None, "tPag": "01", "natOp": "Venda de mercadorias"},
]

DEST_CNPJ = "55666777000188"
DEST_NOME = "CONSTRUTORA ALVES ENGENHARIA LTDA"


def build_xml(invoice_spec, template_root, ns):
    """
    Takes a real XML root as template and replaces content to create
    a construction-civil scenario NF-e while keeping exact same structure.
    """
    # Deep copy the template
    root = copy.deepcopy(template_root)
    
    infNFe = root.find('.//nfe:infNFe', ns)
    
    obra = OBRAS[invoice_spec["obra_idx"]] if invoice_spec["obra_idx"] is not None else None
    forn = FORNECEDORES[invoice_spec["forn_idx"]]
    items = [ITEMS_POR_CATEGORIA[invoice_spec["cat"]][i] for i in invoice_spec["item_indices"]]
    
    # --- Modify IDE ---
    _set_text(infNFe, 'nfe:ide/nfe:nNF', ns, invoice_spec["nNF"])
    _set_text(infNFe, 'nfe:ide/nfe:natOp', ns, invoice_spec["natOp"])
    # Randomize date within Feb 2026
    day = random.randint(1, 14)
    hour = random.randint(7, 18)
    _set_text(infNFe, 'nfe:ide/nfe:dhEmi', ns, f"2026-02-{day:02d}T{hour:02d}:{random.randint(0,59):02d}:00-03:00")
    dhSaiEnt = infNFe.find('nfe:ide/nfe:dhSaiEnt', ns)
    if dhSaiEnt is not None:
        dhSaiEnt.text = f"2026-02-{day:02d}T{hour:02d}:{random.randint(0,59):02d}:00-03:00"
    
    # --- Modify EMIT (Fornecedor) ---
    _set_text(infNFe, 'nfe:emit/nfe:CNPJ', ns, forn["cnpj"])
    _set_text(infNFe, 'nfe:emit/nfe:xNome', ns, forn["xNome"])
    _set_text(infNFe, 'nfe:emit/nfe:xFant', ns, forn["xFant"])
    _set_text(infNFe, 'nfe:emit/nfe:IE', ns, forn["ie"])
    _set_text(infNFe, 'nfe:emit/nfe:enderEmit/nfe:xLgr', ns, forn["xLgr"])
    _set_text(infNFe, 'nfe:emit/nfe:enderEmit/nfe:nro', ns, forn["nro"])
    _set_text(infNFe, 'nfe:emit/nfe:enderEmit/nfe:xBairro', ns, forn["xBairro"])
    _set_text(infNFe, 'nfe:emit/nfe:enderEmit/nfe:xMun', ns, forn["xMun"])
    _set_text(infNFe, 'nfe:emit/nfe:enderEmit/nfe:UF', ns, forn["UF"])
    _set_text(infNFe, 'nfe:emit/nfe:enderEmit/nfe:CEP', ns, forn["CEP"])
    
    # --- Modify DEST (Cliente = Construtora) ---
    _set_text(infNFe, 'nfe:dest/nfe:CNPJ', ns, DEST_CNPJ)
    _set_text(infNFe, 'nfe:dest/nfe:xNome', ns, DEST_NOME)

    # --- Replace DET (items) ---
    # Remove existing dets
    existing_dets = infNFe.findall('nfe:det', ns)
    for det in existing_dets:
        infNFe.remove(det)
    
    # Find insertion point (before <total>)
    total_elem = infNFe.find('nfe:total', ns)
    total_idx = list(infNFe).index(total_elem)
    
    total_val = 0.0
    for i, item in enumerate(items, 1):
        det = ET.Element(f'{{{ns["nfe"]}}}det', attrib={"nItem": str(i)})
        prod = ET.SubElement(det, f'{{{ns["nfe"]}}}prod')
        
        for field in ["cProd", "cEAN", "xProd", "NCM", "CFOP", "uCom", "qCom", "vUnCom", "vProd"]:
            ET.SubElement(prod, f'{{{ns["nfe"]}}}{field}').text = item[field]
        
        # Trib fields (mirror commercial)
        ET.SubElement(prod, f'{{{ns["nfe"]}}}cEANTrib').text = item["cEAN"]
        ET.SubElement(prod, f'{{{ns["nfe"]}}}uTrib').text = item["uCom"]
        ET.SubElement(prod, f'{{{ns["nfe"]}}}qTrib').text = item["qCom"]
        ET.SubElement(prod, f'{{{ns["nfe"]}}}vUnTrib').text = item["vUnCom"]
        ET.SubElement(prod, f'{{{ns["nfe"]}}}indTot').text = "1"
        ET.SubElement(prod, f'{{{ns["nfe"]}}}nItemPed').text = str(i)
        
        # Tax block (Simples Nacional)
        imposto = ET.SubElement(det, f'{{{ns["nfe"]}}}imposto')
        item_val = float(item["vProd"])
        ET.SubElement(imposto, f'{{{ns["nfe"]}}}vTotTrib').text = f"{item_val * 0.3345:.2f}"
        icms = ET.SubElement(imposto, f'{{{ns["nfe"]}}}ICMS')
        icmssn = ET.SubElement(icms, f'{{{ns["nfe"]}}}ICMSSN102')
        ET.SubElement(icmssn, f'{{{ns["nfe"]}}}orig').text = "0"
        ET.SubElement(icmssn, f'{{{ns["nfe"]}}}CSOSN').text = "400"
        pis = ET.SubElement(imposto, f'{{{ns["nfe"]}}}PIS')
        pisnt = ET.SubElement(pis, f'{{{ns["nfe"]}}}PISNT')
        ET.SubElement(pisnt, f'{{{ns["nfe"]}}}CST').text = "07"
        cofins = ET.SubElement(imposto, f'{{{ns["nfe"]}}}COFINS')
        cofinsnt = ET.SubElement(cofins, f'{{{ns["nfe"]}}}COFINSNT')
        ET.SubElement(cofinsnt, f'{{{ns["nfe"]}}}CST').text = "07"
        
        infNFe.insert(total_idx, det)
        total_idx += 1
        total_val += item_val
    
    # --- Update TOTAL ---
    trib_total = total_val * 0.3345
    _set_text(infNFe, 'nfe:total/nfe:ICMSTot/nfe:vProd', ns, f"{total_val:.2f}")
    _set_text(infNFe, 'nfe:total/nfe:ICMSTot/nfe:vNF', ns, f"{total_val:.2f}")
    _set_text(infNFe, 'nfe:total/nfe:ICMSTot/nfe:vTotTrib', ns, f"{trib_total:.2f}")
    
    # --- Update PAG ---
    _set_text(infNFe, 'nfe:pag/nfe:detPag/nfe:tPag', ns, invoice_spec["tPag"])
    _set_text(infNFe, 'nfe:pag/nfe:detPag/nfe:vPag', ns, f"{total_val:.2f}")
    
    # --- Update COBR if exists ---
    cobr_fat = infNFe.find('nfe:cobr/nfe:fat', ns)
    if cobr_fat is not None:
        _set_text(cobr_fat, 'nfe:nFat', ns, f"00{invoice_spec['nNF']}")
        _set_text(cobr_fat, 'nfe:vOrig', ns, f"{total_val:.2f}")
        _set_text(cobr_fat, 'nfe:vLiq', ns, f"{total_val:.2f}")
    
    # --- Update INF ADIC (the KEY field with CNO) ---
    fed = trib_total * 0.4
    est = trib_total * 0.6
    tax_info = f"Empresa optante do Simples Nacional. Total aprox. tributos: R$ {trib_total:,.2f} ({trib_total/total_val*100:.2f}%) Federais R$ {fed:,.2f} Estaduais R$ {est:,.2f}. Fonte IBPT."
    
    if obra:
        cno_line = f"Referente a Obra: {obra['nome']}. CNO: {obra['cno']}. Entrega no local: {obra['endereco']}."
        inf_cpl_text = f"{cno_line} {tax_info}"
    else:
        inf_cpl_text = f"Venda balcao sem referencia de obra. {tax_info}"
    
    _set_text(infNFe, 'nfe:infAdic/nfe:infCpl', ns, inf_cpl_text)
    
    return root


def _set_text(parent, path, ns, value):
    """Set text content of element at path, creating if needed."""
    elem = parent.find(path, ns)
    if elem is not None:
        elem.text = value


def generate_test_batch():
    """
    Reads one real XML as template, then generates 10 construction scenarios.
    """
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    
    # Read a real XML as template
    real_zip = zipfile.ZipFile("xml_nfe_1771077455.zip", "r")
    template_name = real_zip.namelist()[0]
    with real_zip.open(template_name) as f:
        # Register namespace to avoid ns0: prefixes
        ET.register_namespace('', 'http://www.portalfiscal.inf.br/nfe')
        ET.register_namespace('ds', 'http://www.w3.org/2000/09/xmldsig#')
        template_root = ET.fromstring(f.read())
    real_zip.close()
    
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for spec in INVOICES:
            new_root = build_xml(spec, template_root, ns)
            xml_bytes = ET.tostring(new_root, encoding="utf-8", xml_declaration=True)
            
            # Create filename similar to real ones
            chave = f"1726021234567800017655001000000{spec['nNF']}1250{random.randint(100000,999999)}"
            z.writestr(f"{chave}-nfe.xml", xml_bytes)
    
    return output.getvalue()


if __name__ == "__main__":
    data = generate_test_batch()
    with open("lote_teste_obras.zip", "wb") as f:
        f.write(data)
    print(f"Arquivo 'lote_teste_obras.zip' criado com {len(INVOICES)} notas de teste.")
