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


# ============================================================
# CAMINHO DO ARQUIVO DE PERSISTÊNCIA
# ============================================================

_PLANO_JSON = os.path.join(
    os.path.dirname(__file__),
    "plano_de_contas.json"
)


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def _normalize(text: str) -> str:
    """Lowercase and remove accents for keyword matching."""

    if not text:
        return ""

    t = str(text).lower()

    for a, b in [
        ("á", "a"),
        ("à", "a"),
        ("â", "a"),
        ("ã", "a"),
        ("ä", "a"),
        ("é", "e"),
        ("è", "e"),
        ("ê", "e"),
        ("ë", "e"),
        ("í", "i"),
        ("ì", "i"),
        ("î", "i"),
        ("ï", "i"),
        ("ó", "o"),
        ("ò", "o"),
        ("ô", "o"),
        ("õ", "o"),
        ("ö", "o"),
        ("ú", "u"),
        ("ù", "u"),
        ("û", "u"),
        ("ü", "u"),
        ("ç", "c"),
    ]:
        t = t.replace(a, b)

    return t


def _texto_normalizado(texto: str) -> str:
    """
    Normaliza texto para classificação.

    Remove acentos, pontuação e espaços duplicados.
    """

    texto = _normalize(texto)

    if not texto:
        return ""

    # Mantém somente letras, números e espaços
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)

    # Remove espaços duplicados
    texto = re.sub(r"\s+", " ", texto).strip()

    return texto


# ============================================================
# HIKARI — TIPOS DE DESPESA
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

    # ========================================================
    # 002
    #
    # IMPORTANTE:
    # Apesar do nome contábil conter "CIMENTO CAL",
    # esta categoria será utilizada para:
    #
    # FERRO
    # AÇO
    # VERGALHÃO
    # ARAME
    # TELAS
    # PERFIS METÁLICOS
    #
    # NÃO colocar aqui:
    # cimento
    # cal
    # concreto
    # argamassa
    # CP II
    # CP III
    # CP IV
    # ========================================================

    "002": (
        "DESPESAS COM CIMENTO CAL FERRO ARAME",
        [
            "ferro",
            "arame",
            "aco",
            "vergalhao",
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

    # ========================================================
    # 008 — TIJOLOS / BLOCOS
    # ========================================================

    "008": (
        "DESPESAS COM TIJOLOS",
        [
            "tijolo",
            "tijolos",
            "bloco",
            "blocos",
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
            "telhas",
            "cumeeira",
            "calha",
            "rufo",
            "cobertura",
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


# ============================================================
# LISTA DE CATEGORIAS
# ============================================================

HIKARI_DESPESAS_LISTA = [
    desc
    for _, (desc, _) in sorted(HIKARI_DESPESAS.items())
]


# ============================================================
# CATEGORIA → CÓDIGO
# ============================================================

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


# ============================================================
# REVERSE LOOKUP DAS OBRAS
# ============================================================

CODIGO_POR_OBRA = {
    name: cls
    for cls, (code, name) in HIKARI_OBRAS.items()
}


# ============================================================
# CÓDIGOS DO BALANCETE
# ============================================================

_CODIGOS_BALANCETE = {

    # --------------------------------------------------------
    # CUSTO DA OBRA GERAL
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CETEC SENAI ARAGUAINA
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ANFITEATRO SESI ARAGUAINA
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SEDE SESI SENAI PALMAS-TO
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ETI TAQUARI
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ETI PORTO LUZIMANGUES
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SESI DR GURUPI
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # BLOCO IFTO ARAGUAINA
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # REFORMA DUQUE DE CAXIAS II
    # --------------------------------------------------------

    ("REFORMA DUQUE DE CAXIAS II", "002"): 942,
    ("REFORMA DUQUE DE CAXIAS II", "003"): 943,
    ("REFORMA DUQUE DE CAXIAS II", "004"): 944,

    # --------------------------------------------------------
    # AMPLIACAO SEDE CREA PALMAS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CICLOVIA CESAMAR
    # --------------------------------------------------------

    ("CICLOVIA CESAMAR", "002"): 962,
    ("CICLOVIA CESAMAR", "003"): 963,
    ("CICLOVIA CESAMAR", "004"): 964,
    ("CICLOVIA CESAMAR", "006"): 966,
    ("CICLOVIA CESAMAR", "007"): 967,
    ("CICLOVIA CESAMAR", "009"): 969,
    ("CICLOVIA CESAMAR", "012"): 1242,
    ("CICLOVIA CESAMAR", "016"): 1675,

    # --------------------------------------------------------
    # CENTRO DE CONVENCOES PARAISO
    # --------------------------------------------------------

    ("CENTRO DE CONVENCOES PARAISO", "002"): 972,
    ("CENTRO DE CONVENCOES PARAISO", "003"): 973,
    ("CENTRO DE CONVENCOES PARAISO", "006"): 976,
    ("CENTRO DE CONVENCOES PARAISO", "007"): 978,
    ("CENTRO DE CONVENCOES PARAISO", "008"): 979,
    ("CENTRO DE CONVENCOES PARAISO", "009"): 1206,
    ("CENTRO DE CONVENCOES PARAISO", "010"): 1243,

    # --------------------------------------------------------
    # CENTRO DE ATENDIMENTO SOCIOEDUCATIVO
    # --------------------------------------------------------

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "002",
    ): 982,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "003",
    ): 983,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "004",
    ): 984,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "005",
    ): 985,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "006",
    ): 986,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "007",
    ): 987,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "008",
    ): 988,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "009",
    ): 989,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "010",
    ): 1208,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "012",
    ): 1244,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "014",
    ): 1649,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "015",
    ): 1654,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "016",
    ): 1674,

    (
        "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
        "017",
    ): 1670,

    # --------------------------------------------------------
    # GUARITA SENAI CT GURUPI
    # --------------------------------------------------------

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
    """Carrega o plano de contas extra do arquivo JSON."""

    if os.path.exists(_PLANO_JSON):

        try:

            with open(
                _PLANO_JSON,
                "r",
                encoding="utf-8"
            ) as f:

                return json.load(f)

        except Exception:
            pass

    return {
        "categorias_extras": [],
        "obras_extras": [],
    }


