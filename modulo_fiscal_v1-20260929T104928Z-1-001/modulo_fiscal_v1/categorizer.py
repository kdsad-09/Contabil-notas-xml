"""
categorizer.py — Hikari Construções LTDA EPP

Classificação de despesas e obras para o Catraca Fiscal.

Compatível com app.py:
- categorize_invoice
- suggest_project
- HIKARI_DESPESAS_LISTA
- HIKARI_OBRAS_LISTA
- get_codigo_contabil
- HIKARI_DESPESAS
- HIKARI_OBRAS
- CODIGO_POR_OBRA

Também mantém:
- plano de contas dinâmico;
- persistência em plano_de_contas.json;
- códigos contábeis do balancete;
- classificação prioritária de tijolos/blocos;
- classificação de ferro/aço/vergalhão/arame;
- CIMENTO NÃO é usado para classificar na categoria 002.
"""

import json
import os
import re
import unicodedata
from typing import Optional


# ============================================================
# ARQUIVO DE PERSISTÊNCIA
# ============================================================

_PLANO_JSON = os.path.join(
    os.path.dirname(__file__),
    "plano_de_contas.json"
)


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def _normalize(text: str) -> str:
    """
    Normaliza texto:
    - minúsculas;
    - remove acentos;
    - troca pontuação por espaço;
    - remove espaços duplicados.
    """
    if text is None:
        return ""

    text = str(text).lower()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


# Compatibilidade com versões anteriores
def _texto_normalizado(texto):
    return _normalize(texto)


def _keyword_pattern(keyword: str) -> str:
    """
    Cria regex segura para palavra/frase inteira.

    Exemplo:
        'barra de aço'
    vira uma expressão que também funciona após remover acentos.
    """
    keyword = _normalize(keyword)

    if not keyword:
        return ""

    partes = keyword.split()

    return (
        r"\b"
        + r"\s+".join(re.escape(parte) for parte in partes)
        + r"\b"
    )


def _contains_keyword(text: str, keyword: str) -> bool:
    text = _normalize(text)
    pattern = _keyword_pattern(keyword)

    if not pattern:
        return False

    return bool(re.search(pattern, text))


# ============================================================
# HIKARI — CATEGORIAS DE DESPESA
# ============================================================

