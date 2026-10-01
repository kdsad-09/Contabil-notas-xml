"""
categorizer.py — Hikari Construções LTDA EPP
Expense codes extracted from official balancete (plano de contas 3.1.1).
Each obra center has its own set of short numeric codes (Código column).

Suporta plano de contas dinâmico: categorias e obras extras salvas em
plano_de_contas.json persistem entre sessões.
"""
import re
import json
import os
from typing import Optional

# Caminho do arquivo de persistência do plano de contas
_PLANO_JSON = os.path.join(os.path.dirname(__file__), "plano_de_contas.json")


def _normalize(text: str) -> str:
    """Lowercase and remove accents for keyword matching."""
    if not text:
        return ""
    t = text.lower()
    for a, b in [("á","a"),("à","a"),("â","a"),("ã","a"),
                 ("é","e"),("ê","e"),("í","i"),("ó","o"),
                 ("ô","o"),("õ","o"),("ú","u"),("ç","c")]:
        t = t.replace(a, b)
    return t


# ══════════════════════════════════════════════════════════════
# HIKARI — Expense types with keywords for auto-classification
# ══════════════════════════════════════════════════════════════
HIKARI_DESPESAS = {
    "001": ("DESPESAS COM COMBUSTIVEIS E LUBRIFICANTES", [
        "combustivel", "gasolina", "diesel", "oleo", "lubrificante",
        "graxa", "etanol", "alcool",
    ]),
    "002": ("DESPESAS COM CIMENTO CAL FERRO ARAME", [
        "cimento", "ferro", "arame", "aco", "vergalhao", "concreto",
        "argamassa", "cal", "cp ii", "cp iii", "cp iv", "tela soldada",
    ]),
    "003": ("DESPESAS COM MATERIAL ELETRICO", [
        "eletric", "fio", "cabo", "tomada", "disjuntor", "lampada",
        "luminaria", "eletroduto", "interruptor", "led", "sobrepor",
        "iluminacao", "quadro eletrico", "qdr",
    ]),
    "004": ("DESPESAS COM AREIA BRITA E SEIXO", [
        "areia", "brita", "seixo", "pedra", "cascalho", "agregado",
        "pedrisco", "rachao",
    ]),
    "005": ("DESPESAS COM MADEIRA", [
        "madeira", "tabua", "caibro", "ripa", "compensado", "mdf",
        "viga madeira", "pontalete", "sarrafo", "madeiras",
    ]),
    "006": ("DESPESAS COM TINTAS E VERNIZACAO", [
        "tinta", "verniz", "esmalte", "pincel", "rolo", "solvente",
        "lixa", "massa corrida", "textura", "impermeabilizante",
        "suvinil", "coral", "pintura", "vernizacao",
    ]),
    "007": ("DESPESAS COM FERRAMENTAS", [
        "ferramenta", "furadeira", "parafusadeira", "martelo", "alicate",
        "chave", "serra", "nivel", "trena", "marreta", "ferramentas",
    ]),
    "008": ("DESPESAS COM TIJOLOS", [
        "tijolo", "bloco", "bloco ceramico", "bloco concreto",
        "bloco estrutural", "tijolos",
    ]),
    "009": ("DESPESAS COM MATERIAL DIVERSOS", [
        "material diverso", "diversos", "parafuso", "prego", "silicone",
        "fita", "cola", "veda", "adesivo", "bucha", "itens diversos",
    ]),
    "010": ("DESPESAS COM PRODUTOS DE LIMPEZA", [
        "limpeza", "detergente", "desinfetante", "alvejante", "vassoura",
        "balde", "pano", "saponaceo",
    ]),
    "011": ("DESPESAS COM LOCACAO DE MAQUINAS E EQUIPAMENTOS", [
        "locacao", "aluguel", "betoneira", "andaime", "vibrador",
        "escora", "forma metalica", "mensal", "equipamento",
    ]),
    "012": ("DESPESAS COM REVESTIMENTOS E ACABAMENTOS", [
        "revestimento", "acabamento", "rejunte", "soleira", "rodape",
        "granito", "marmore", "forro",
    ]),
    "014": ("DESPESAS COM SERVICOS DE TERCEIRO", [
        "servico", "mao de obra", "instalacao", "manutencao",
        "engenharia", "prestacao", "terceiro", "empreitada",
    ]),
    "015": ("DESPESAS COM MATERIAL HIDRAULICO", [
        "hidraulic", "cano", "tubo pvc", "tubo soldavel", "conexao",
        "joelho", "torneira", "caixa d agua", "sifao", "registro",
        "esgoto", "fortlev", "tigre",
    ]),
    "016": ("DESPESAS COM TELHAS", [
        "telha", "cumeeira", "calha", "rufo", "cobertura", "telhas",
    ]),
    "017": ("DESPESAS COM ALIMENTACAO", [
        "alimentacao", "refeicao", "marmita", "alimento", "cesta basica",
        "rancho",
    ]),
    "018": ("DESPESAS COM PISOS EM GERAL", [
        "piso", "porcelanato", "azulejo", "ceramica", "laminado",
        "vinilico", "pisos",
    ]),
}