def save_plano_json(data: dict) -> None:
    """Salva o plano de contas extra no arquivo JSON."""

    with open(
        _PLANO_JSON,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def get_all_categorias(extra_cats: list) -> list:
    """Retorna a lista completa de categorias (base + extras)."""

    base = list(HIKARI_DESPESAS_LISTA)

    for item in extra_cats:

        nome = item.get(
            "nome",
            ""
        ).strip().upper()

        if nome and nome not in base:
            base.append(nome)

    return base


def get_all_obras(extra_obras: list) -> list:
    """Retorna a lista completa de obras (base + extras)."""

    base = list(HIKARI_OBRAS_LISTA)

    for item in extra_obras:

        nome = item.get(
            "nome",
            ""
        ).strip().upper()

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
    Returns the short numeric code (Código column from balancete)
    for a given category + obra combination.

    If the specific combo is not in the balancete,
    falls back to OBRA GERAL code.

    If still not found, returns the suffix.
    """

    if not obra_nome:
        obra_nome = "CUSTO DA OBRA GERAL"

    # --------------------------------------------------------
    # Categorias extras
    # --------------------------------------------------------

    if extra_cats:

        for item in extra_cats:

            if (
                item.get("nome", "")
                .strip()
                .upper()
                == categoria
            ):

                cod = item.get(
                    "codigo",
                    ""
                ).strip()

                return cod if cod else ""

    # --------------------------------------------------------
    # Categoria base
    # --------------------------------------------------------

    suffix = CODIGO_POR_DESPESA.get(categoria)

    if not suffix:
        return ""

    # --------------------------------------------------------
    # Busca combinação obra + despesa
    # --------------------------------------------------------

    code = _CODIGOS_BALANCETE.get(
        (
            obra_nome,
            suffix,
        )
    )

    if code is not None:
        return str(code)

    # --------------------------------------------------------
    # Fallback para obra geral
    # --------------------------------------------------------

    code = _CODIGOS_BALANCETE.get(
        (
            "CUSTO DA OBRA GERAL",
            suffix,
        )
    )

    if code is not None:
        return f"~{code}"

    return suffix


# ============================================================
# REGRAS PRIORITÁRIAS DE CLASSIFICAÇÃO
# ============================================================

def _encontrar_categoria_prioritaria(texto: str) -> Optional[str]:
    """
    Identifica materiais que possuem regras específicas.

    A prioridade é:

    1. Tijolos / blocos
    2. Ferro / aço / vergalhão / arame

    Essas regras são verificadas ANTES da pontuação genérica.
    """

    texto = _texto_normalizado(texto)

    if not texto:
        return None

    # --------------------------------------------------------
    # 1. TIJOLOS / BLOCOS
    # --------------------------------------------------------

    regras_tijolos = [

        r"\btijolo\b",
        r"\btijolos\b",

        r"\bbloco ceramico\b",
        r"\bbloco de ceramica\b",

        r"\bbloco concreto\b",
        r"\bbloco de concreto\b",

        r"\bbloco estrutural\b",
        r"\bblocos estruturais\b",
    ]

    for padrao in regras_tijolos:

        if re.search(
            padrao,
            texto
        ):

            return "DESPESAS COM TIJOLOS"

    # --------------------------------------------------------
    # 2. FERRO / AÇO / VERGALHÃO / ARAME
    # --------------------------------------------------------

    regras_ferro = [

        r"\bferro\b",
        r"\barame\b",
        r"\baco\b",
        r"\bvergalhao\b",

        r"\bbarra de ferro\b",
        r"\bbarras de ferro\b",

        r"\bbarra de aco\b",
        r"\bbarras de aco\b",

        r"\bperfil de aco\b",
        r"\bperfil metalico\b",

        r"\bcantoneira\b",

        r"\bmetalao\b",

        r"\btrelica\b",

        r"\btela soldada\b",
        r"\btela galvanizada\b",

        r"\bferro redondo\b",
        r"\bferro chato\b",
        r"\bferro quadrado\b",
        r"\bferro mecanico\b",

        r"\baco carbono\b",
    ]

    for padrao in regras_ferro:

        if re.search(
            padrao,
            texto
        ):

            return (
                "DESPESAS COM CIMENTO CAL FERRO ARAME"
            )

    return None


# ============================================================
# CLASSIFICAÇÃO DA NOTA FISCAL
# ============================================================

def categorize_invoice(
    items_list: list,
    inf_adic: str,
    cno: str,
):
    """
    Classifica uma nota fiscal.

    Lógica:

    1. Analisa os itens individualmente.
    2. Verifica regras prioritárias.
    3. Tijolo/bloco recebe categoria de tijolos.
    4. Ferro/aço/vergalhão/arame recebe a categoria 002.
    5. A categoria 002 NÃO usa cimento, cal, concreto ou
       argamassa como palavras de classificação.
    6. Informações adicionais não contaminam a classificação
       quando existem itens identificados.
    7. Se nenhuma regra prioritária for encontrada, utiliza
       a classificação genérica existente.
    """

    # --------------------------------------------------------
    # Garante lista
    # --------------------------------------------------------

    if items_list is None:
        items_list = []

    if isinstance(
        items_list,
        str
    ):
        items_list = [items_list]

    # --------------------------------------------------------
    # Remove itens vazios
    # --------------------------------------------------------

    itens_validos = [

        str(item).strip()

        for item in items_list

        if (
            item is not None
            and str(item).strip()
        )
    ]

    # ========================================================
    # ETAPA 1 — CLASSIFICAÇÃO PRIORITÁRIA ITEM POR ITEM
    # ========================================================

    categorias_detectadas = []

    for item in itens_validos:

        categoria = _encontrar_categoria_prioritaria(
            item
        )

        if categoria:

            categorias_detectadas.append(
                (
                    categoria,
                    item,
                )
            )

    # ========================================================
    # ETAPA 2 — TIJOLOS / BLOCOS
    #
    # Tem prioridade sobre "concreto".
    #
    # Exemplo:
    # "BLOCO DE CONCRETO"
    #
    # Resultado:
    # DESPESAS COM TIJOLOS
    # ========================================================

    categorias_tijolo = [

        item

        for categoria, item
        in categorias_detectadas

        if categoria
        == "DESPESAS COM TIJOLOS"
    ]

    if categorias_tijolo:

        return (
            "DESPESAS COM TIJOLOS",
            "Classificação direta por item: tijolo/bloco identificado.",
        )

    # ========================================================
    # ETAPA 3 — FERRO / AÇO / VERGALHÃO / ARAME
    # ========================================================

    categorias_ferro = [

        item

        for categoria, item
        in categorias_detectadas

        if (
            categoria
            == "DESPESAS COM CIMENTO CAL FERRO ARAME"
        )
    ]

    if categorias_ferro:

        return (
            "DESPESAS COM CIMENTO CAL FERRO ARAME",
            "Classificação direta por item: ferro/aço/vergalhão/arame identificado.",
        )

    # ========================================================
    # ETAPA 4 — CLASSIFICAÇÃO GENÉRICA
    #
    # SOMENTE OS ITENS SÃO UTILIZADOS.
    #
    # O inf_adic não entra aqui para evitar que observações
    # da nota contaminem a classificação do produto.
    # ========================================================

    raw = " ".join(
        itens_validos
    )

    text = _texto_normalizado(
        raw
    )

    scores = {}

    for code, (
        desc,
        keywords
    ) in HIKARI_DESPESAS.items():

        # ----------------------------------------------------
        # Categoria 002:
        #
        # Mesmo que futuramente alguém acrescente novamente
        # "cimento", "cal", "concreto" etc. ao dicionário,
        # essas palavras não serão usadas para classificar
        # essa categoria.
        # ----------------------------------------------------

        if (
            desc
            == "DESPESAS COM CIMENTO CAL FERRO ARAME"
        ):

            palavras_proibidas = {
                "cimento",
                "cal",
                "concreto",
                "argamassa",
                "cp ii",
                "cp iii",
                "cp iv",
            }

            keywords = [

                kw

                for kw in keywords

                if _texto_normalizado(kw)
                not in palavras_proibidas
            ]

        score = 0

        for kw in keywords:

            kw_normalizado = _texto_normalizado(
                kw
            )

            if not kw_normalizado:
                continue

            # ------------------------------------------------
            # Palavra inteira.
            #
            # Evita que uma parte de outra palavra gere
            # classificação indevida.
            # ------------------------------------------------

            padrao = (
                r"\b"
                + re.escape(
                    kw_normalizado
                )
                + r"\b"
            )

            if re.search(
                padrao,
                text
            ):

                score += 1

        scores[desc] = score

    # ========================================================
    # ETAPA 5 — MAIOR PONTUAÇÃO
    # ========================================================

    if scores:

        best_cat = max(
            scores,
            key=scores.get
        )

        best_score = scores[
            best_cat
        ]

        if best_score > 0:

            return (
                best_cat,
                (
                    "Detectado via palavras-chave "
                    f"dos itens (Score: {best_score})."
                ),
            )

    # ========================================================
    # ETAPA 6 — SEM CLASSIFICAÇÃO
    # ========================================================

    return (
        "DESPESAS COM MATERIAL DIVERSOS",
        "Nenhuma regra de material foi identificada.",
    )