HIKARI_DESPESAS = {

    "001": (
        "DESPESAS COM COMBUSTIVEIS E LUBRIFICANTES",
        [
            "combustivel",
            "gasolina",
            "diesel",
            "oleo",
            "lubrificante",
            "graxa",
            "etanol",
            "alcool",
        ],
    ),

    # IMPORTANTE:
    # Apesar do nome histórico conter CIMENTO e CAL,
    # esta categoria será utilizada nas regras automáticas
    # somente para FERRO / AÇO / ARAME / VERGALHÃO.
    "002": (
        "DESPESAS COM CIMENTO CAL FERRO ARAME",
        [
            "ferro",
            "arame",
            "aco",
            "vergalhao",
            "vergalhoes",
            "barra de ferro",
            "barras de ferro",
            "barra de aco",
            "barras de aco",
            "perfil de aco",
            "perfil metalico",
            "cantoneira",
            "metalao",
            "trelica",
            "tela soldada",
            "tela soldada galvanizada",
            "tela galvanizada",
            "ferro redondo",
            "ferro chato",
            "ferro quadrado",
            "ferro mecanico",
            "aco carbono",
        ],
    ),

    "003": (
        "DESPESAS COM MATERIAL ELETRICO",
        [
            "eletric",
            "fio",
            "cabo",
            "tomada",
            "disjuntor",
            "lampada",
            "luminaria",
            "eletroduto",
            "interruptor",
            "led",
            "sobrepor",
            "iluminacao",
            "quadro eletrico",
            "qdr",
        ],
    ),

    "004": (
        "DESPESAS COM AREIA BRITA E SEIXO",
        [
            "areia",
            "brita",
            "seixo",
            "pedra",
            "cascalho",
            "agregado",
            "pedrisco",
            "rachao",
        ],
    ),

    "005": (
        "DESPESAS COM MADEIRA",
        [
            "madeira",
            "tabua",
            "caibro",
            "ripa",
            "compensado",
            "mdf",
            "viga madeira",
            "pontalete",
            "sarrafo",
            "madeiras",
        ],
    ),

    "006": (
        "DESPESAS COM TINTAS E VERNIZACAO",
        [
            "tinta",
            "verniz",
            "esmalte",
            "pincel",
            "rolo",
            "solvente",
            "lixa",
            "massa corrida",
            "textura",
            "impermeabilizante",
            "suvinil",
            "coral",
            "pintura",
            "vernizacao",
        ],
    ),

    "007": (
        "DESPESAS COM FERRAMENTAS",
        [
            "ferramenta",
            "furadeira",
            "parafusadeira",
            "martelo",
            "alicate",
            "chave",
            "serra",
            "nivel",
            "trena",
            "marreta",
            "ferramentas",
        ],
    ),

    "008": (
        "DESPESAS COM TIJOLOS",
        [
            "tijolo",
            "tijolos",
            "bloco",
            "bloco ceramico",
            "bloco de ceramica",
            "bloco concreto",
            "bloco de concreto",
            "bloco estrutural",
            "blocos estruturais",
        ],
    ),

    "009": (
        "DESPESAS COM MATERIAL DIVERSOS",
        [
            "material diverso",
            "diversos",
            "parafuso",
            "prego",
            "silicone",
            "fita",
            "cola",
            "veda",
            "adesivo",
            "bucha",
            "itens diversos",
        ],
    ),

    "010": (
        "DESPESAS COM PRODUTOS DE LIMPEZA",
        [
            "limpeza",
            "detergente",
            "desinfetante",
            "alvejante",
            "vassoura",
            "balde",
            "pano",
            "saponaceo",
        ],
    ),

    "011": (
        "DESPESAS COM LOCACAO DE MAQUINAS E EQUIPAMENTOS",
        [
            "locacao",
            "aluguel",
            "betoneira",
            "andaime",
            "vibrador",
            "escora",
            "forma metalica",
            "mensal",
            "equipamento",
        ],
    ),

    "012": (
        "DESPESAS COM REVESTIMENTOS E ACABAMENTOS",
        [
            "revestimento",
            "acabamento",
            "rejunte",
            "soleira",
            "rodape",
            "granito",
            "marmore",
            "forro",
        ],
    ),

    "014": (
        "DESPESAS COM SERVICOS DE TERCEIRO",
        [
            "servico",
            "mao de obra",
            "instalacao",
            "manutencao",
            "engenharia",
            "prestacao",
            "terceiro",
            "empreitada",
        ],
    ),

    "015": (
        "DESPESAS COM MATERIAL HIDRAULICO",
        [
            "hidraulic",
            "cano",
            "tubo pvc",
            "tubo soldavel",
            "conexao",
            "joelho",
            "torneira",
            "caixa d agua",
            "sifao",
            "registro",
            "esgoto",
            "fortlev",
            "tigre",
        ],
    ),

    "016": (
        "DESPESAS COM TELHAS",
        [
            "telha",
            "cumeeira",
            "calha",
            "rufo",
            "cobertura",
            "telhas",
        ],
    ),

    "017": (
        "DESPESAS COM ALIMENTACAO",
        [
            "alimentacao",
            "refeicao",
            "marmita",
            "alimento",
            "cesta basica",
            "rancho",
        ],
    ),

    "018": (
        "DESPESAS COM PISOS EM GERAL",
        [
            "piso",
            "porcelanato",
            "azulejo",
            "ceramica",
            "laminado",
            "vinilico",
            "pisos",
        ],
    ),
}


# Lista usada pelos dropdowns do app.py
HIKARI_DESPESAS_LISTA = [
    desc
    for _, (desc, _) in sorted(HIKARI_DESPESAS.items())
]


# Categoria -> sufixo contábil
CODIGO_POR_DESPESA = {
    desc: suffix
    for suffix, (desc, _) in HIKARI_DESPESAS.items()
}


# ============================================================
# HIKARI — OBRAS
# ============================================================