# Flat list of category names for UI dropdowns (base)
HIKARI_DESPESAS_LISTA = [desc for _, (desc, _) in sorted(HIKARI_DESPESAS.items())]

# Reverse lookup: category name → suffix
CODIGO_POR_DESPESA = {desc: suffix for suffix, (desc, _) in HIKARI_DESPESAS.items()}


# ══════════════════════════════════════════════════════════════
# HIKARI — Obra centers from balancete (Código + Classificação)
# ══════════════════════════════════════════════════════════════
HIKARI_OBRAS = {
    "3.1.1.01": (271,  "CUSTO DA OBRA GERAL"),
    "3.1.1.02": (273,  "CETEC SENAI ARAGUAINA"),
    "3.1.1.03": (285,  "ANFITEATRO SESI ARAGUAINA"),
    "3.1.1.04": (880,  "SEDE SESI SENAI PALMAS-TO"),
    "3.1.1.06": (900,  "ETI TAQUARI"),
    "3.1.1.07": (910,  "ETI PORTO LUZIMANGUES"),
    "3.1.1.08": (920,  "SESI DR GURUPI"),
    "3.1.1.09": (930,  "BLOCO IFTO ARAGUAINA"),
    "3.1.1.10": (940,  "REFORMA DUQUE DE CAXIAS II"),
    "3.1.1.11": (950,  "AMPLIACAO SEDE CREA PALMAS"),
    "3.1.1.12": (960,  "CICLOVIA CESAMAR"),
    "3.1.1.13": (970,  "CENTRO DE CONVENCOES PARAISO"),
    "3.1.1.14": (980,  "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA"),
    "3.1.1.21": (1978, "GUARITA SENAI CT GURUPI"),
}

HIKARI_OBRAS_LISTA = ["CUSTO DA OBRA GERAL"] + sorted(
    [name for cls, (code, name) in HIKARI_OBRAS.items() if cls != "3.1.1.01"]
)

# Reverse lookups
CODIGO_POR_OBRA = {name: cls for cls, (code, name) in HIKARI_OBRAS.items()}


# ══════════════════════════════════════════════════════════════
# SHORT CODES — (obra_nome, despesa_suffix) → código do balancete
# ══════════════════════════════════════════════════════════════
_CODIGOS_BALANCETE = {
    # ── CUSTO DA OBRA GERAL (3.1.1.01) ──
    ("CUSTO DA OBRA GERAL", "001"): 272,
    ("CUSTO DA OBRA GERAL", "002"): 1020,
    ("CUSTO DA OBRA GERAL", "003"): 1021,
    ("CUSTO DA OBRA GERAL", "004"): 1022,
    ("CUSTO DA OBRA GERAL", "005"): 1023,
    ("CUSTO DA OBRA GERAL", "006"): 1024,
    ("CUSTO DA OBRA GERAL", "007"): 1025,
    ("CUSTO DA OBRA GERAL", "008"): 1026,
    ("CUSTO DA OBRA GERAL", "009"): 1027,
    ("CUSTO DA OBRA GERAL", "010"): 1181,
    ("CUSTO DA OBRA GERAL", "011"): 1185,
    ("CUSTO DA OBRA GERAL", "012"): 1231,
    ("CUSTO DA OBRA GERAL", "014"): 1639,
    ("CUSTO DA OBRA GERAL", "015"): 1647,
    ("CUSTO DA OBRA GERAL", "016"): 1664,
    ("CUSTO DA OBRA GERAL", "017"): 1688,
    ("CUSTO DA OBRA GERAL", "018"): 1755,
    # ── CETEC SENAI ARAGUAINA (3.1.1.02) ──
    ("CETEC SENAI ARAGUAINA", "002"): 275,
    ("CETEC SENAI ARAGUAINA", "003"): 276,
    ("CETEC SENAI ARAGUAINA", "004"): 277,
    ("CETEC SENAI ARAGUAINA", "005"): 278,
    ("CETEC SENAI ARAGUAINA", "006"): 279,
    ("CETEC SENAI ARAGUAINA", "007"): 280,
    ("CETEC SENAI ARAGUAINA", "008"): 281,
    ("CETEC SENAI ARAGUAINA", "009"): 282,
    ("CETEC SENAI ARAGUAINA", "010"): 497,
    ("CETEC SENAI ARAGUAINA", "011"): 1182,
    ("CETEC SENAI ARAGUAINA", "012"): 1186,
    ("CETEC SENAI ARAGUAINA", "015"): 1232,
    # ── ANFITEATRO SESI ARAGUAINA (3.1.1.03) ──
    ("ANFITEATRO SESI ARAGUAINA", "001"): 871,
    ("ANFITEATRO SESI ARAGUAINA", "002"): 872,
    ("ANFITEATRO SESI ARAGUAINA", "003"): 873,
    ("ANFITEATRO SESI ARAGUAINA", "005"): 875,
    ("ANFITEATRO SESI ARAGUAINA", "006"): 876,
    ("ANFITEATRO SESI ARAGUAINA", "007"): 877,
    ("ANFITEATRO SESI ARAGUAINA", "008"): 878,
    ("ANFITEATRO SESI ARAGUAINA", "009"): 879,
    ("ANFITEATRO SESI ARAGUAINA", "010"): 1187,
    ("ANFITEATRO SESI ARAGUAINA", "012"): 1233,
    ("ANFITEATRO SESI ARAGUAINA", "014"): 1646,
    ("ANFITEATRO SESI ARAGUAINA", "015"): 1669,
    ("ANFITEATRO SESI ARAGUAINA", "016"): 1757,
    # ── SEDE SESI SENAI PALMAS-TO (3.1.1.04) ──
    ("SEDE SESI SENAI PALMAS-TO", "002"): 882,
    ("SEDE SESI SENAI PALMAS-TO", "003"): 883,
    ("SEDE SESI SENAI PALMAS-TO", "004"): 884,
    ("SEDE SESI SENAI PALMAS-TO", "005"): 885,
    ("SEDE SESI SENAI PALMAS-TO", "006"): 886,
    ("SEDE SESI SENAI PALMAS-TO", "007"): 887,
    ("SEDE SESI SENAI PALMAS-TO", "008"): 888,
    ("SEDE SESI SENAI PALMAS-TO", "009"): 889,
    ("SEDE SESI SENAI PALMAS-TO", "010"): 1189,
    ("SEDE SESI SENAI PALMAS-TO", "012"): 1234,
    # ── ETI TAQUARI (3.1.1.06) ──
    ("ETI TAQUARI", "002"): 902,
    ("ETI TAQUARI", "003"): 903,
    ("ETI TAQUARI", "004"): 904,
    ("ETI TAQUARI", "005"): 905,
    ("ETI TAQUARI", "006"): 906,
    ("ETI TAQUARI", "007"): 907,
    ("ETI TAQUARI", "008"): 908,
    ("ETI TAQUARI", "009"): 909,
    ("ETI TAQUARI", "010"): 1180,
    ("ETI TAQUARI", "011"): 1193,
    ("ETI TAQUARI", "012"): 1206,
    # ── ETI PORTO LUZIMANGUES (3.1.1.07) ──
    ("ETI PORTO LUZIMANGUES", "002"): 912,
    ("ETI PORTO LUZIMANGUES", "003"): 913,
    ("ETI PORTO LUZIMANGUES", "004"): 914,
    ("ETI PORTO LUZIMANGUES", "005"): 915,
    ("ETI PORTO LUZIMANGUES", "006"): 916,
    ("ETI PORTO LUZIMANGUES", "007"): 917,
    ("ETI PORTO LUZIMANGUES", "008"): 918,
    ("ETI PORTO LUZIMANGUES", "009"): 919,
    ("ETI PORTO LUZIMANGUES", "010"): 1194,
    ("ETI PORTO LUZIMANGUES", "012"): 1237,
    ("ETI PORTO LUZIMANGUES", "014"): 1655,
    ("ETI PORTO LUZIMANGUES", "015"): 1760,
    # ── SESI DR GURUPI (3.1.1.08) ──
    ("SESI DR GURUPI", "002"): 922,
    ("SESI DR GURUPI", "003"): 923,
    ("SESI DR GURUPI", "004"): 924,
    ("SESI DR GURUPI", "005"): 925,
    ("SESI DR GURUPI", "006"): 926,
    ("SESI DR GURUPI", "007"): 927,
    ("SESI DR GURUPI", "008"): 928,
    ("SESI DR GURUPI", "009"): 929,
    ("SESI DR GURUPI", "010"): 1196,
    ("SESI DR GURUPI", "012"): 1238,
    ("SESI DR GURUPI", "014"): 1665,
    ("SESI DR GURUPI", "016"): 1856,
    # ── BLOCO IFTO ARAGUAINA (3.1.1.09) ──
    ("BLOCO IFTO ARAGUAINA", "002"): 932,
    ("BLOCO IFTO ARAGUAINA", "003"): 933,
    ("BLOCO IFTO ARAGUAINA", "004"): 934,
    ("BLOCO IFTO ARAGUAINA", "005"): 935,
    ("BLOCO IFTO ARAGUAINA", "006"): 936,
    ("BLOCO IFTO ARAGUAINA", "007"): 937,
    ("BLOCO IFTO ARAGUAINA", "009"): 939,
    ("BLOCO IFTO ARAGUAINA", "010"): 1198,
    ("BLOCO IFTO ARAGUAINA", "012"): 1239,
    ("BLOCO IFTO ARAGUAINA", "014"): 1648,
    ("BLOCO IFTO ARAGUAINA", "015"): 1663,
    ("BLOCO IFTO ARAGUAINA", "016"): 1762,
    # ── REFORMA DUQUE DE CAXIAS II (3.1.1.10) ──
    ("REFORMA DUQUE DE CAXIAS II", "002"): 942,
    ("REFORMA DUQUE DE CAXIAS II", "003"): 943,
    ("REFORMA DUQUE DE CAXIAS II", "004"): 944,
    # ── AMPLIACAO SEDE CREA PALMAS (3.1.1.11) ──
    ("AMPLIACAO SEDE CREA PALMAS", "002"): 952,
    ("AMPLIACAO SEDE CREA PALMAS", "003"): 953,
    ("AMPLIACAO SEDE CREA PALMAS", "004"): 954,
    ("AMPLIACAO SEDE CREA PALMAS", "005"): 955,
    ("AMPLIACAO SEDE CREA PALMAS", "006"): 956,
    ("AMPLIACAO SEDE CREA PALMAS", "007"): 957,
    ("AMPLIACAO SEDE CREA PALMAS", "008"): 958,
    ("AMPLIACAO SEDE CREA PALMAS", "009"): 959,
    ("AMPLIACAO SEDE CREA PALMAS", "010"): 1202,
    ("AMPLIACAO SEDE CREA PALMAS", "012"): 1241,
    ("AMPLIACAO SEDE CREA PALMAS", "014"): 1721,
    ("AMPLIACAO SEDE CREA PALMAS", "015"): 1764,
    # ── CICLOVIA CESAMAR (3.1.1.12) ──
    ("CICLOVIA CESAMAR", "002"): 962,
    ("CICLOVIA CESAMAR", "003"): 963,
    ("CICLOVIA CESAMAR", "004"): 964,
    ("CICLOVIA CESAMAR", "006"): 966,
    ("CICLOVIA CESAMAR", "007"): 967,
    ("CICLOVIA CESAMAR", "009"): 969,
    ("CICLOVIA CESAMAR", "012"): 1242,
    ("CICLOVIA CESAMAR", "016"): 1675,
    # ── CENTRO DE CONVENCOES PARAISO (3.1.1.13) ──
    ("CENTRO DE CONVENCOES PARAISO", "002"): 972,
    ("CENTRO DE CONVENCOES PARAISO", "003"): 973,
    ("CENTRO DE CONVENCOES PARAISO", "006"): 976,
    ("CENTRO DE CONVENCOES PARAISO", "007"): 978,
    ("CENTRO DE CONVENCOES PARAISO", "008"): 979,
    ("CENTRO DE CONVENCOES PARAISO", "009"): 1206,
    ("CENTRO DE CONVENCOES PARAISO", "010"): 1243,
    # ── CENTRO DE ATEND. SOCIOEDUCATIVO DE ARAGUAINA (3.1.1.14) ──
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "002"): 982,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "003"): 983,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "004"): 984,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "005"): 985,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "006"): 986,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "007"): 987,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "008"): 988,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "009"): 989,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "010"): 1208,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "012"): 1244,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "014"): 1649,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "015"): 1654,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "016"): 1674,
    ("CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA", "017"): 1670,
    # ── GUARITA SENAI CT GURUPI (3.1.1.21) ──
    ("GUARITA SENAI CT GURUPI", "002"): 1980,
    ("GUARITA SENAI CT GURUPI", "003"): 1981,
    ("GUARITA SENAI CT GURUPI", "006"): 1984,
    ("GUARITA SENAI CT GURUPI", "009"): 1987,
    ("GUARITA SENAI CT GURUPI", "012"): 1990,
    ("GUARITA SENAI CT GURUPI", "015"): 1991,
}