HIKARI_OBRAS = {

    "3.1.1.01": (
        271,
        "CUSTO DA OBRA GERAL"
    ),

    "3.1.1.02": (
        273,
        "CETEC SENAI ARAGUAINA"
    ),

    "3.1.1.03": (
        285,
        "ANFITEATRO SESI ARAGUAINA"
    ),

    "3.1.1.04": (
        880,
        "SEDE SESI SENAI PALMAS-TO"
    ),

    "3.1.1.06": (
        900,
        "ETI TAQUARI"
    ),

    "3.1.1.07": (
        910,
        "ETI PORTO LUZIMANGUES"
    ),

    "3.1.1.08": (
        920,
        "SESI DR GURUPI"
    ),

    "3.1.1.09": (
        930,
        "BLOCO IFTO ARAGUAINA"
    ),

    "3.1.1.10": (
        940,
        "REFORMA DUQUE DE CAXIAS II"
    ),

    "3.1.1.11": (
        950,
        "AMPLIACAO SEDE CREA PALMAS"
    ),

    "3.1.1.12": (
        960,
        "CICLOVIA CESAMAR"
    ),

    "3.1.1.13": (
        970,
        "CENTRO DE CONVENCOES PARAISO"
    ),

    "3.1.1.14": (
        980,
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA"
    ),

    "3.1.1.21": (
        1978,
        "GUARITA SENAI CT GURUPI"
    ),
}


HIKARI_OBRAS_LISTA = [
    "CUSTO DA OBRA GERAL"
] + sorted(
    [
        name
        for cls, (code, name) in HIKARI_OBRAS.items()
        if cls != "3.1.1.01"
    ]
)


# Nome da obra -> classificação contábil
CODIGO_POR_OBRA = {
    name: cls
    for cls, (code, name) in HIKARI_OBRAS.items()
}


# ============================================================
# CÓDIGOS DO BALANCETE
# ============================================================

_CODIGOS_BALANCETE = {

    # CUSTO DA OBRA GERAL
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

    # CETEC SENAI ARAGUAINA
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

    # ANFITEATRO SESI ARAGUAINA
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

    # SEDE SESI SENAI PALMAS
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

    # ETI TAQUARI
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

    # ETI PORTO LUZIMANGUES
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

    # SESI DR GURUPI
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

    # BLOCO IFTO ARAGUAINA
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

    # REFORMA DUQUE DE CAXIAS II
    ("REFORMA DUQUE DE CAXIAS II", "002"): 942,
    ("REFORMA DUQUE DE CAXIAS II", "003"): 943,
    ("REFORMA DUQUE DE CAXIAS II", "004"): 944,

    # AMPLIACAO SEDE CREA PALMAS
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

    # CICLOVIA CESAMAR
    ("CICLOVIA CESAMAR", "002"): 962,
    ("CICLOVIA CESAMAR", "003"): 963,
    ("CICLOVIA CESAMAR", "004"): 964,
    ("CICLOVIA CESAMAR", "006"): 966,
    ("CICLOVIA CESAMAR", "007"): 967,
    ("CICLOVIA CESAMAR", "009"): 969,
    ("CICLOVIA CESAMAR", "012"): 1242,
    ("CICLOVIA CESAMAR", "016"): 1675,

    # CENTRO DE CONVENCOES PARAISO
    ("CENTRO DE CONVENCOES PARAISO", "002"): 972,
    ("CENTRO DE CONVENCOES PARAISO", "003"): 973,
    ("CENTRO DE CONVENCOES PARAISO", "006"): 976,
    ("CENTRO DE CONVENCOES PARAISO", "007"): 978,
    ("CENTRO DE CONVENCOES PARAISO", "008"): 979,
    ("CENTRO DE CONVENCOES PARAISO", "009"): 1206,
    ("CENTRO DE CONVENCOES PARAISO", "010"): 1243,

    # CENTRO SOCIOEDUCATIVO ARAGUAINA
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

    # GUARITA SENAI CT GURUPI
    ("GUARITA SENAI CT GURUPI", "002"): 1980,
    ("GUARITA SENAI CT GURUPI", "003"): 1981,
    ("GUARITA SENAI CT GURUPI", "006"): 1984,
    ("GUARITA SENAI CT GURUPI", "009"): 1987,
    ("GUARITA SENAI CT GURUPI", "012"): 1990,
    ("GUARITA SENAI CT GURUPI", "015"): 1991,
}


# ============================================================
# PERSISTÊNCIA DO PLANO DE CONTAS
# ============================================================

def load_plano_json() -> dict:
    """
    Carrega categorias e obras extras.
    """

    if os.path.exists(_PLANO_JSON):

        try:

            with open(
                _PLANO_JSON,
                "r",
                encoding="utf-8"
            ) as arquivo:

                dados = json.load(arquivo)

                if isinstance(dados, dict):
                    return dados

        except Exception:
            pass

    return {
        "categorias_extras": [],
        "obras_extras": [],
    }


def save_plano_json(data: dict) -> None:
    """
    Salva categorias e obras extras.
    """

    with open(
        _PLANO_JSON,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            data,
            arquivo,
            ensure_ascii=False,
            indent=2
        )