# ══════════════════════════════════════════════════════════════
# PERSISTÊNCIA DO PLANO DE CONTAS (JSON)
# ══════════════════════════════════════════════════════════════

def load_plano_json() -> dict:
    """Carrega o plano de contas extra do arquivo JSON."""
    if os.path.exists(_PLANO_JSON):
        try:
            with open(_PLANO_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"categorias_extras": [], "obras_extras": []}


def save_plano_json(data: dict) -> None:
    """Salva o plano de contas extra no arquivo JSON."""
    with open(_PLANO_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_categorias(extra_cats: list) -> list:
    """Retorna a lista completa de categorias (base + extras)."""
    base = list(HIKARI_DESPESAS_LISTA)
    for item in extra_cats:
        nome = item.get("nome", "").strip().upper()
        if nome and nome not in base:
            base.append(nome)
    return base


def get_all_obras(extra_obras: list) -> list:
    """Retorna a lista completa de obras (base + extras)."""
    base = list(HIKARI_OBRAS_LISTA)
    for item in extra_obras:
        nome = item.get("nome", "").strip().upper()
        if nome and nome not in base:
            base.append(nome)
    return base


def get_codigo_contabil(categoria: str, obra_nome: Optional[str] = None,
                        extra_cats: Optional[list] = None) -> str:
    """
    Returns the short numeric code (Código column from balancete)
    for a given category + obra combination.

    If the specific combo is not in the balancete, falls back to OBRA GERAL code.
    If still not found, returns the suffix number (or empty for custom categories).

    Returns a tuple: (codigo_str, is_fallback: bool)
    Wrapped in a simple string — caller checks for prefix "~" to detect fallback.
    """
    if not obra_nome:
        obra_nome = "CUSTO DA OBRA GERAL"

    # Verifica categorias extras (código personalizado)
    if extra_cats:
        for item in extra_cats:
            if item.get("nome", "").strip().upper() == categoria:
                cod = item.get("codigo", "").strip()
                return cod if cod else ""

    suffix = CODIGO_POR_DESPESA.get(categoria)
    if not suffix:
        return ""  # custom category not in balancete

    # Try exact obra + despesa match
    code = _CODIGOS_BALANCETE.get((obra_nome, suffix))
    if code is not None:
        return str(code)

    # Fallback: usa OBRA GERAL — prefixo "~" indica fallback visual
    code = _CODIGOS_BALANCETE.get(("CUSTO DA OBRA GERAL", suffix))
    if code is not None:
        return f"~{code}"  # "~" indica que é código de fallback (obra geral)

    return suffix  # last resort


def categorize_invoice(items_list: list, inf_adic: str, cno: str):
    """
    Suggests a Hikari expense category based on items and additional info.
    Returns: (Category name, Explanation)
    """
    raw = " ".join(items_list) + " " + (inf_adic or "")
    text = _normalize(raw)

    scores: dict[str, int] = {}
    for code, (desc, keywords) in HIKARI_DESPESAS.items():
        score: int = 0
        for kw in keywords:
            if kw in text:
                score += 1
        scores[desc] = score

    best_cat: str = max(scores, key=lambda k: scores[k])

    if scores[best_cat] > 0:
        return best_cat, f"Detectado via palavras-chave (Score: {scores[best_cat]})"
    else:
        return "DESPESAS COM MATERIAL DIVERSOS", "Nenhuma palavra-chave especifica identificada"


def suggest_project(inf_adic: str, cno: str):
    """
    Suggests the Obra based on CNO or contents of infAdic.
    If no CNO → "CUSTO DA OBRA GERAL"
    """
    obra_name = None

    if inf_adic:
        match = re.search(
            r'(?:referente\s+a\s+obra|obra|projeto)\s*[:\-]?\s*([^.;,\n]+)',
            inf_adic, re.IGNORECASE
        )
        if match:
            name = match.group(1).strip()
            name = re.sub(r'\s*CNO.*$', '', name, flags=re.IGNORECASE).strip()
            if len(name) > 3:
                obra_name = name

        text_upper = inf_adic.upper()
        for cls, (code, name) in HIKARI_OBRAS.items():
            if cls != "3.1.1.01" and name in text_upper:
                return name, f"Identificado via nome da obra no infAdic (Codigo: {code})"

    if cno and obra_name:
        return f"{obra_name} (CNO: {cno})", "Identificado via infAdic + CNO"
    elif cno:
        return f"Obra CNO: {cno}", "Identificado via codigo CNO"

    return "CUSTO DA OBRA GERAL", "CNO nao identificado — classificado como Obra Geral"