def get_all_categorias(extra_cats: Optional[list] = None) -> list:
    """
    Retorna categorias base + categorias extras.
    """

    base = list(HIKARI_DESPESAS_LISTA)

    for item in (extra_cats or []):

        if not isinstance(item, dict):
            continue

        nome = (
            item.get("nome", "")
            .strip()
            .upper()
        )

        if nome and nome not in base:
            base.append(nome)

    return base


def get_all_obras(extra_obras: Optional[list] = None) -> list:
    """
    Retorna obras base + obras extras.
    """

    base = list(HIKARI_OBRAS_LISTA)

    for item in (extra_obras or []):

        if not isinstance(item, dict):
            continue

        nome = (
            item.get("nome", "")
            .strip()
            .upper()
        )

        if nome and nome not in base:
            base.append(nome)

    return base


# ============================================================
# CÓDIGO CONTÁBIL
# ============================================================

def get_codigo_contabil(
    categoria: str,
    obra_nome: Optional[str] = None,
    extra_cats: Optional[list] = None,
) -> str:

    """
    Retorna o código contábil da categoria dentro da obra.

    Se a combinação específica não existir,
    utiliza o código da OBRA GERAL com prefixo "~".
    """

    categoria = str(categoria or "").strip().upper()

    if not obra_nome:
        obra_nome = "CUSTO DA OBRA GERAL"

    obra_nome = str(obra_nome).strip().upper()

    # --------------------------------------------------------
    # CATEGORIAS PERSONALIZADAS
    # --------------------------------------------------------

    for item in (extra_cats or []):

        if not isinstance(item, dict):
            continue

        nome = (
            item.get("nome", "")
            .strip()
            .upper()
        )

        if nome == categoria:

            codigo = str(
                item.get("codigo", "")
            ).strip()

            return codigo

    # --------------------------------------------------------
    # CATEGORIA PADRÃO
    # --------------------------------------------------------

    suffix = CODIGO_POR_DESPESA.get(categoria)

    if not suffix:
        return ""

    # Código exato da obra
    codigo = _CODIGOS_BALANCETE.get(
        (obra_nome, suffix)
    )

    if codigo is not None:
        return str(codigo)

    # Fallback para obra geral
    codigo = _CODIGOS_BALANCETE.get(
        ("CUSTO DA OBRA GERAL", suffix)
    )

    if codigo is not None:
        return f"~{codigo}"

    return suffix


# ============================================================
# REGRAS PRIORITÁRIAS DE MATERIAL
# ============================================================

REGRAS_MATERIAIS_PRIORITARIAS = [

    # --------------------------------------------------------
    # TIJOLOS / BLOCOS
    #
    # Esta regra vem primeiro propositalmente.
    # Assim "BLOCO DE CONCRETO" não é confundido com
    # qualquer outra categoria.
    # --------------------------------------------------------

    (
        "DESPESAS COM TIJOLOS",
        [
            r"\btijolos?\b",
            r"\bblocos?\s+ceramicos?\b",
            r"\bblocos?\s+de\s+ceramica\b",
            r"\bblocos?\s+concreto\b",
            r"\bblocos?\s+de\s+concreto\b",
            r"\bblocos?\s+estruturais?\b",
        ],
    ),

    # --------------------------------------------------------
    # FERRO / AÇO / VERGALHÃO / ARAME
    # --------------------------------------------------------

    (
        "DESPESAS COM CIMENTO CAL FERRO ARAME",
        [
            r"\bvergalhoes?\b",
            r"\bferro\b",
            r"\barame\b",
            r"\baco\b",
            r"\bbarras?\s+de\s+ferro\b",
            r"\bbarras?\s+de\s+aco\b",
            r"\bperfil\s+de\s+aco\b",
            r"\bperfil\s+metalico\b",
            r"\bcantoneira\b",
            r"\bmetalao\b",
            r"\btrelica\b",
            r"\btela\s+soldada\b",
            r"\btela\s+galvanizada\b",
            r"\bferro\s+redondo\b",
            r"\bferro\s+chato\b",
            r"\bferro\s+quadrado\b",
            r"\bferro\s+mecanico\b",
            r"\baco\s+carbono\b",
        ],
    ),
]


def _encontrar_categoria_prioritaria(texto):
    """
    Procura categorias que precisam de precedência.
    """

    texto = _normalize(texto)

    if not texto:
        return None

    for categoria, padroes in REGRAS_MATERIAIS_PRIORITARIAS:

        for padrao in padroes:

            if re.search(padrao, texto):
                return categoria

    return None


# ============================================================
# CLASSIFICAÇÃO DE DESPESA
# ============================================================

def categorize_invoice(
    items_list,
    inf_adic="",
    cno=""
):
    """
    Classifica uma NF na categoria de despesa Hikari.

    IMPORTANTE PARA O app.py ATUAL:

    O app.py pode passar um contexto XML inteiro dentro de
    items_list. Por isso esta função aceita tanto descrições
    simples quanto o contexto enriquecido.

    Prioridades:

    1. Tijolo/bloco;
    2. Ferro/aço/vergalhão/arame;
    3. Demais categorias por palavras-chave;
    4. Material diversos.

    CIMENTO e CAL NÃO classificam automaticamente na 002.
    """

    # --------------------------------------------------------
    # NORMALIZA ENTRADA
    # --------------------------------------------------------

    if items_list is None:
        items_list = []

    if isinstance(items_list, str):
        items_list = [items_list]

    itens_validos = []

    for item in items_list:

        if item is None:
            continue

        texto = str(item).strip()

        if texto:
            itens_validos.append(texto)

    # --------------------------------------------------------
    # TEXTO DOS ITENS
    # --------------------------------------------------------

    texto_itens = " ".join(itens_validos)

    # --------------------------------------------------------
    # 1. TIJOLO / BLOCO
    # --------------------------------------------------------

    texto_normalizado = _normalize(texto_itens)

    padroes_tijolo = [
        r"\btijolos?\b",
        r"\bblocos?\s+ceramicos?\b",
        r"\bblocos?\s+de\s+ceramica\b",
        r"\bblocos?\s+concreto\b",
        r"\bblocos?\s+de\s+concreto\b",
        r"\bblocos?\s+estruturais?\b",
    ]

    for padrao in padroes_tijolo:

        if re.search(padrao, texto_normalizado):

            return (
                "DESPESAS COM TIJOLOS",
                "Classificação direta: tijolo/bloco identificado nos itens da NF."
            )

    # --------------------------------------------------------
    # 2. FERRO / AÇO / ARAME / VERGALHÃO
    # --------------------------------------------------------

    padroes_ferro = [
        r"\bvergalhoes?\b",
        r"\bferro\b",
        r"\barame\b",
        r"\baco\b",
        r"\bbarras?\s+de\s+ferro\b",
        r"\bbarras?\s+de\s+aco\b",
        r"\bperfil\s+de\s+aco\b",
        r"\bperfil\s+metalico\b",
        r"\bcantoneira\b",
        r"\bmetalao\b",
        r"\btrelica\b",
        r"\btela\s+soldada\b",
        r"\btela\s+galvanizada\b",
        r"\bferro\s+redondo\b",
        r"\bferro\s+chato\b",
        r"\bferro\s+quadrado\b",
        r"\bferro\s+mecanico\b",
        r"\baco\s+carbono\b",
    ]

    for padrao in padroes_ferro:

        if re.search(padrao, texto_normalizado):

            return (
                "DESPESAS COM CIMENTO CAL FERRO ARAME",
                "Classificação direta: ferro/aço/vergalhão/arame identificado nos itens da NF."
            )

    # --------------------------------------------------------
    # 3. CLASSIFICAÇÃO GENÉRICA
    # --------------------------------------------------------

    scores = {}

    for codigo, (descricao, keywords) in HIKARI_DESPESAS.items():

        score = 0

        for keyword in keywords:

            keyword_normalizada = _normalize(keyword)

            if not keyword_normalizada:
                continue

            pattern = _keyword_pattern(
                keyword_normalizada
            )

            if pattern and re.search(
                pattern,
                texto_normalizado
            ):
                score += 1

        scores[descricao] = score

    # --------------------------------------------------------
    # MELHOR CATEGORIA
    # --------------------------------------------------------

    if scores:

        melhor_categoria = max(
            scores,
            key=scores.get
        )

        melhor_score = scores[
            melhor_categoria
        ]

        if melhor_score > 0:

            return (
                melhor_categoria,
                f"Detectado via palavras-chave dos itens (Score: {melhor_score})."
            )

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    return (
        "DESPESAS COM MATERIAL DIVERSOS",
        "Nenhuma regra de material foi identificada."
    )


# ============================================================
# SUGESTÃO DE OBRA
# ============================================================

# Apelidos adicionais para melhorar identificação pelo XML.
#
# A chave precisa ser exatamente o nome existente em HIKARI_OBRAS.
_OBRA_ALIASES = {

    "CETEC SENAI ARAGUAINA": [
        "cetec senai araguaina",
        "cetec araguaina",
    ],

    "ANFITEATRO SESI ARAGUAINA": [
        "anfiteatro sesi araguaina",
        "anfiteatro araguaina",
    ],

    "SEDE SESI SENAI PALMAS-TO": [
        "sede sesi senai palmas",
        "sesi senai palmas",
    ],

    "ETI TAQUARI": [
        "eti taquari",
        "taquari",
    ],

    "ETI PORTO LUZIMANGUES": [
        "eti porto luzimangues",
        "porto luzimangues",
        "luzimangues",
    ],

    "SESI DR GURUPI": [
        "sesi dr gurupi",
        "sesi gurupi",
    ],

    "BLOCO IFTO ARAGUAINA": [
        "bloco ifto araguaina",
        "ifto araguaina",
    ],

    "REFORMA DUQUE DE CAXIAS II": [
        "reforma duque de caxias ii",
        "duque de caxias ii",
        "duque de caxias",
    ],

    "AMPLIACAO SEDE CREA PALMAS": [
        "ampliacao sede crea palmas",
        "sede crea palmas",
        "crea palmas",
    ],

    "CICLOVIA CESAMAR": [
        "ciclovia cesamar",
        "cesamar",
    ],

    "CENTRO DE CONVENCOES PARAISO": [
        "centro de convencoes paraiso",
        "convencoes paraiso",
    ],

    "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA": [
        "centro de atendimento socioeducativo de araguaina",
        "socioeducativo de araguaina",
        "socioeducativo araguaina",
    ],

    "GUARITA SENAI CT GURUPI": [
        "guarita senai ct gurupi",
        "guarita senai gurupi",
    ],
}


def suggest_project(
    inf_adic="",
    cno=""
):
    """
    Sugere a obra a partir do texto/contexto XML.

    Assinatura compatível com app.py:

        suggest_project(texto_busca, cno)

    Retorna:
        (nome_da_obra, motivo)

    O app.py atual já tenta identificar o CNO usando contas_db
    antes de chamar esta função. Portanto aqui fazemos uma
    segunda camada textual segura.
    """

    texto = _normalize(inf_adic)

    cno_texto = str(cno or "").strip()

    # --------------------------------------------------------
    # PROCURA NOME COMPLETO DAS OBRAS
    # --------------------------------------------------------

    candidatos = []

    for classificacao, (
        codigo,
        nome_obra
    ) in HIKARI_OBRAS.items():

        if nome_obra == "CUSTO DA OBRA GERAL":
            continue

        nome_normalizado = _normalize(
            nome_obra
        )

        if (
            nome_normalizado
            and nome_normalizado in texto
        ):

            candidatos.append(
                (
                    len(nome_normalizado),
                    nome_obra,
                    "nome completo"
                )
            )

    # --------------------------------------------------------
    # PROCURA APELIDOS
    # --------------------------------------------------------

    for nome_obra, aliases in _OBRA_ALIASES.items():

        for alias in aliases:

            alias_normalizado = _normalize(
                alias
            )

            if (
                alias_normalizado
                and alias_normalizado in texto
            ):

                candidatos.append(
                    (
                        len(alias_normalizado),
                        nome_obra,
                        alias
                    )
                )

    # --------------------------------------------------------
    # ESCOLHE A CORRESPONDÊNCIA MAIS ESPECÍFICA
    # --------------------------------------------------------

    if candidatos:

        candidatos.sort(
            key=lambda item: item[0],
            reverse=True
        )

        _, obra, termo = candidatos[0]

        if cno_texto:

            return (
                obra,
                f"Obra identificada pelo contexto do XML; CNO informado: {cno_texto}."
            )

        return (
            obra,
            f"Obra identificada por correspondência textual: {termo}."
        )

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    if cno_texto:

        return (
            "CUSTO DA OBRA GERAL",
            f"CNO {cno_texto} não possui correspondência no cadastro legado; mantida Obra Geral."
        )

    return (
        "CUSTO DA OBRA GERAL",
        "Nenhuma obra específica identificada; mantida Obra Geral."
    )
