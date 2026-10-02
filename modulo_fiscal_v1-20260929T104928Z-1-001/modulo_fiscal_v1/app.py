"""
app.py — Catraca Fiscal v3
Streamlit dashboard for NF-e XML triage.
Hikari expense codes + obra centers from balancete.
Google Gemini AI integration for intelligent categorization.

VERSÃO COM CLASSIFICAÇÃO FISCAL APRIMORADA

Principais melhorias:
- Leitura de contexto completo do XML para classificação.
- CNO tem prioridade para identificação da obra.
- Usa CFOP, natureza da operação, fornecedor, cliente, itens, NCM
  e informações adicionais na classificação.
- Agrupa os itens por CFOP.
- Mantém separação de notas com múltiplos CFOPs.
- Recalcula automaticamente categoria, obra e conta analítica.
- Mantém fallback da Obra Geral quando não existe mapeamento específico.
- Mantém Google Gemini como segunda camada de classificação.
- Mantém Plano de Contas, Fornecedores, Obras e Lançamento Manual.
"""

import streamlit as st
import zipfile
import pandas as pd
import datetime
import re
import unicodedata

from xml_processor import parse_nfe

from categorizer import (
    categorize_invoice,
    suggest_project,
    HIKARI_DESPESAS_LISTA,
    HIKARI_OBRAS_LISTA,
    get_codigo_contabil,
    HIKARI_DESPESAS,
    HIKARI_OBRAS,
    CODIGO_POR_OBRA,
    load_plano_json,
    save_plano_json,
    get_all_categorias,
    get_all_obras,
)

from exporter import export_to_excel
from ai_classifier import classify_batch, is_available as ai_available

import fornecedor_db
import contas_db

from dominio_exporter import export_to_dominio_excel


# ═══════════════════════════════════════════════════════════════════
# HELPERS GERAIS
# ═══════════════════════════════════════════════════════════════════

def _matches_filters(doc, f_status, f_cat, f_obra, f_tipo, state):
    uid = doc["uid"]

    status = state["approvals"].get(uid, "Pendente")
    cat = state["categories"].get(
        uid,
        "DESPESAS COM MATERIAL DIVERSOS"
    )
    obra = state["obras"].get(
        uid,
        "CUSTO DA OBRA GERAL"
    )

    tipo = doc.get(
        "tipo_nf_classificado",
        "Entrada"
    )

    if f_status != "Todos" and status != f_status:
        return False

    if f_cat != "Todas" and cat != f_cat:
        return False

    if f_obra != "Todas" and obra != f_obra:
        return False

    if f_tipo != "Todos" and tipo != f_tipo:
        return False

    return True


def _fmt_brl(val):
    try:
        return (
            f"R$ {float(val):,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    except Exception:
        return "R$ 0,00"


def _normalizar_texto(texto):
    """
    Normaliza texto para facilitar comparação e regras de classificação.
    """
    if texto is None:
        return ""

    texto = str(texto).strip().upper()

    texto = unicodedata.normalize(
        "NFD",
        texto
    )

    texto = "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )

    texto = re.sub(r"\s+", " ", texto)

    return texto


def _valor_texto(doc, *campos):
    """
    Retorna o primeiro campo preenchido.
    """
    for campo in campos:
        valor = doc.get(campo)

        if valor is not None and str(valor).strip():
            return str(valor).strip()

    return ""


def _safe_join(values, separator=" | "):
    """
    Junta valores sem duplicidade.
    """
    resultado = []
    vistos = set()

    for value in values:
        if value is None:
            continue

        value = str(value).strip()

        if not value:
            continue

        chave = _normalizar_texto(value)

        if chave in vistos:
            continue

        vistos.add(chave)
        resultado.append(value)

    return separator.join(resultado)


# ═══════════════════════════════════════════════════════════════════
# CONTEXTO FISCAL DO XML
# ═══════════════════════════════════════════════════════════════════

def _extrair_itens_contexto(doc):
    """
    Extrai dos itens do XML informações úteis para classificação.

    A classificação não deve olhar apenas para a descrição.
    NCM e CFOP também ajudam a distinguir materiais, serviços,
    equipamentos, combustíveis, locações etc.
    """

    descricoes = []
    ncms = []
    cfops = []
    codigos = []
    unidades = []

    for item in doc.get("itens", []) or []:
        if not isinstance(item, dict):
            continue

        descricao = _valor_texto(
            item,
            "descricao",
            "xProd",
            "nome",
            "produto"
        )

        ncm = _valor_texto(
            item,
            "ncm",
            "NCM"
        )

        cfop = _valor_texto(
            item,
            "cfop",
            "CFOP"
        )

        codigo = _valor_texto(
            item,
            "codigo",
            "cProd",
            "codigo_produto"
        )

        unidade = _valor_texto(
            item,
            "unidade",
            "uCom",
            "un"
        )

        if descricao:
            descricoes.append(descricao)

        if ncm:
            ncms.append(ncm)

        if cfop:
            cfops.append(cfop)

        if codigo:
            codigos.append(codigo)

        if unidade:
            unidades.append(unidade)

    return {
        "descricoes": _safe_join(descricoes),
        "ncms": _safe_join(ncms),
        "cfops": _safe_join(cfops),
        "codigos": _safe_join(codigos),
        "unidades": _safe_join(unidades),
    }


def _montar_contexto_classificacao(doc):
    """
    Monta um contexto fiscal rico a partir da nota.

    Esse contexto é utilizado:
    - pela categorização local;
    - pela sugestão de obra;
    - pela IA;
    - para auditoria posterior.

    A ideia é evitar que a classificação dependa de uma única informação
    do XML.
    """

    itens = _extrair_itens_contexto(doc)

    fornecedor = _valor_texto(
        doc,
        "fornecedor",
        "emitente",
        "xNome_emitente"
    )

    fornecedor_cnpj = _valor_texto(
        doc,
        "fornecedor_cnpj",
        "cnpj_emitente",
        "CNPJ"
    )

    cliente = _valor_texto(
        doc,
        "cliente",
        "destinatario",
        "xNome_destinatario"
    )

    cliente_cnpj = _valor_texto(
        doc,
        "cliente_cnpj",
        "cnpj_destinatario"
    )

    natureza = _valor_texto(
        doc,
        "natureza_op",
        "natOp",
        "natureza_operacao"
    )

    inf_adic = _valor_texto(
        doc,
        "infAdic",
        "informacoes_adicionais",
        "informacoes_adicionais_fisco"
    )

    cno = _valor_texto(
        doc,
        "cno_sugerido",
        "cno",
        "CNO"
    )

    n_nf = _valor_texto(
        doc,
        "nNF",
        "numero_nf"
    )

    data_emissao = _valor_texto(
        doc,
        "data_emissao",
        "dhEmi",
        "dEmi"
    )

    cfop_destaque = _valor_texto(
        doc,
        "cfop_destaque"
    )

    cfops_nota = doc.get("cfops_nota", [])

    if isinstance(cfops_nota, (list, tuple)):
        cfops_nota_texto = _safe_join(cfops_nota)
    else:
        cfops_nota_texto = str(cfops_nota or "")

    tipo_nf = _valor_texto(
        doc,
        "tipo_nf_classificado"
    )

    partes = [
        f"NF: {n_nf}",
        f"Data emissão: {data_emissao}",
        f"Fornecedor: {fornecedor}",
        f"CNPJ fornecedor: {fornecedor_cnpj}",
        f"Cliente: {cliente}",
        f"CNPJ cliente: {cliente_cnpj}",
        f"Natureza da operação: {natureza}",
        f"Tipo NF: {tipo_nf}",
        f"CNO: {cno}",
        f"CFOP destaque: {cfop_destaque}",
        f"CFOPs da nota: {cfops_nota_texto}",
        f"CFOPs dos itens: {itens['cfops']}",
        f"NCMs: {itens['ncms']}",
        f"Códigos dos produtos: {itens['codigos']}",
        f"Unidades: {itens['unidades']}",
        f"Itens/produtos: {itens['descricoes']}",
        f"Informações adicionais: {inf_adic}",
    ]

    contexto = _safe_join(
        partes,
        separator="\n"
    )

    return {
        "fornecedor": fornecedor,
        "fornecedor_cnpj": fornecedor_cnpj,
        "cliente": cliente,
        "cliente_cnpj": cliente_cnpj,
        "natureza": natureza,
        "inf_adic": inf_adic,
        "cno": cno,
        "cfop_destaque": cfop_destaque,
        "cfops_nota": cfops_nota_texto,
        "tipo_nf": tipo_nf,
        "itens_descricao": itens["descricoes"],
        "itens_ncm": itens["ncms"],
        "itens_cfop": itens["cfops"],
        "contexto": contexto,
    }


def _enriquecer_documento_classificacao(doc):
    """
    Adiciona ao documento os dados derivados do XML.

    Não substitui os campos originais.
    """

    contexto = _montar_contexto_classificacao(doc)

    doc["classificacao_contexto_xml"] = contexto["contexto"]
    doc["classificacao_itens"] = contexto["itens_descricao"]
    doc["classificacao_ncms"] = contexto["itens_ncm"]
    doc["classificacao_cfops"] = contexto["itens_cfop"]
    doc["classificacao_natureza"] = contexto["natureza"]

    return contexto


# ═══════════════════════════════════════════════════════════════════
# REGRAS DE TIPO DE NF
# ═══════════════════════════════════════════════════════════════════

def _classificar_tipo_nf_por_xml(doc):
    """
    Classifica Entrada/Saída/Retorno usando os dados existentes no XML.

    Se o xml_processor já tiver definido tipo_nf_classificado,
    preservamos a classificação quando ela estiver preenchida.

    Para retorno/devolução, procuramos também CFOPs típicos de retorno.
    """

    tipo_existente = doc.get("tipo_nf_classificado")

    if tipo_existente:
        return tipo_existente

    cfops = []

    valor_cfop_destaque = doc.get("cfop_destaque")

    if valor_cfop_destaque:
        cfops.append(str(valor_cfop_destaque))

    for cfop in doc.get("cfops_nota", []) or []:
        cfops.append(str(cfop))

    for item in doc.get("itens", []) or []:
        if isinstance(item, dict):
            cfop = item.get("cfop")
            if cfop:
                cfops.append(str(cfop))

    cfops = [
        re.sub(r"\D", "", c)
        for c in cfops
        if c
    ]

    cfops = list(dict.fromkeys(cfops))

    # CFOPs normalmente associados a devolução/retorno.
    prefixos_retorno = (
        "120",
        "141",
        "220",
        "241",
        "520",
        "541",
        "555",
        "620",
        "641",
        "655",
    )

    for cfop in cfops:
        if cfop.startswith(prefixos_retorno):
            return "Retorno/Devolução"

    # 1.xxx / 2.xxx normalmente entradas.
    # 5.xxx / 6.xxx normalmente saídas.
    for cfop in cfops:
        if cfop.startswith(("5", "6", "7")):
            return "Saída"

    return "Entrada"


# ═══════════════════════════════════════════════════════════════════
# CLASSIFICAÇÃO DE OBRA
# ═══════════════════════════════════════════════════════════════════

def _buscar_obra_por_varias_fontes(doc, contexto):
    """
    Procura obra por várias fontes, mantendo o CNO como principal
    identificador quando disponível.

    Ordem:
    1. CNO
    2. identificação via contas_db
    3. informações adicionais
    4. contexto textual
    """

    cno = (
        contexto.get("cno")
        or doc.get("cno_sugerido")
        or doc.get("cno")
    )

    if cno:
        try:
            obra_contas = contas_db.lookup_obra_por_cno(str(cno).strip())

            if obra_contas:
                obra_label = (
                    obra_contas.get("dropdown_label")
                    or obra_contas.get("nome_display")
                    or obra_contas.get("nome")
                )

                if obra_label:
                    return (
                        obra_label,
                        f"Identificado diretamente pelo CNO {cno}"
                    )
        except Exception:
            pass

    texto_busca = contexto.get("contexto", "")

    # Primeiro tenta a lógica legada com o contexto enriquecido.
    try:
        obra_legacy, reason_legacy = suggest_project(
            texto_busca,
            cno
        )

        if obra_legacy and obra_legacy != "CUSTO DA OBRA GERAL":
            try:
                obra_obj = contas_db.get_obra_by_identifier(
                    obra_legacy
                )

                if obra_obj:
                    label = (
                        obra_obj.get("dropdown_label")
                        or obra_obj.get("nome_display")
                        or obra_legacy
                    )

                    return (
                        label,
                        reason_legacy or "Identificado pelo contexto fiscal do XML"
                    )

            except Exception:
                pass

            return (
                obra_legacy,
                reason_legacy or "Identificado pelo contexto fiscal do XML"
            )

    except Exception:
        pass

    # Busca textual direta nas obras cadastradas.
    texto_normalizado = _normalizar_texto(texto_busca)

    if texto_normalizado:
        try:
            todas_obras = contas_db.get_all_obras()

            candidatos = []

            for obra in todas_obras:
                nome = (
                    obra.get("nome_display")
                    or obra.get("nome")
                    or obra.get("display")
                    or ""
                )

                if not nome:
                    continue

                nome_norm = _normalizar_texto(nome)

                # Palavras relevantes do nome da obra.
                palavras = [
                    p
                    for p in nome_norm.split()
                    if len(p) >= 5
                ]

                coincidencias = [
                    p
                    for p in palavras
                    if p in texto_normalizado
                ]

                if coincidencias:
                    candidatos.append(
                        (
                            len(coincidencias),
                            obra
                        )
                    )

            if candidatos:
                candidatos.sort(
                    key=lambda x: x[0],
                    reverse=True
                )

                melhor = candidatos[0][1]

                label = (
                    melhor.get("dropdown_label")
                    or melhor.get("nome_display")
                    or melhor.get("nome")
                )

                if label:
                    return (
                        label,
                        "Obra identificada por correspondência textual no XML"
                    )

        except Exception:
            pass

    return (
        "CUSTO DA OBRA GERAL — Cód. 271 (3.1.1.01)",
        "Obra Geral padrão — nenhuma obra específica identificada no XML"
    )


# ═══════════════════════════════════════════════════════════════════
# CLASSIFICAÇÃO COMPLETA DA NOTA
# ═══════════════════════════════════════════════════════════════════

def _classificar_documento_xml(doc):
    """
    Faz a classificação inicial completa da nota.

    O objetivo é centralizar a lógica em um único ponto.
    """

    contexto = _enriquecer_documento_classificacao(doc)

    # Tipo NF.
    tipo_nf = _classificar_tipo_nf_por_xml(doc)
    doc["tipo_nf_classificado"] = tipo_nf

    # Fornecedor.
    try:
        fornec_match = fornecedor_db.lookup_fornecedor_por_nome(
            contexto.get("fornecedor", "")
        )
    except Exception:
        fornec_match = None

    doc["fornecedor_contabil"] = fornec_match or {}

    # Categorização.
    #
    # IMPORTANTE:
    # Passamos o contexto inteiro em vez de apenas a descrição dos itens.
    #
    # Isso permite que o categorizer utilize:
    # - produto;
    # - NCM;
    # - CFOP;
    # - natureza da operação;
    # - fornecedor;
    # - cliente;
    # - CNO;
    # - informações adicionais.
    try:
        cat, cat_reason = categorize_invoice(
            [contexto["contexto"]],
            contexto["contexto"],
            contexto["cno"],
        )
    except Exception:
        # Fallback seguro caso a implementação atual do categorizer
        # tenha expectativa diferente.
        try:
            cat, cat_reason = categorize_invoice(
                [contexto["itens_descricao"]],
                contexto["inf_adic"],
                contexto["cno"],
            )
        except Exception:
            cat = "DESPESAS COM MATERIAL DIVERSOS"
            cat_reason = "Fallback de classificação"

    # Obra.
    obra_sugerida, proj_reason = _buscar_obra_por_varias_fontes(
        doc,
        contexto
    )

    doc["categoria_sugerida"] = cat
    doc["obra_sugerida"] = obra_sugerida
    doc["motivo_categoria_xml"] = cat_reason
    doc["motivo_obra_xml"] = proj_reason

    return (
        cat,
        obra_sugerida,
        cat_reason,
        proj_reason,
        fornec_match or {},
        contexto,
    )


# ═══════════════════════════════════════════════════════════════════
# RESOLUÇÃO DO CÓDIGO CONTÁBIL
# ═══════════════════════════════════════════════════════════════════

def _resolve_codigo_contabil(categoria: str, obra: str) -> tuple:
    """
    Resolve o código e detalhes da subclasse dentro do segmento.

    Retorna:
        (codigo_str, info_dict)
    """

    try:
        info = contas_db.get_codigo_info_para_obra_e_categoria(
            obra,
            categoria
        )
    except Exception:
        info = {}

    if info is None:
        info = {}

    cod = info.get("codigo")

    if cod:
        prefix = "~" if info.get("is_fallback") else ""
        return f"{prefix}{cod}", info

    try:
        legacy_code = get_codigo_contabil(
            categoria,
            obra,
            st.session_state.get("plano_extra_cats")
        )
    except Exception:
        legacy_code = ""

    return legacy_code, info


# ═══════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Catraca Fiscal v3 — Triagem NF-e Hikari",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ═══════════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════════

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="st-"] {
    font-family: 'Inter', sans-serif;
}

.cno-tag {
    background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
    border-left: 4px solid #2e7d32;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    font-size: 13px;
    font-weight: 500;
}

.alert-missing {
    background: #fff3cd;
    border-left: 4px solid #ffc107;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    font-size: 13px;
}

.ai-tag {
    background: linear-gradient(135deg, #e3f2fd, #bbdefb);
    border-left: 4px solid #1565c0;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    font-size: 13px;
}

.badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
}

.badge-pending {
    background: #FFF3CD;
    color: #856404;
}

.badge-approved {
    background: #D4EDDA;
    color: #155724;
}

.badge-rejected {
    background: #F8D7DA;
    color: #721C24;
}

.badge-retorno {
    background: #FFE0B2;
    color: #BF360C;
}

.badge-entrada {
    background: #E8F5E9;
    color: #1B5E20;
}

.badge-saida {
    background: #FBE9E7;
    color: #BF360C;
}

.obras-gerais-tag {
    background: #f8d7da;
    border-left: 4px solid #dc3545;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    font-size: 13px;
    font-weight: 500;
}

.retorno-tag {
    background: linear-gradient(135deg, #FFF3E0, #FFE0B2);
    border-left: 4px solid #E65100;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    font-size: 13px;
    font-weight: 600;
}

.codigo-tag {
    background: linear-gradient(135deg, #ede7f6, #d1c4e9);
    border-left: 4px solid #5e35b1;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    font-size: 14px;
    font-weight: 600;
    font-family: 'Courier New', monospace;
    letter-spacing: 0.5px;
}

.codigo-tag .code-value {
    background: #5e35b1;
    color: white;
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 15px;
}

.codigo-fallback-tag {
    background: linear-gradient(135deg, #fff8e1, #fff3cd);
    border-left: 4px solid #f9a825;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    font-size: 14px;
    font-weight: 600;
    font-family: 'Courier New', monospace;
    letter-spacing: 0.5px;
}

.codigo-fallback-tag .code-value {
    background: #f9a825;
    color: #333;
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 15px;
}

.manual-header {
    background: linear-gradient(135deg, #e8eaf6, #c5cae9);
    border-left: 4px solid #3949ab;
    padding: 12px 16px;
    border-radius: 8px;
    margin: 10px 0;
    font-size: 14px;
    font-weight: 600;
}

.classificacao-xml {
    background: linear-gradient(135deg, #f3e5f5, #e1bee7);
    border-left: 4px solid #7b1fa2;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    font-size: 12px;
}

.contexto-fiscal {
    background: #f5f5f5;
    border-left: 4px solid #607d8b;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    font-size: 12px;
}
</style>
""",
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════════

_plano_json = load_plano_json()

for key, default in [
    ("processed_data", []),
    ("approvals", {}),
    ("categories", {}),
    ("obras", {}),
    ("codigos", {}),
    ("codigos_info", {}),
    ("fornecedores_map", {}),
    ("ai_reasons", {}),
    ("gemini_key", ""),
    ("deepseek_key", ""),
    ("ai_classified", False),
    ("plano_extra_cats", _plano_json.get("categorias_extras", [])),
    ("plano_extra_obras", _plano_json.get("obras_extras", [])),
    ("lancamentos_manuais", []),
    ("filter_status", "Todos"),
    ("filter_cat", "Todas"),
    ("filter_obra", "Todas"),
    ("filter_tipo", "Todos"),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ═══════════════════════════════════════════════════════════════════
# LISTAS DINÂMICAS
# ═══════════════════════════════════════════════════════════════════

CATEGORY_OPTIONS = (
    get_all_categorias(
        st.session_state["plano_extra_cats"]
    )
    + ["OUTRA (digitar)"]
)

contas_obras_list = contas_db.get_obra_names_for_dropdown()

base_obras = get_all_obras(
    st.session_state["plano_extra_obras"]
)

OBRA_OPTIONS = list(contas_obras_list)

for bo in base_obras:
    if (
        bo not in OBRA_OPTIONS
        and bo != "CUSTO DA OBRA GERAL"
    ):
        OBRA_OPTIONS.append(bo)

OBRA_OPTIONS += ["OUTRA (digitar)"]


# ═══════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════

with st.sidebar:

    st.markdown("## Catraca Fiscal v3")
    st.caption("Triagem NF-e — Hikari Construcoes")
    st.divider()

    page = st.radio(
        "Navegacao",
        [
            "Triagem",
            "Exportacao",
            "Fornecedores & Obras",
            "Plano de Contas",
            "Lancamento Manual",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # UPLOAD XML
    # ═══════════════════════════════════════════════════════════════

    st.markdown("#### Upload de XMLs")

    uploaded_file = st.file_uploader(
        "Arquivo ZIP",
        type="zip",
        label_visibility="collapsed",
    )

    if uploaded_file:

        with zipfile.ZipFile(uploaded_file, "r") as z:

            xml_files = [
                f
                for f in z.namelist()
                if f.lower().endswith(".xml")
            ]

            st.info(
                f"{len(xml_files)} arquivos XML encontrados"
            )

            if st.button(
                "Processar Lote",
                use_container_width=True,
                type="primary",
            ):

                # Limpa lote anterior.
                st.session_state["processed_data"] = []
                st.session_state["approvals"] = {}
                st.session_state["categories"] = {}
                st.session_state["obras"] = {}
                st.session_state["codigos"] = {}
                st.session_state["codigos_info"] = {}
                st.session_state["fornecedores_map"] = {}
                st.session_state["ai_reasons"] = {}
                st.session_state["ai_classified"] = False

                progress = st.progress(
                    0,
                    text="Processando XMLs..."
                )

                errors = []

                for i, xml_file in enumerate(xml_files):

                    try:

                        with z.open(xml_file) as f:
                            data_rows = parse_nfe(
                                f.read()
                            )

                    except Exception as exc:
                        errors.append(
                            f"{xml_file}: erro ao ler XML: {exc}"
                        )
                        continue

                    if (
                        data_rows
                        and isinstance(data_rows[0], dict)
                        and "error" in data_rows[0]
                    ):
                        errors.append(
                            f"{xml_file}: "
                            f"{data_rows[0]['error']}"
                        )
                        continue

                    if not data_rows:
                        continue

                    # ═══════════════════════════════════════════════
                    # AGRUPAMENTO POR CFOP
                    # ═══════════════════════════════════════════════

                    cfop_groups = {}

                    for row in data_rows:

                        cfop_k = (
                            row.get("cfop_destaque")
                            or ""
                        )

                        if cfop_k not in cfop_groups:
                            cfop_groups[cfop_k] = []

                        cfop_groups[cfop_k].append(
                            row
                        )

                    for cfop_sub_idx, (
                        cfop_val,
                        rows_for_cfop
                    ) in enumerate(
                        cfop_groups.items()
                    ):

                        base_data = (
                            rows_for_cfop[0].copy()
                        )

                        # ═══════════════════════════════════════
                        # PARCELAS
                        # ═══════════════════════════════════════

                        parcelas = []

                        for row in rows_for_cfop:

                            parcelas.append(
                                {
                                    "nDup": row.get(
                                        "parcela_numero",
                                        "1",
                                    ),
                                    "dVenc": row.get(
                                        "parcela_vencimento",
                                        base_data.get(
                                            "data_emissao"
                                        ),
                                    ),
                                    "vDup": row.get(
                                        "parcela_valor",
                                        base_data.get(
                                            "valor_total"
                                        ),
                                    ),
                                }
                            )

                        base_data["parcelas"] = parcelas

                        # ═══════════════════════════════════════
                        # UID
                        # ═══════════════════════════════════════

                        if len(cfop_groups) > 1:

                            base_data["uid"] = (
                                f"{base_data['nNF']}_"
                                f"{cfop_val}_"
                                f"{i}_"
                                f"{cfop_sub_idx}"
                            )

                            base_data["cfop_info"] = (
                                f"CFOP {cfop_val}"
                            )

                        else:

                            base_data["uid"] = (
                                f"{base_data['nNF']}_{i}"
                            )

                            base_data["cfop_info"] = (
                                f"CFOP {cfop_val}"
                                if cfop_val
                                else ""
                            )

                        # ═══════════════════════════════════════
                        # CLASSIFICAÇÃO COMPLETA DO XML
                        # ═══════════════════════════════════════

                        (
                            cat,
                            obra_sugerida,
                            cat_reason,
                            proj_reason,
                            fornec_match,
                            contexto,
                        ) = _classificar_documento_xml(
                            base_data
                        )

                        # Garante tipo NF.
                        base_data[
                            "tipo_nf_classificado"
                        ] = _classificar_tipo_nf_por_xml(
                            base_data
                        )

                        # ═══════════════════════════════════════
                        # SALVA DADOS DERIVADOS
                        # ═══════════════════════════════════════

                        base_data["categoria"] = cat

                        base_data[
                            "obra_sugerida"
                        ] = obra_sugerida

                        base_data[
                            "filename"
                        ] = xml_file

                        base_data[
                            "contexto_classificacao"
                        ] = contexto

                        # ═══════════════════════════════════════
                        # CÓDIGO CONTÁBIL
                        # ═══════════════════════════════════════

                        codigo, cod_info = (
                            _resolve_codigo_contabil(
                                cat,
                                obra_sugerida,
                            )
                        )

                        # ═══════════════════════════════════════
                        # SESSION STATE
                        # ═══════════════════════════════════════

                        uid = base_data["uid"]

                        st.session_state[
                            "processed_data"
                        ].append(
                            base_data
                        )

                        st.session_state[
                            "approvals"
                        ][uid] = "Pendente"

                        st.session_state[
                            "categories"
                        ][uid] = cat

                        st.session_state[
                            "obras"
                        ][uid] = obra_sugerida

                        st.session_state[
                            "codigos"
                        ][uid] = codigo

                        st.session_state[
                            "codigos_info"
                        ][uid] = cod_info

                        st.session_state[
                            "fornecedores_map"
                        ][uid] = (
                            fornec_match or {}
                        )

                        st.session_state[
                            "ai_reasons"
                        ][uid] = (
                            f"{cat_reason} | "
                            f"{proj_reason}"
                        )

                    progress.progress(
                        (i + 1) / max(
                            len(xml_files),
                            1
                        ),
                        text=(
                            f"Processando "
                            f"{i + 1}/"
                            f"{len(xml_files)}..."
                        ),
                    )

                progress.empty()

                st.success(
                    f"{len(st.session_state['processed_data'])} "
                    f"notas processadas!"
                )

                if errors:
                    st.warning(
                        f"{len(errors)} XML(s) apresentaram problemas."
                    )

                    for err in errors:
                        st.warning(err)

                st.rerun()

    # ═══════════════════════════════════════════════════════════════
    # GEMINI
    # ═══════════════════════════════════════════════════════════════

    st.divider()

    st.markdown("#### Classificacao com IA")

    if ai_available():

        api_key = st.text_input(
            "Chave API Google Gemini",
            type="password",
            value=st.session_state.get(
                "gemini_key",
                ""
            ),
            help=(
                "Insira sua chave da API Google Gemini"
            ),
        )

        if api_key:
            st.session_state[
                "gemini_key"
            ] = api_key

        if (
            st.session_state["processed_data"]
            and api_key
        ):

            if st.button(
                "Classificar com Google Gemini AI",
                use_container_width=True,
                type="primary",
            ):

                with st.spinner(
                    "Enviando contexto fiscal "
                    "dos XMLs para o Google Gemini..."
                ):

                    result = classify_batch(
                        st.session_state[
                            "processed_data"
                        ],
                        api_key,
                    )

                if result and "_error" not in result:

                    for doc in st.session_state[
                        "processed_data"
                    ]:

                        uid = doc["uid"]
                        nf = doc["nNF"]

                        if nf not in result:
                            continue

                        r = result[nf]

                        # Categoria.
                        cat = r.get(
                            "categoria",
                            st.session_state[
                                "categories"
                            ].get(
                                uid,
                                "DESPESAS COM MATERIAL DIVERSOS"
                            ),
                        )

                        if not cat:
                            cat = (
                                "DESPESAS COM MATERIAL DIVERSOS"
                            )

                        st.session_state[
                            "categories"
                        ][uid] = cat

                        # Obra.
                        obra = r.get(
                            "obra_sugerida",
                            st.session_state[
                                "obras"
                            ].get(
                                uid,
                                "CUSTO DA OBRA GERAL"
                            ),
                        )

                        o_match = None

                        try:
                            o_match = (
                                contas_db
                                .get_obra_by_identifier(
                                    obra
                                )
                            )
                        except Exception:
                            o_match = None

                        if o_match:

                            obra_label = (
                                o_match.get(
                                    "dropdown_label"
                                )
                                or o_match.get(
                                    "nome_display"
                                )
                                or obra
                            )

                        else:
                            obra_label = obra

                        st.session_state[
                            "obras"
                        ][uid] = obra_label

                        # Código.
                        cod, cod_info = (
                            _resolve_codigo_contabil(
                                cat,
                                obra_label,
                            )
                        )

                        st.session_state[
                            "codigos"
                        ][uid] = cod

                        st.session_state[
                            "codigos_info"
                        ][uid] = cod_info

                        # Motivo IA.
                        reason = r.get(
                            "motivo_categoria",
                            ""
                        )

                        reason_obra = r.get(
                            "motivo_obra",
                            ""
                        )

                        partes_reason = []

                        if reason:
                            partes_reason.append(
                                f"IA Gemini categoria: {reason}"
                            )

                        if reason_obra:
                            partes_reason.append(
                                f"IA Gemini obra: {reason_obra}"
                            )

                        if partes_reason:
                            st.session_state[
                                "ai_reasons"
                            ][uid] = " | ".join(
                                partes_reason
                            )

                    st.session_state[
                        "ai_classified"
                    ] = True

                    st.success(
                        "Classificacao com Google Gemini AI concluida!"
                    )

                    st.rerun()

                elif result and "_error" in result:

                    st.error(
                        f"Erro da API: "
                        f"{result['_error']}"
                    )

                else:

                    st.error(
                        "Falha na classificacao. "
                        "Verifique a chave API."
                    )

        elif (
            st.session_state["processed_data"]
            and not api_key
        ):

            st.caption(
                "Insira a chave API para ativar a IA"
            )

    else:

        st.warning(
            "Instale: pip install google-generativeai"
        )

        st.code(
            "pip install google-generativeai",
            language="bash",
        )

    # ═══════════════════════════════════════════════════════════════
    # PROGRESSO
    # ═══════════════════════════════════════════════════════════════

    if st.session_state["processed_data"]:

        st.divider()

        st.markdown("#### Progresso")

        total = len(
            st.session_state[
                "processed_data"
            ]
        )

        approved = list(
            st.session_state[
                "approvals"
            ].values()
        ).count("Aprovado")

        rejected = list(
            st.session_state[
                "approvals"
            ].values()
        ).count("Rejeitado")

        pending = (
            total
            - approved
            - rejected
        )

        pct = (
            (approved + rejected) / total
            if total > 0
            else 0
        )

        st.progress(
            pct,
            text=(
                f"{approved + rejected}/"
                f"{total} triados "
                f"({pct:.0%})"
            ),
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Aprovados",
            approved
        )

        c2.metric(
            "Rejeitados",
            rejected
        )

        c3.metric(
            "Pendentes",
            pending
        )

        # Tipo NF.
        tipos = {}

        for d in st.session_state[
            "processed_data"
        ]:

            t = d.get(
                "tipo_nf_classificado",
                "Entrada"
            )

            tipos[t] = (
                tipos.get(t, 0)
                + 1
            )

        if tipos:

            st.divider()

            st.markdown(
                "#### Por Tipo NF"
            )

            for t, cnt in sorted(
                tipos.items()
            ):

                icon = (
                    "🔄"
                    if "Retorno" in t
                    else (
                        "📥"
                        if t == "Entrada"
                        else "📤"
                    )
                )

                st.caption(
                    f"{icon} **{t}** — {cnt}"
                )

        # Obras.
        st.divider()

        st.markdown(
            "#### Por Obra"
        )

        obras_dict = {}

        for d in st.session_state[
            "processed_data"
        ]:

            obra = st.session_state[
                "obras"
            ].get(
                d["uid"],
                "CUSTO DA OBRA GERAL"
            )

            if obra not in obras_dict:
                obras_dict[obra] = {
                    "count": 0,
                    "total": 0.0,
                }

            obras_dict[obra]["count"] += 1

            obras_dict[obra]["total"] += (
                d.get(
                    "valor_total",
                    0
                )
                or 0
            )

        for obra, info in obras_dict.items():

            st.caption(
                f"**{obra}** — "
                f"{info['count']} NFs — "
                f"{_fmt_brl(info['total'])}"
            )


# ═══════════════════════════════════════════════════════════════════
# PAGE 1 — TRIAGEM
# ═══════════════════════════════════════════════════════════════════

if page == "Triagem":

    st.markdown(
        "# Triagem de Notas Fiscais"
    )

    st.caption(
        "Revise, classifique com os codigos Hikari, "
        "e aprove ou rejeite cada nota."
    )

    if not st.session_state[
        "processed_data"
    ]:

        st.info(
            "Faca o upload de um arquivo ZIP "
            "com XMLs na barra lateral."
        )

        st.stop()

    if st.session_state.get(
        "ai_classified"
    ):

        st.markdown(
            """
            <div class="ai-tag">
            <strong>Classificacao com Google Gemini AI ativa</strong>
            — categorias e obras foram revisadas pela IA com base
            no contexto fiscal dos XMLs. Revise e ajuste.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ═══════════════════════════════════════════════════════════════
    # FILTROS
    # ═══════════════════════════════════════════════════════════════

    f1, f2, f3, f4 = st.columns(4)

    with f1:

        filter_status = st.selectbox(
            "Filtrar Status",
            [
                "Todos",
                "Pendente",
                "Aprovado",
                "Rejeitado",
            ],
            key="flt_status",
        )

    with f2:

        all_cats = sorted(
            set(
                st.session_state[
                    "categories"
                ].values()
            )
        )

        filter_cat = st.selectbox(
            "Filtrar Categoria",
            ["Todas"] + all_cats,
            key="flt_cat",
        )

    with f3:

        all_obras = sorted(
            set(
                st.session_state[
                    "obras"
                ].values()
            )
        )

        filter_obra = st.selectbox(
            "Filtrar Obra",
            ["Todas"] + all_obras,
            key="flt_obra",
        )

    with f4:

        filter_tipo = st.selectbox(
            "Filtrar Tipo NF",
            [
                "Todos",
                "Entrada",
                "Saída",
                "Retorno/Devolução",
            ],
            key="flt_tipo",
        )

    # ═══════════════════════════════════════════════════════════════
    # AÇÕES EM LOTE
    # ═══════════════════════════════════════════════════════════════

    b1, b2, b3 = st.columns(
        [1, 1, 4]
    )

    if b1.button(
        "Aprovar Todos Visiveis",
        use_container_width=True,
    ):

        for d in st.session_state[
            "processed_data"
        ]:

            if _matches_filters(
                d,
                filter_status,
                filter_cat,
                filter_obra,
                filter_tipo,
                st.session_state,
            ):

                st.session_state[
                    "approvals"
                ][d["uid"]] = "Aprovado"

        st.rerun()

    if b2.button(
        "Rejeitar Todos Visiveis",
        use_container_width=True,
    ):

        for d in st.session_state[
            "processed_data"
        ]:

            if _matches_filters(
                d,
                filter_status,
                filter_cat,
                filter_obra,
                filter_tipo,
                st.session_state,
            ):

                st.session_state[
                    "approvals"
                ][d["uid"]] = "Rejeitado"

        st.rerun()

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # PAGINAÇÃO
    # ═══════════════════════════════════════════════════════════════

    visible_docs = [
        d
        for d in st.session_state[
            "processed_data"
        ]
        if _matches_filters(
            d,
            filter_status,
            filter_cat,
            filter_obra,
            filter_tipo,
            st.session_state,
        )
    ]

    items_per_page = 10

    total_pages = (
        max(
            1,
            (
                len(visible_docs) - 1
            ) // items_per_page
            + 1,
        )
        if visible_docs
        else 1
    )

    if total_pages > 1:

        pag_col1, pag_col2 = st.columns(
            [1, 4]
        )

        with pag_col1:

            page_num = st.number_input(
                "Pagina",
                min_value=1,
                max_value=total_pages,
                step=1,
                value=1,
                key=(
                    f"pgn_"
                    f"{filter_status}_"
                    f"{filter_cat}_"
                    f"{filter_obra}_"
                    f"{filter_tipo}"
                ),
            )

        with pag_col2:

            st.write(
                f"Exibindo {len(visible_docs)} "
                f"notas no total "
                f"({total_pages} paginas)"
            )

    else:

        page_num = 1

        st.write(
            f"Exibindo {len(visible_docs)} notas"
        )

    start_idx = (
        page_num - 1
    ) * items_per_page

    end_idx = (
        start_idx + items_per_page
    )

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # CARDS DAS NOTAS
    # ═══════════════════════════════════════════════════════════════

    for idx, doc in enumerate(
        visible_docs[
            start_idx:end_idx
        ]
    ):

        uid = doc["uid"]

        status = st.session_state[
            "approvals"
        ].get(
            uid,
            "Pendente"
        )

        cat = st.session_state[
            "categories"
        ].get(
            uid,
            "DESPESAS COM MATERIAL DIVERSOS"
        )

        obra = st.session_state[
            "obras"
        ].get(
            uid,
            "CUSTO DA OBRA GERAL"
        )

        ai_reason = st.session_state[
            "ai_reasons"
        ].get(
            uid,
            ""
        )

        tipo_nf = doc.get(
            "tipo_nf_classificado",
            "Entrada"
        )

        badge_cls = {
            "Pendente": "badge-pending",
            "Aprovado": "badge-approved",
            "Rejeitado": "badge-rejected",
        }

        badge_html = (
            f'<span class="badge '
            f'{badge_cls.get(status, "badge-pending")}">'
            f'{status}</span>'
        )

        tipo_badge_map = {
            "Entrada": (
                "badge-entrada",
                "📥 Entrada",
            ),
            "Saída": (
                "badge-saida",
                "📤 Saída",
            ),
            "Retorno/Devolução": (
                "badge-retorno",
                "🔄 Retorno/Devolução",
            ),
        }

        tipo_cls, tipo_label = (
            tipo_badge_map.get(
                tipo_nf,
                (
                    "badge-entrada",
                    tipo_nf,
                ),
            )
        )

        tipo_badge_html = (
            f'<span class="badge '
            f'{tipo_cls}">'
            f'{tipo_label}</span>'
        )

        with st.container(
            border=True
        ):

            # ═══════════════════════════════════════════════════════
            # HEADER
            # ═══════════════════════════════════════════════════════

            h1, h2, h3 = st.columns(
                [5, 2, 1]
            )

            with h1:

                fornec_info = (
                    st.session_state
                    .get(
                        "fornecedores_map",
                        {}
                    )
                    .get(
                        uid,
                        {}
                    )
                )

                if (
                    fornec_info
                    and fornec_info.get(
                        "codigo_contabil"
                    )
                ):

                    cod_f_badge = (
                        f'&nbsp;'
                        f'<span style="'
                        f'background:#004d40; '
                        f'color:#a7ffeb; '
                        f'padding:2px 8px; '
                        f'border-radius:4px; '
                        f'font-weight:600; '
                        f'font-size:12px;">'
                        f'🏢 Cód. Fornecedor: '
                        f'{fornec_info["codigo_contabil"]}'
                        f'</span>'
                    )

                else:

                    cod_f_badge = (
                        f'&nbsp;'
                        f'<span style="'
                        f'background:#5d4037; '
                        f'color:#ffccbc; '
                        f'padding:2px 8px; '
                        f'border-radius:4px; '
                        f'font-weight:500; '
                        f'font-size:12px;">'
                        f'🏢 Cód. Fornecedor: '
                        f'5 (Diversos)'
                        f'</span>'
                    )

                cfop_badge = ""

                if doc.get(
                    "cfop_destaque"
                ):

                    cfop_badge = (
                        f'&nbsp;'
                        f'<span style="'
                        f'background:#1a237e; '
                        f'color:#c5cae9; '
                        f'padding:2px 8px; '
                        f'border-radius:4px; '
                        f'font-weight:600; '
                        f'font-size:12px;">'
                        f'📑 CFOP '
                        f'{doc["cfop_destaque"]}'
                        f'</span>'
                    )

                st.markdown(
                    f"**NF {doc['nNF']}** — "
                    f"{doc['fornecedor']} "
                    f"&nbsp;{tipo_badge_html}"
                    f"{cod_f_badge}"
                    f"{cfop_badge}",
                    unsafe_allow_html=True,
                )

                desc_info = ""

                if (
                    doc.get(
                        "valor_desconto",
                        0
                    )
                    > 0
                ):

                    desc_info = (
                        " | Desc: "
                        + _fmt_brl(
                            doc.get(
                                "valor_desconto",
                                0
                            )
                        )
                    )

                st.caption(
                    f"CNPJ: "
                    f"{doc.get('fornecedor_cnpj', 'N/A')} | "
                    f"{doc.get('fornecedor_cidade', '')}/"
                    f"{doc.get('fornecedor_uf', '')} | "
                    f"{doc.get('natureza_op', '')}"
                    f"{desc_info}"
                )

            with h2:

                st.metric(
                    "Valor Total Líquido",
                    _fmt_brl(
                        doc.get(
                            "valor_total",
                            0
                        )
                    ),
                )

            with h3:

                st.markdown(
                    badge_html,
                    unsafe_allow_html=True,
                )

            # ═══════════════════════════════════════════════════════
            # RETORNO
            # ═══════════════════════════════════════════════════════

            if tipo_nf == "Retorno/Devolução":

                cfops_str = ", ".join(
                    doc.get(
                        "cfops_nota",
                        []
                    )
                ) or "—"

                st.markdown(
                    f"""
                    <div class="retorno-tag">
                    ⚠️ <strong>NOTA DE RETORNO / DEVOLUÇÃO</strong>
                    — CFOPs: {cfops_str}.
                    Esta nota representa uma devolução e deve ser
                    tratada como estorno no lançamento contábil.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # ═══════════════════════════════════════════════════════
            # CONTEXTO XML
            # ═══════════════════════════════════════════════════════

            contexto = doc.get(
                "contexto_classificacao",
                {}
            )

            if isinstance(
                contexto,
                dict
            ):

                cno_ctx = contexto.get(
                    "cno",
                    ""
                )

                natureza_ctx = contexto.get(
                    "natureza",
                    ""
                )

                cfop_ctx = contexto.get(
                    "cfops_nota",
                    ""
                )

                ncm_ctx = contexto.get(
                    "itens_ncm",
                    ""
                )

                if (
                    cno_ctx
                    or natureza_ctx
                    or cfop_ctx
                    or ncm_ctx
                ):

                    with st.expander(
                        "🔎 Contexto fiscal utilizado na classificação",
                        expanded=False,
                    ):

                        st.markdown(
                            f"""
                            <div class="contexto-fiscal">
                            <strong>CNO:</strong> {cno_ctx or "não identificado"}<br>
                            <strong>Natureza:</strong> {natureza_ctx or "não informada"}<br>
                            <strong>CFOPs:</strong> {cfop_ctx or "não informado"}<br>
                            <strong>NCMs:</strong> {ncm_ctx or "não informado"}<br>
                            <strong>Itens:</strong> {contexto.get("itens_descricao", "") or "não informado"}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

            # ═══════════════════════════════════════════════════════
            # DETALHES + CATEGORIA
            # ═══════════════════════════════════════════════════════

            d1, d2 = st.columns(2)

            with d1:

                st.markdown(
                    f"**Emissao:** "
                    f"{doc['data_emissao']} | "
                    f"**Pagamento Base:** "
                    f"{doc.get('pagamento', 'N/A')} | "
                    f"**Itens NF:** "
                    f"{doc.get('qtd_itens', 0)} | "
                    f"**Parcelas:** "
                    f"{doc.get('qtd_parcelas', 1)}"
                )

                st.markdown(
                    f"**Cliente:** "
                    f"{doc['cliente']}"
                )

            with d2:

                opts = list(
                    CATEGORY_OPTIONS
                )

                if (
                    cat not in opts
                    and cat != "OUTRA (digitar)"
                ):
                    opts.insert(
                        0,
                        cat
                    )

                cat_idx = (
                    opts.index(cat)
                    if cat in opts
                    else len(opts) - 1
                )

                selected_cat = st.selectbox(
                    "Categoria de Despesa",
                    opts,
                    index=cat_idx,
                    key=f"cat_{uid}",
                    help=(
                        ai_reason
                        if ai_reason
                        else None
                    ),
                )

                if (
                    selected_cat
                    == "OUTRA (digitar)"
                ):

                    custom_cat = st.text_input(
                        "Digite a categoria",
                        value=(
                            ""
                            if cat
                            == "OUTRA (digitar)"
                            else cat
                        ),
                        key=(
                            f"custom_cat_{uid}"
                        ),
                    )

                    if custom_cat:

                        st.session_state[
                            "categories"
                        ][uid] = (
                            custom_cat.upper()
                        )

                        cod, cod_info = (
                            _resolve_codigo_contabil(
                                custom_cat.upper(),
                                st.session_state[
                                    "obras"
                                ].get(
                                    uid,
                                    "CUSTO DA OBRA GERAL"
                                ),
                            )
                        )

                        st.session_state[
                            "codigos"
                        ][uid] = cod

                        st.session_state[
                            "codigos_info"
                        ][uid] = cod_info

                elif selected_cat != cat:

                    st.session_state[
                        "categories"
                    ][uid] = selected_cat

                    cod, cod_info = (
                        _resolve_codigo_contabil(
                            selected_cat,
                            st.session_state[
                                "obras"
                            ].get(
                                uid,
                                "CUSTO DA OBRA GERAL"
                            ),
                        )
                    )

                    st.session_state[
                        "codigos"
                    ][uid] = cod

                    st.session_state[
                        "codigos_info"
                    ][uid] = cod_info

            # ═══════════════════════════════════════════════════════
            # OBRA
            # ═══════════════════════════════════════════════════════

            obra_opts = list(
                OBRA_OPTIONS
            )

            if (
                obra not in obra_opts
                and obra != "OUTRA (digitar)"
            ):

                obra_opts.insert(
                    0,
                    obra
                )

            obra_idx = (
                obra_opts.index(obra)
                if obra in obra_opts
                else len(obra_opts) - 1
            )

            selected_obra = st.selectbox(
                "Obra / Centro de Custo (Segmento com CNO)",
                obra_opts,
                index=obra_idx,
                key=f"obra_{uid}",
            )

            if (
                selected_obra
                == "OUTRA (digitar)"
            ):

                custom_obra = st.text_input(
                    "Digite o nome da obra",
                    value=(
                        ""
                        if obra
                        == "OUTRA (digitar)"
                        else obra
                    ),
                    key=(
                        f"custom_obra_{uid}"
                    ),
                )

                if custom_obra:

                    st.session_state[
                        "obras"
                    ][uid] = (
                        custom_obra.upper()
                    )

                    cod, cod_info = (
                        _resolve_codigo_contabil(
                            st.session_state[
                                "categories"
                            ].get(
                                uid,
                                "DESPESAS COM MATERIAL DIVERSOS"
                            ),
                            custom_obra.upper(),
                        )
                    )

                    st.session_state[
                        "codigos"
                    ][uid] = cod

                    st.session_state[
                        "codigos_info"
                    ][uid] = cod_info

            elif selected_obra != obra:

                st.session_state[
                    "obras"
                ][uid] = selected_obra

                cod, cod_info = (
                    _resolve_codigo_contabil(
                        st.session_state[
                            "categories"
                        ].get(
                            uid,
                            "DESPESAS COM MATERIAL DIVERSOS"
                        ),
                        selected_obra,
                    )
                )

                st.session_state[
                    "codigos"
                ][uid] = cod

                st.session_state[
                    "codigos_info"
                ][uid] = cod_info

            # ═══════════════════════════════════════════════════════
            # CONTAS
            # ═══════════════════════════════════════════════════════

            curr_cat = st.session_state[
                "categories"
            ].get(
                uid,
                "DESPESAS COM MATERIAL DIVERSOS"
            )

            curr_obra = st.session_state[
                "obras"
            ].get(
                uid,
                "CUSTO DA OBRA GERAL"
            )

            codigo = st.session_state[
                "codigos"
            ].get(
                uid,
                ""
            )

            cod_info = (
                st.session_state
                .get(
                    "codigos_info",
                    {}
                )
                .get(
                    uid
                )
            )

            if (
                not codigo
                or not cod_info
            ):

                codigo, cod_info = (
                    _resolve_codigo_contabil(
                        curr_cat,
                        curr_obra,
                    )
                )

                st.session_state[
                    "codigos"
                ][uid] = codigo

                st.session_state[
                    "codigos_info"
                ][uid] = cod_info

            is_fallback = (
                codigo.startswith("~")
                or cod_info.get(
                    "is_fallback",
                    False
                )
            )

            codigo_display = (
                codigo.lstrip("~")
                if codigo
                else ""
            )

            # ═══════════════════════════════════════════════════════
            # OBRA OBJ
            # ═══════════════════════════════════════════════════════

            try:
                obra_obj = (
                    contas_db
                    .get_obra_by_identifier(
                        curr_obra
                    )
                )
            except Exception:
                obra_obj = None

            obra_nome_disp = (
                obra_obj.get(
                    "nome_display",
                    curr_obra
                )
                if obra_obj
                else curr_obra
            )

            obra_cod_disp = (
                obra_obj.get(
                    "codigo",
                    271
                )
                if obra_obj
                else 271
            )

            obra_cls_disp = (
                obra_obj.get(
                    "classificacao",
                    "3.1.1.01"
                )
                if obra_obj
                else "3.1.1.01"
            )

            obra_cno_disp = (
                obra_obj.get("cno")
                if obra_obj
                else doc.get(
                    "cno_sugerido"
                )
            )

            # ═══════════════════════════════════════════════════════
            # SEGMENTO
            # ═══════════════════════════════════════════════════════

            if obra_cno_disp:

                st.markdown(
                    f"""
                    <div class="cno-tag">
                    🏗️ <strong>Segmento / Obra:</strong>
                    {obra_nome_disp}
                    &nbsp;|&nbsp;
                    <strong>Cód. Conta:</strong>
                    <span class="code-value"
                    style="background:#2e7d32;
                    color:white;
                    padding:1px 6px;
                    border-radius:3px;">
                    {obra_cod_disp}
                    </span>
                    ({obra_cls_disp})
                    &nbsp;|&nbsp;
                    <strong>CNO:</strong>
                    {obra_cno_disp}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            else:

                st.markdown(
                    f"""
                    <div class="obras-gerais-tag">
                    🏗️ <strong>Segmento:</strong>
                    CUSTO DA OBRA GERAL
                    &nbsp;|&nbsp;
                    <strong>Cód. Conta:</strong>
                    <span class="code-value"
                    style="background:#dc3545;
                    color:white;
                    padding:1px 6px;
                    border-radius:3px;">
                    {obra_cod_disp}
                    </span>
                    ({obra_cls_disp})
                    &nbsp;|&nbsp;
                    <small>
                    Classificada como Obra Geral
                    (sem CNO específico)
                    </small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # ═══════════════════════════════════════════════════════
            # SUBCLASSE
            # ═══════════════════════════════════════════════════════

            subclasse_classif = (
                cod_info.get(
                    "classificacao",
                    ""
                )
            )

            classif_str = (
                f" ({subclasse_classif})"
                if subclasse_classif
                else ""
            )

            if is_fallback:

                st.markdown(
                    f"""
                    <div class="codigo-fallback-tag">
                    ⚠️ <strong>
                    Subclasse / Conta Analítica
                    (Fallback Obra Geral):
                    </strong>
                    <span class="code-value">
                    {codigo_display}
                    </span>
                    {classif_str}
                    — {curr_cat}
                    &nbsp;
                    <small>
                    — Subclasse não mapeada nesta obra
                    específica, usando conta da Obra Geral
                    </small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            elif codigo_display:

                st.markdown(
                    f"""
                    <div class="codigo-tag">
                    🏛️ <strong>
                    Subclasse / Conta Analítica:
                    </strong>
                    <span class="code-value">
                    {codigo_display}
                    </span>
                    {classif_str}
                    — {curr_cat}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            else:

                st.markdown(
                    f"""
                    <div class="alert-missing">
                    ⚠️ <strong>Subclasse:</strong>
                    {curr_cat}
                    — Conta contábil não mapeada
                    para esta combinação.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # ═══════════════════════════════════════════════════════
            # MOTIVO DA CLASSIFICAÇÃO
            # ═══════════════════════════════════════════════════════

            if ai_reason:

                st.markdown(
                    f"""
                    <div class="classificacao-xml">
                    🔎 <strong>Rastreabilidade da classificação:</strong>
                    {ai_reason}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # ═══════════════════════════════════════════════════════
            # INFO ADICIONAL
            # ═══════════════════════════════════════════════════════

            if doc.get("infAdic"):

                with st.expander(
                    "Informacoes Adicionais",
                    expanded=False,
                ):

                    st.text(
                        doc["infAdic"]
                    )

            # ═══════════════════════════════════════════════════════
            # PARCELAS
            # ═══════════════════════════════════════════════════════

            parcelas = doc.get(
                "parcelas",
                []
            )

            if not parcelas:

                parcelas = [
                    {
                        "nDup": "1",
                        "dVenc": doc.get(
                            "data_emissao"
                        ),
                        "vDup": doc.get(
                            "valor_total"
                        ),
                    }
                ]

            with st.expander(
                f"Parcelas ({len(parcelas)})",
                expanded=True,
            ):

                parcela_rows = []

                for p in parcelas:

                    try:
                        valor_parcela = float(
                            p.get(
                                "vDup"
                            )
                            or doc.get(
                                "valor_total"
                            )
                            or 0
                        )
                    except Exception:
                        valor_parcela = 0.0

                    parcela_rows.append(
                        {
                            "Parcela": p.get(
                                "nDup",
                                "1"
                            ),
                            "Vencimento": p.get(
                                "dVenc",
                                doc.get(
                                    "data_emissao"
                                )
                            ),
                            "Valor (R$)": _fmt_brl(
                                valor_parcela
                            ),
                        }
                    )

                st.dataframe(
                    pd.DataFrame(
                        parcela_rows
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            # ═══════════════════════════════════════════════════════
            # ITENS
            # ═══════════════════════════════════════════════════════

            with st.expander(
                f"Itens da Nota "
                f"({doc.get('qtd_itens', 0)} produtos)",
                expanded=True,
            ):

                if doc.get("itens"):

                    df_items = pd.DataFrame(
                        doc["itens"]
                    )

                    cols = [
                        c
                        for c in [
                            "codigo",
                            "descricao",
                            "ncm",
                            "cfop",
                            "qtd",
                            "unidade",
                            "valor_unit",
                            "valor_total",
                        ]
                        if c in df_items.columns
                    ]

                    names = {
                        "codigo": "Codigo",
                        "descricao": "Descricao",
                        "ncm": "NCM",
                        "cfop": "CFOP",
                        "qtd": "Qtd",
                        "unidade": "Un",
                        "valor_unit": "Vl. Unitario",
                        "valor_total": "Vl. Total",
                    }

                    st.dataframe(
                        df_items[
                            cols
                        ].rename(
                            columns=names
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                else:

                    st.warning(
                        "Nenhum item encontrado nesta nota."
                    )

            # ═══════════════════════════════════════════════════════
            # BOTÕES
            # ═══════════════════════════════════════════════════════

            a1, a2, a3, a4 = st.columns(
                [1, 1, 1, 3]
            )

            if a1.button(
                "Aprovar",
                key=f"apv_{uid}",
                type="primary",
                use_container_width=True,
            ):

                st.session_state[
                    "approvals"
                ][uid] = "Aprovado"

                st.rerun()

            if a2.button(
                "Rejeitar",
                key=f"rej_{uid}",
                use_container_width=True,
            ):

                st.session_state[
                    "approvals"
                ][uid] = "Rejeitado"

                st.rerun()

            if a3.button(
                "Pendente",
                key=f"pnd_{uid}",
                use_container_width=True,
            ):

                st.session_state[
                    "approvals"
                ][uid] = "Pendente"

                st.rerun()


# ═══════════════════════════════════════════════════════════════════
# PAGE 2 — EXPORTAÇÃO
# ═══════════════════════════════════════════════════════════════════

elif page == "Exportacao":

    st.markdown(
        "# Exportacao de Dados"
    )

    st.caption(
        "Visualize e exporte os dados triados "
        "para Excel ou CSV."
    )

    total_items = (
        len(
            st.session_state[
                "processed_data"
            ]
        )
        + len(
            st.session_state[
                "lancamentos_manuais"
            ]
        )
    )

    if total_items == 0:

        st.info(
            "Nenhum dado processado. "
            "Va para a aba Triagem ou "
            "Lancamento Manual primeiro."
        )

        st.stop()

    export_scope = st.radio(
        "Escopo das NFs",
        [
            "Somente Aprovados",
            "Todos Processados",
            "Aprovados + Pendentes",
        ],
        horizontal=True,
    )

    all_data = st.session_state[
        "processed_data"
    ]

    if export_scope == "Somente Aprovados":

        export_list = [
            d
            for d in all_data
            if st.session_state[
                "approvals"
            ].get(
                d["uid"]
            )
            == "Aprovado"
        ]

    elif export_scope == "Aprovados + Pendentes":

        export_list = [
            d
            for d in all_data
            if st.session_state[
                "approvals"
            ].get(
                d["uid"]
            )
            in (
                "Aprovado",
                "Pendente",
            )
        ]

    else:

        export_list = list(
            all_data
        )

    lancamentos = (
        st.session_state[
            "lancamentos_manuais"
        ]
    )

    incluir_manuais = st.checkbox(
        "Incluir Lancamentos Manuais na exportacao",
        value=True,
    )

    # ═══════════════════════════════════════════════════════════════
    # MÉTRICAS
    # ═══════════════════════════════════════════════════════════════

    m1, m2, m3, m4, m5, m6 = st.columns(6)

    total_val = sum(
        d.get(
            "valor_total",
            0
        )
        or 0
        for d in export_list
    )

    total_val_manual = (
        sum(
            float(
                m.get(
                    "valor",
                    0
                )
                or 0
            )
            for m in lancamentos
        )
        if incluir_manuais
        else 0
    )

    m1.metric(
        "NFs",
        len(export_list)
    )

    m2.metric(
        "Lançamentos Manuais",
        len(lancamentos)
    )

    m3.metric(
        "Valor NFs",
        _fmt_brl(total_val)
    )

    m4.metric(
        "Valor Manuais",
        _fmt_brl(total_val_manual)
    )

    m5.metric(
        "Total Geral",
        _fmt_brl(
            total_val
            + total_val_manual
        )
    )

    retornos = sum(
        1
        for d in export_list
        if d.get(
            "tipo_nf_classificado"
        )
        == "Retorno/Devolução"
    )

    m6.metric(
        "Retornos/Devoluções",
        retornos
    )

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # TABELA PRINCIPAL
    # ═══════════════════════════════════════════════════════════════

    rows = []

    for d in export_list:

        uid = d["uid"]

        cat = st.session_state[
            "categories"
        ].get(
            uid,
            "DESPESAS COM MATERIAL DIVERSOS"
        )

        obra = st.session_state[
            "obras"
        ].get(
            uid,
            "CUSTO DA OBRA GERAL"
        )

        codigo = st.session_state[
            "codigos"
        ].get(
            uid,
            ""
        )

        if not codigo:

            codigo, _ = (
                _resolve_codigo_contabil(
                    cat,
                    obra
                )
            )

        tipo_nf = d.get(
            "tipo_nf_classificado",
            "Entrada"
        )

        parcelas = d.get(
            "parcelas",
            []
        )

        if not parcelas:

            parcelas = [
                {
                    "nDup": "1",
                    "dVenc": d.get(
                        "data_emissao"
                    ),
                    "vDup": d.get(
                        "valor_total"
                    ),
                }
            ]

        for p in parcelas:

            try:
                valor_parcela = float(
                    p.get(
                        "vDup"
                    )
                    or d.get(
                        "valor_total"
                    )
                    or 0
                )
            except Exception:
                valor_parcela = 0.0

            rows.append(
                {
                    "Tipo NF": tipo_nf,
                    "Fornecedor": d[
                        "fornecedor"
                    ],
                    "Vencimento Parcela": p.get(
                        "dVenc",
                        ""
                    ),
                    "Valor Parcela": valor_parcela,
                    "NF": d["nNF"],
                    "Parcela": p.get(
                        "nDup",
                        "1"
                    ),
                    "Data Emissão NF": d[
                        "data_emissao"
                    ],
                    "CNPJ Fornecedor": d.get(
                        "fornecedor_cnpj",
                        ""
                    ),
                    "Cliente": d[
                        "cliente"
                    ],
                    "Valor Total NF": d[
                        "valor_total"
                    ],
                    "Codigo Contabil": codigo.lstrip(
                        "~"
                    ),
                    "Categoria": cat,
                    "Obra": obra,
                    "CNO": d.get(
                        "cno_sugerido",
                        ""
                    ),
                    "Pagamento": d.get(
                        "pagamento",
                        ""
                    ),
                    "Qtd Itens": d.get(
                        "qtd_itens",
                        0
                    ),
                    "Status": st.session_state[
                        "approvals"
                    ].get(
                        uid,
                        "Pendente"
                    ),
                    "Info Adicional": (
                        d.get(
                            "infAdic",
                            ""
                        )
                        or ""
                    )[:200],
                }
            )

    df_export = pd.DataFrame(
        rows
    )

    # ═══════════════════════════════════════════════════════════════
    # MANUAIS
    # ═══════════════════════════════════════════════════════════════

    if (
        incluir_manuais
        and lancamentos
    ):

        manual_rows_view = []

        for m in lancamentos:

            manual_rows_view.append(
                {
                    "Tipo NF": "Manual",
                    "Fornecedor": m.get(
                        "fornecedor",
                        ""
                    ),
                    "Vencimento Parcela": m.get(
                        "vencimento",
                        ""
                    ),
                    "Valor Parcela": float(
                        m.get(
                            "valor",
                            0
                        )
                        or 0
                    ),
                    "NF": m.get(
                        "nr_documento",
                        ""
                    ),
                    "Parcela": "1",
                    "Data Emissão NF": m.get(
                        "data",
                        ""
                    ),
                    "CNPJ Fornecedor": m.get(
                        "cnpj",
                        ""
                    ),
                    "Cliente": m.get(
                        "cliente",
                        ""
                    ),
                    "Valor Total NF": float(
                        m.get(
                            "valor",
                            0
                        )
                        or 0
                    ),
                    "Codigo Contabil": m.get(
                        "codigo_contabil",
                        ""
                    ).lstrip("~"),
                    "Categoria": m.get(
                        "categoria",
                        ""
                    ),
                    "Obra": m.get(
                        "obra",
                        ""
                    ),
                    "CNO": m.get(
                        "cno",
                        ""
                    ),
                    "Pagamento": m.get(
                        "forma_pagamento",
                        ""
                    ),
                    "Qtd Itens": 0,
                    "Status": "Aprovado",
                    "Info Adicional": m.get(
                        "observacao",
                        ""
                    ),
                }
            )

        df_manual_view = pd.DataFrame(
            manual_rows_view
        )

        df_combined = pd.concat(
            [
                df_export,
                df_manual_view,
            ],
            ignore_index=True,
        )

    else:

        df_combined = df_export

    # ═══════════════════════════════════════════════════════════════
    # TABS
    # ═══════════════════════════════════════════════════════════════

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "Tabela Geral (Parcelas)",
            "Por Obra",
            "Por Categoria",
            "Resumo por Nota",
            "Retornos/Devoluções",
            "💳 Boletos a Vencer",
        ]
    )

    with tab1:

        st.dataframe(
            df_combined,
            use_container_width=True,
            hide_index=True,
            height=400,
        )

    with tab2:

        if not df_combined.empty:

            df_obra = (
                df_combined
                .groupby("Obra")
                .agg(
                    Notas=(
                        "NF",
                        "nunique"
                    ),
                    Valor=(
                        "Valor Parcela",
                        "sum"
                    ),
                )
                .reset_index()
            )

            df_obra[
                "Valor Fmt"
            ] = df_obra[
                "Valor"
            ].apply(
                _fmt_brl
            )

            st.dataframe(
                df_obra[
                    [
                        "Obra",
                        "Notas",
                        "Valor Fmt",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.bar_chart(
                df_obra.set_index(
                    "Obra"
                )["Valor"]
            )

    with tab3:

        if not df_combined.empty:

            df_cat = (
                df_combined
                .groupby("Categoria")
                .agg(
                    Notas=(
                        "NF",
                        "nunique"
                    ),
                    Valor=(
                        "Valor Parcela",
                        "sum"
                    ),
                )
                .reset_index()
            )

            df_cat[
                "Valor Fmt"
            ] = df_cat[
                "Valor"
            ].apply(
                _fmt_brl
            )

            st.dataframe(
                df_cat[
                    [
                        "Categoria",
                        "Notas",
                        "Valor Fmt",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.bar_chart(
                df_cat.set_index(
                    "Categoria"
                )["Valor"]
            )

    with tab4:

        note_rows = []

        for d in export_list:

            uid = d["uid"]

            cat = st.session_state[
                "categories"
            ].get(
                uid,
                "DESPESAS COM MATERIAL DIVERSOS"
            )

            obra = st.session_state[
                "obras"
            ].get(
                uid,
                "CUSTO DA OBRA GERAL"
            )

            codigo = (
                st.session_state[
                    "codigos"
                ]
                .get(
                    uid,
                    ""
                )
                .lstrip("~")
            )

            note_rows.append(
                {
                    "Tipo NF": d.get(
                        "tipo_nf_classificado",
                        "Entrada"
                    ),
                    "Fornecedor": d[
                        "fornecedor"
                    ],
                    "NF": d[
                        "nNF"
                    ],
                    "Valor Total": d[
                        "valor_total"
                    ],
                    "Data Emissão": d[
                        "data_emissao"
                    ],
                    "Obra": obra,
                    "Categoria": cat,
                    "Codigo Contabil": codigo,
                    "CNO": d.get(
                        "cno_sugerido",
                        ""
                    ),
                    "Pagamento": d.get(
                        "pagamento",
                        ""
                    ),
                    "Qtd Itens": d.get(
                        "qtd_itens",
                        0
                    ),
                    "Status": st.session_state[
                        "approvals"
                    ].get(
                        uid,
                        "Pendente"
                    ),
                }
            )

        df_by_note = pd.DataFrame(
            note_rows
        )

        st.dataframe(
            df_by_note,
            use_container_width=True,
            hide_index=True,
            height=400,
        )

    with tab5:

        if df_combined.empty:

            st.info(
                "Nenhuma nota."
            )

        else:

            df_ret = (
                df_combined[
                    df_combined[
                        "Tipo NF"
                    ]
                    == "Retorno/Devolução"
                ]
            )

            if df_ret.empty:

                st.success(
                    "✅ Nenhuma nota de retorno/"
                    "devolucao identificada no lote."
                )

            else:

                st.warning(
                    f"⚠️ {len(df_ret)} parcela(s) "
                    "de Retorno/Devolucao identificadas:"
                )

                st.dataframe(
                    df_ret,
                    use_container_width=True,
                    hide_index=True,
                    height=300,
                )

                total_ret = (
                    df_ret[
                        "Valor Parcela"
                    ].sum()
                )

                st.metric(
                    "Total em Retornos",
                    _fmt_brl(total_ret)
                )
    # ═══════════════════════════════════════════════════════════════
    # TAB 6 — BOLETOS A VENCER
    # ═══════════════════════════════════════════════════════════════

    with tab6:

        st.markdown("### 💳 Boletos a Vencer")

        st.caption(
            "Exibe somente notas com forma de pagamento Boleto "
            "e parcelas com vencimento posterior à emissão. "
            "Pagamentos à vista são ignorados."
        )

        boletos_rows = []

        # Evita repetir a mesma parcela quando a NF foi
        # separada internamente por CFOP.
        boletos_vistos = set()

        for d in export_list:

            # --------------------------------------------------
            # SOMENTE BOLETO
            # --------------------------------------------------

            pagamento_codigo = str(
                d.get("pagamento_tipo_cod", "") or ""
            ).strip()

            pagamento_texto = str(
                d.get("pagamento", "") or ""
            ).upper()

            eh_boleto = (
                pagamento_codigo == "15"
                or "BOLETO" in pagamento_texto
            )

            if not eh_boleto:
                continue

            # --------------------------------------------------
            # IGNORA PAGAMENTO À VISTA
            # --------------------------------------------------

            if d.get("is_a_vista", False):
                continue

            fornecedor = d.get(
                "fornecedor",
                ""
            )

            cnpj = d.get(
                "fornecedor_cnpj",
                ""
            )

            # Código contábil do fornecedor já identificado na Triagem.
            # Usa o mesmo cadastro/mapeamento já existente no sistema.
            uid_boleto = d.get("uid", "")

            fornec_info_boleto = (
                st.session_state
                .get("fornecedores_map", {})
                .get(uid_boleto, {})
                or {}
            )

            codigo_fornecedor = str(
                fornec_info_boleto.get("codigo_contabil", "")
                or ""
            ).strip()

            numero_nf = d.get(
                "nNF",
                ""
            )

            data_emissao = d.get(
                "data_emissao",
                ""
            )

            parcelas = d.get(
                "parcelas",
                []
            ) or []

            # --------------------------------------------------
            # ANALISA CADA DUPLICATA / BOLETO
            # --------------------------------------------------

            for p in parcelas:

                vencimento = str(
                    p.get("dVenc", "") or ""
                ).strip()

                numero_parcela = str(
                    p.get("nDup", "1") or "1"
                ).strip()

                try:
                    valor = float(
                        p.get("vDup", 0) or 0
                    )
                except (TypeError, ValueError):
                    valor = 0.0

                if not vencimento:
                    continue

                # ----------------------------------------------
                # CONVERTE DATAS
                # ----------------------------------------------

                venc_dt = pd.to_datetime(
                    vencimento,
                    errors="coerce"
                )

                emissao_dt = pd.to_datetime(
                    data_emissao,
                    errors="coerce"
                )

                if pd.isna(venc_dt):
                    continue

                # ----------------------------------------------
                # IGNORA BOLETO À VISTA
                # vencimento = emissão
                # ----------------------------------------------

                if (
                    not pd.isna(emissao_dt)
                    and venc_dt.date()
                    <= emissao_dt.date()
                ):
                    continue

                # ----------------------------------------------
                # EVITA DUPLICIDADE
                # ----------------------------------------------

                chave_boleto = (
                    str(numero_nf),
                    str(cnpj),
                    numero_parcela,
                    venc_dt.date(),
                    round(valor, 2),
                )

                if chave_boleto in boletos_vistos:
                    continue

                boletos_vistos.add(
                    chave_boleto
                )

                # ----------------------------------------------
                # SITUAÇÃO DO VENCIMENTO
                # ----------------------------------------------

                hoje = pd.Timestamp.today().normalize()

                if venc_dt.normalize() < hoje:
                    situacao = "🔴 Vencido"

                elif venc_dt.normalize() == hoje:
                    situacao = "🟠 Vence hoje"

                else:

                    dias = (
                        venc_dt.normalize()
                        - hoje
                    ).days

                    situacao = (
                        f"🟢 A vencer ({dias} dias)"
                    )

                # ----------------------------------------------
                # ADICIONA À TABELA
                # ----------------------------------------------

                boletos_rows.append(
                    {
                        "Vencimento": venc_dt,
                        "Fornecedor": fornecedor,
                        "Código Fornecedor": codigo_fornecedor,
                        "CNPJ": cnpj,
                        "NF": numero_nf,
                        "Parcela": numero_parcela,
                        "Valor": valor,
                        "Situação": situacao,
                        "Emissão": data_emissao,
                    }
                )

        # ======================================================
        # MONTA TABELA
        # ======================================================

        if not boletos_rows:

            st.success(
                "Nenhum boleto a prazo encontrado "
                "nas notas carregadas."
            )

        else:

            df_boletos = pd.DataFrame(
                boletos_rows
            )

            # Mais próximo do vencimento primeiro
            df_boletos = (
                df_boletos
                .sort_values(
                    by="Vencimento",
                    ascending=True
                )
                .reset_index(drop=True)
            )

            # ==================================================
            # INDICADORES
            # ==================================================

            total_boletos = len(
                df_boletos
            )

            valor_total_boletos = (
                df_boletos["Valor"].sum()
            )

            hoje = (
                pd.Timestamp
                .today()
                .normalize()
            )

            vencidos = (
                df_boletos[
                    df_boletos["Vencimento"]
                    .dt.normalize()
                    < hoje
                ]
            )

            valor_vencido = (
                vencidos["Valor"].sum()
                if not vencidos.empty
                else 0
            )

            m1, m2, m3 = st.columns(3)

            m1.metric(
                "Boletos",
                total_boletos
            )

            m2.metric(
                "Total em boletos",
                _fmt_brl(
                    valor_total_boletos
                )
            )

            m3.metric(
                "Total vencido",
                _fmt_brl(
                    valor_vencido
                )
            )

            st.divider()

            # ==================================================
            # FORMATAÇÃO PARA EXIBIÇÃO
            # ==================================================

            df_boletos_view = (
                df_boletos.copy()
            )

            df_boletos_view[
                "Vencimento"
            ] = (
                df_boletos_view[
                    "Vencimento"
                ]
                .dt.strftime(
                    "%d/%m/%Y"
                )
            )

            df_boletos_view[
                "Valor"
            ] = (
                df_boletos_view[
                    "Valor"
                ]
                .apply(_fmt_brl)
            )

            st.dataframe(
                df_boletos_view[
                    [
                        "Vencimento",
                        "Fornecedor",
                        "Código Fornecedor",
                        "CNPJ",
                        "NF",
                        "Parcela",
                        "Valor",
                        "Situação",
                        "Emissão",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                height=450,
            )

            # ==================================================
            # DOWNLOAD EXCEL — BOLETOS A VENCER
            # ==================================================

            from io import BytesIO

            excel_buffer = BytesIO()

            # Usa uma cópia própria para o Excel.
            # Não altera df_boletos nem outras partes do sistema.
            df_excel_boletos = df_boletos.copy()

            # Datas como datas reais do Excel
            df_excel_boletos["Vencimento"] = (
                pd.to_datetime(
                    df_excel_boletos["Vencimento"],
                    errors="coerce"
                )
            )

            df_excel_boletos["Emissão"] = (
                pd.to_datetime(
                    df_excel_boletos["Emissão"],
                    errors="coerce"
                )
            )

            # Remove emojis da situação para deixar
            # o arquivo Excel mais limpo
            df_excel_boletos["Situação"] = (
                df_excel_boletos["Situação"]
                .astype(str)
                .str.replace(
                    r"^[🔴🟠🟢]\s*",
                    "",
                    regex=True
                )
            )

            # Ordem das colunas no Excel
            df_excel_boletos = df_excel_boletos[
                [
                    "Vencimento",
                    "Fornecedor",
                    "Código Fornecedor",
                    "CNPJ",
                    "NF",
                    "Parcela",
                    "Valor",
                    "Situação",
                    "Emissão",
                ]
            ]

            with pd.ExcelWriter(
                excel_buffer,
                engine="openpyxl"
            ) as writer:

                df_excel_boletos.to_excel(
                    writer,
                    index=False,
                    sheet_name="Boletos a Vencer"
                )

                # ----------------------------------------------
                # FORMATAÇÃO DO EXCEL
                # ----------------------------------------------

                worksheet = writer.sheets[
                    "Boletos a Vencer"
                ]

                # Congela cabeçalho
                worksheet.freeze_panes = "A2"

                # Ativa filtro
                worksheet.auto_filter.ref = (
                    worksheet.dimensions
                )

                # Largura das colunas
                worksheet.column_dimensions["A"].width = 15
                worksheet.column_dimensions["B"].width = 40
                worksheet.column_dimensions["C"].width = 18
                worksheet.column_dimensions["D"].width = 20
                worksheet.column_dimensions["E"].width = 15
                worksheet.column_dimensions["F"].width = 12
                worksheet.column_dimensions["G"].width = 18
                worksheet.column_dimensions["H"].width = 25
                worksheet.column_dimensions["I"].width = 15

                # Formatação das linhas
                for row in range(
                    2,
                    worksheet.max_row + 1
                ):

                    # Vencimento
                    worksheet[
                        f"A{row}"
                    ].number_format = "DD/MM/YYYY"

                    # Valor
                    worksheet[
                        f"G{row}"
                    ].number_format = (
                        'R$ #,##0.00'
                    )

                    # Emissão
                    worksheet[
                        f"I{row}"
                    ].number_format = "DD/MM/YYYY"

            excel_buffer.seek(0)

            st.download_button(
                label="📥 Baixar boletos a vencer em Excel",
                data=excel_buffer.getvalue(),
                file_name="boletos_a_vencer.xlsx",
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                use_container_width=True,
                key="download_boletos_vencer_excel",
            )
    # ═══════════════════════════════════════════════════════════════
    # DOWNLOADS
    # ═══════════════════════════════════════════════════════════════

    st.divider()

    st.markdown(
        "### 📥 Opções de Download"
    )

    dc1, dc2, dc3, dc4 = st.columns(4)

    dominio_data = export_to_dominio_excel(
        export_list,
        st.session_state[
            "categories"
        ],
        st.session_state[
            "obras"
        ],
        st.session_state[
            "codigos"
        ],
        st.session_state[
            "approvals"
        ],
        fornecedores_map=(
            st.session_state.get(
                "fornecedores_map",
                {}
            )
        ),
    )

    if dominio_data:

        dc1.download_button(
            "⭐ Baixar Modelo Domínio (.xlsx)",
            data=dominio_data,
            file_name=(
                "lancamentos_dominio_hikari.xlsx"
            ),
            mime=(
                "application/"
                "vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
            use_container_width=True,
            type="primary",
            help=(
                "Planilha formatada conforme "
                "o modelo de lançamentos do "
                "Domínio Contábil."
            ),
        )

    excel_data = export_to_excel(
        export_list,
        st.session_state[
            "categories"
        ],
        st.session_state[
            "obras"
        ],
        st.session_state[
            "approvals"
        ],
        codigos=st.session_state[
            "codigos"
        ],
        lancamentos_manuais=(
            lancamentos
            if incluir_manuais
            else []
        ),
    )

    if excel_data:

        dc2.download_button(
            "⬇️ Baixar Relatório Multi-Aba (.xlsx)",
            data=excel_data,
            file_name=(
                "hikari_notas_triadas.xlsx"
            ),
            mime=(
                "application/"
                "vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

    if not df_combined.empty:

        csv_data = (
            df_combined
            .to_csv(
                index=False
            )
            .encode(
                "utf-8-sig"
            )
        )

        dc3.download_button(
            "⬇️ Baixar CSV Geral",
            data=csv_data,
            file_name=(
                "hikari_notas_triadas.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

    # ═══════════════════════════════════════════════════════════════
    # ITENS DETALHADOS
    # ═══════════════════════════════════════════════════════════════

    detail_rows = []

    for d in export_list:

        uid = d["uid"]

        cat = st.session_state[
            "categories"
        ].get(
            uid,
            "DESPESAS COM MATERIAL DIVERSOS"
        )

        obra = st.session_state[
            "obras"
        ].get(
            uid,
            "CUSTO DA OBRA GERAL"
        )

        codigo = (
            st.session_state[
                "codigos"
            ]
            .get(
                uid,
                ""
            )
            .lstrip("~")
        )

        if not codigo:

            c_res, _ = (
                _resolve_codigo_contabil(
                    cat,
                    obra
                )
            )

            codigo = (
                c_res.lstrip("~")
            )

        tipo_nf = d.get(
            "tipo_nf_classificado",
            "Entrada"
        )

        for item in d.get(
            "itens",
            []
        ):

            detail_rows.append(
                {
                    "Tipo NF": tipo_nf,
                    "NF": d["nNF"],
                    "Fornecedor": d[
                        "fornecedor"
                    ],
                    "Codigo Contabil": codigo,
                    "Obra": obra,
                    "Categoria": cat,
                    "CNO": d.get(
                        "cno_sugerido",
                        ""
                    ),
                    **item,
                }
            )

    if detail_rows:

        df_detail = pd.DataFrame(
            detail_rows
        )

        csv_detail = (
            df_detail
            .to_csv(
                index=False
            )
            .encode(
                "utf-8-sig"
            )
        )

        dc4.download_button(
            "⬇️ Baixar Itens Detalhados (CSV)",
            data=csv_detail,
            file_name=(
                "hikari_itens_detalhados.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════════════
# PAGE — FORNECEDORES & OBRAS
# ═══════════════════════════════════════════════════════════════════

elif page == "Fornecedores & Obras":

    st.markdown(
        "# Tabela de Fornecedores e Obras"
    )

    st.caption(
        "Consulta das tabelas oficiais de "
        "Fornecedores e Plano de Contas com CNO da Hikari."
    )

    tab_f, tab_o = st.tabs(
        [
            "🏢 Fornecedores (Códigos Contábeis)",
            "🏗️ Obras & CNOs (Contas.xlsx)",
        ]
    )

    # ═══════════════════════════════════════════════════════════════
    # FORNECEDORES
    # ═══════════════════════════════════════════════════════════════

    with tab_f:

        df_fornec = (
            fornecedor_db
            .load_fornecedores()
        )

        f_search = st.text_input(
            "🔍 Buscar Fornecedor por Nome:",
            placeholder=(
                "Digite o nome da empresa..."
            ),
        )

        if f_search:

            mask = (
                df_fornec[
                    "nome_fornecedor"
                ]
                .str.contains(
                    f_search,
                    case=False,
                    na=False,
                )
            )

            df_display = (
                df_fornec[mask]
            )

        else:

            df_display = df_fornec

        st.markdown(
            f"**Total cadastrado:** "
            f"{len(df_fornec)} fornecedores | "
            f"**Exibindo:** "
            f"{len(df_display)}"
        )

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            height=450,
        )

    # ═══════════════════════════════════════════════════════════════
    # OBRAS
    # ═══════════════════════════════════════════════════════════════

    with tab_o:

        obras_data = (
            contas_db
            .get_all_obras()
        )

        o_search = st.text_input(
            "🔍 Buscar Obra ou CNO:",
            placeholder=(
                "Digite nome da obra ou CNO..."
            ),
        )

        rows_o = []

        for o in obras_data:

            cno_val = (
                o.get("cno")
                or "—"
            )

            nome_val = (
                o.get("nome_display")
                or o.get("display")
                or ""
            )

            row_dict = {
                "Código Contábil": o.get(
                    "codigo"
                ),
                "Classificação": o.get(
                    "classificacao"
                ),
                "Nome da Obra": nome_val,
                "CNO": cno_val,
                "Categorias Mapeadas": len(
                    o.get(
                        "categorias",
                        {}
                    )
                ),
            }

            if o_search:

                if (
                    o_search.lower()
                    in str(
                        nome_val
                    ).lower()
                    or o_search
                    in str(
                        cno_val
                    )
                ):
                    rows_o.append(
                        row_dict
                    )

            else:

                rows_o.append(
                    row_dict
                )

        df_obras_tab = pd.DataFrame(
            rows_o
        )

        st.markdown(
            f"**Total de Obras:** "
            f"{len(obras_data)} | "
            f"**Exibindo:** "
            f"{len(df_obras_tab)}"
        )

        st.dataframe(
            df_obras_tab,
            use_container_width=True,
            hide_index=True,
            height=350,
        )

        st.markdown("---")

        st.markdown(
            "### 🔎 Detalhamento: "
            "Segmento e suas Subclasses "
            "(Contas Analíticas)"
        )

        st.caption(
            "Selecione um segmento/obra abaixo "
            "para visualizar todas as subclasses "
            "de despesa."
        )

        obra_labels = [
            o["dropdown_label"]
            for o in obras_data
            if o.get(
                "dropdown_label"
            )
        ]

        sel_detalhe = st.selectbox(
            "Selecione a Obra para detalhamento:",
            obra_labels,
            key="sel_obra_detalhe",
        )

        if sel_detalhe:

            subclasses = (
                contas_db
                .get_subclasses_for_obra(
                    sel_detalhe
                )
            )

            o_info = (
                contas_db
                .get_obra_by_identifier(
                    sel_detalhe
                )
            )

            if o_info:

                cno_info = (
                    f" | **CNO:** "
                    f"{o_info['cno']}"
                    if o_info.get("cno")
                    else ""
                )

                st.info(
                    f"🏗️ **Segmento / Obra:** "
                    f"{o_info.get('nome_display')} | "
                    f"**Cód. Conta:** "
                    f"{o_info.get('codigo')} "
                    f"({o_info.get('classificacao')})"
                    f"{cno_info}"
                )

            if subclasses:

                st.markdown(
                    f"**Subclasses / Contas "
                    f"Analíticas Vinculadas "
                    f"({len(subclasses)} contas):**"
                )

                sub_table = []

                for s in subclasses:

                    sub_table.append(
                        {
                            "Código da Subclasse": s.get(
                                "codigo"
                            ),
                            "Classificação": s.get(
                                "classificacao"
                            ),
                            "Nome da Subclasse (Despesa)": s.get(
                                "nome"
                            ),
                        }
                    )

                st.dataframe(
                    pd.DataFrame(
                        sub_table
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            else:

                st.warning(
                    "Nenhuma subclasse vinculada."
                )


# ═══════════════════════════════════════════════════════════════════
# PAGE — PLANO DE CONTAS
# ═══════════════════════════════════════════════════════════════════

elif page == "Plano de Contas":

    st.markdown(
        "# Plano de Contas"
    )

    st.caption(
        "Gerencie as categorias de despesa e "
        "obras/centros de custo. "
        "Adições aqui aparecem nos dropdowns "
        "de triagem e são salvas automaticamente."
    )

    tab_cat, tab_obra = st.tabs(
        [
            "📂 Categorias de Despesa",
            "🏗️ Obras / Centros de Custo",
        ]
    )

    # ═══════════════════════════════════════════════════════════════
    # CATEGORIAS
    # ═══════════════════════════════════════════════════════════════

    with tab_cat:

        st.markdown(
            "### Categorias Base (Plano Hikari)"
        )

        base_cat_rows = []

        for suffix, (
            nome,
            _
        ) in sorted(
            HIKARI_DESPESAS.items()
        ):

            base_cat_rows.append(
                {
                    "Código": suffix,
                    "Descrição": nome,
                    "Tipo": "Base",
                }
            )

        st.dataframe(
            pd.DataFrame(
                base_cat_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")

        st.markdown(
            "### Categorias Extras (Personalizadas)"
        )

        extra_cats = (
            st.session_state[
                "plano_extra_cats"
            ]
        )

        if extra_cats:

            extra_cat_df = pd.DataFrame(
                extra_cats
            )

            st.dataframe(
                extra_cat_df,
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.info(
                "Nenhuma categoria extra adicionada ainda."
            )

        st.markdown(
            "#### Adicionar Nova Categoria"
        )

        with st.form(
            "form_add_cat"
        ):

            nc1, nc2 = st.columns(
                [1, 3]
            )

            novo_cod_cat = (
                nc1.text_input(
                    "Código (ex: 019)",
                    max_chars=10,
                )
            )

            novo_nome_cat = (
                nc2.text_input(
                    "Nome da Categoria "
                    "(ex: DESPESAS COM SEGUROS)"
                )
            )

            submit_cat = (
                st.form_submit_button(
                    "➕ Adicionar Categoria",
                    type="primary",
                )
            )

        if submit_cat:

            if (
                not novo_cod_cat
                or not novo_nome_cat
            ):

                st.error(
                    "Preencha código e nome antes de adicionar."
                )

            else:

                nome_up = (
                    novo_nome_cat
                    .strip()
                    .upper()
                )

                cod_up = (
                    novo_cod_cat
                    .strip()
                )

                existentes = (
                    [
                        c["nome"]
                        for c in extra_cats
                    ]
                    + HIKARI_DESPESAS_LISTA
                )

                if nome_up in existentes:

                    st.warning(
                        f"Categoria '{nome_up}' já existe."
                    )

                else:

                    st.session_state[
                        "plano_extra_cats"
                    ].append(
                        {
                            "codigo": cod_up,
                            "nome": nome_up,
                        }
                    )

                    save_plano_json(
                        {
                            "categorias_extras":
                                st.session_state[
                                    "plano_extra_cats"
                                ],
                            "obras_extras":
                                st.session_state[
                                    "plano_extra_obras"
                                ],
                        }
                    )

                    st.success(
                        f"Categoria '{nome_up}' adicionada e salva!"
                    )

                    st.rerun()

        if extra_cats:

            st.markdown(
                "#### Remover Categoria Extra"
            )

            nomes_extras = [
                c["nome"]
                for c in extra_cats
            ]

            to_remove_cat = (
                st.selectbox(
                    "Selecionar para remover",
                    nomes_extras,
                    key="rm_cat",
                )
            )

            if st.button(
                "🗑️ Remover Categoria Selecionada",
                key="btn_rm_cat",
            ):

                st.session_state[
                    "plano_extra_cats"
                ] = [
                    c
                    for c in extra_cats
                    if c["nome"]
                    != to_remove_cat
                ]

                save_plano_json(
                    {
                        "categorias_extras":
                            st.session_state[
                                "plano_extra_cats"
                            ],
                        "obras_extras":
                            st.session_state[
                                "plano_extra_obras"
                            ],
                    }
                )

                st.success(
                    f"Categoria '{to_remove_cat}' removida."
                )

                st.rerun()

    # ═══════════════════════════════════════════════════════════════
    # OBRAS
    # ═══════════════════════════════════════════════════════════════

    with tab_obra:

        st.markdown(
            "### Obras Base (Plano Hikari)"
        )

        base_obra_rows = []

        for cls, (
            cod,
            nome
        ) in sorted(
            HIKARI_OBRAS.items()
        ):

            base_obra_rows.append(
                {
                    "Classificação": cls,
                    "Código": cod,
                    "Nome": nome,
                    "Tipo": "Base",
                }
            )

        st.dataframe(
            pd.DataFrame(
                base_obra_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")

        st.markdown(
            "### Obras Extras (Personalizadas)"
        )

        extra_obras = (
            st.session_state[
                "plano_extra_obras"
            ]
        )

        if extra_obras:

            st.dataframe(
                pd.DataFrame(
                    extra_obras
                ),
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.info(
                "Nenhuma obra extra adicionada ainda."
            )

        st.markdown(
            "#### Adicionar Nova Obra"
        )

        with st.form(
            "form_add_obra"
        ):

            no1, no2, no3 = st.columns(
                [1, 1, 3]
            )

            nova_cls_obra = (
                no1.text_input(
                    "Classificação "
                    "(ex: 3.1.1.22)",
                    max_chars=12,
                )
            )

            novo_cod_obra = (
                no2.text_input(
                    "Código Numérico "
                    "(ex: 2100)",
                    max_chars=10,
                )
            )

            novo_nome_obra = (
                no3.text_input(
                    "Nome da Obra "
                    "(ex: HOSPITAL REGIONAL PALMAS)"
                )
            )

            submit_obra = (
                st.form_submit_button(
                    "➕ Adicionar Obra",
                    type="primary",
                )
            )

        if submit_obra:

            if not novo_nome_obra:

                st.error(
                    "O nome da obra é obrigatório."
                )

            else:

                nome_up = (
                    novo_nome_obra
                    .strip()
                    .upper()
                )

                existentes = (
                    [
                        o["nome"]
                        for o in extra_obras
                    ]
                    + HIKARI_OBRAS_LISTA
                )

                if nome_up in existentes:

                    st.warning(
                        f"Obra '{nome_up}' já existe."
                    )

                else:

                    st.session_state[
                        "plano_extra_obras"
                    ].append(
                        {
                            "classificacao":
                                nova_cls_obra.strip(),
                            "codigo":
                                novo_cod_obra.strip(),
                            "nome":
                                nome_up,
                        }
                    )

                    save_plano_json(
                        {
                            "categorias_extras":
                                st.session_state[
                                    "plano_extra_cats"
                                ],
                            "obras_extras":
                                st.session_state[
                                    "plano_extra_obras"
                                ],
                        }
                    )

                    st.success(
                        f"Obra '{nome_up}' adicionada e salva!"
                    )

                    st.rerun()

        if extra_obras:

            st.markdown(
                "#### Remover Obra Extra"
            )

            nomes_extras_obra = [
                o["nome"]
                for o in extra_obras
            ]

            to_remove_obra = (
                st.selectbox(
                    "Selecionar para remover",
                    nomes_extras_obra,
                    key="rm_obra",
                )
            )

            if st.button(
                "🗑️ Remover Obra Selecionada",
                key="btn_rm_obra",
            ):

                st.session_state[
                    "plano_extra_obras"
                ] = [
                    o
                    for o in extra_obras
                    if o["nome"]
                    != to_remove_obra
                ]

                save_plano_json(
                    {
                        "categorias_extras":
                            st.session_state[
                                "plano_extra_cats"
                            ],
                        "obras_extras":
                            st.session_state[
                                "plano_extra_obras"
                            ],
                    }
                )

                st.success(
                    f"Obra '{to_remove_obra}' removida."
                )

                st.rerun()

    # ═══════════════════════════════════════════════════════════════
    # INFORMAÇÕES SOBRE FALLBACK
    # ═══════════════════════════════════════════════════════════════

    st.divider()

    st.markdown(
        "#### Mapeamento de Códigos Contábeis (Balancete)"
    )

    st.caption(
        "Para combinações obra+despesa não mapeadas, "
        "o sistema usa o código da Obra Geral como fallback "
        "(exibido em amarelo nos cards)."
    )

    st.info(
        "💡 Os códigos das obras extras ainda não têm "
        "mapeamento automático no balancete. "
        "Use o campo 'Código Numérico' ao adicionar a obra."
    )


# ═══════════════════════════════════════════════════════════════════
# PAGE — LANÇAMENTO MANUAL
# ═══════════════════════════════════════════════════════════════════

elif page == "Lancamento Manual":

    st.markdown(
        "# Lançamento Manual"
    )

    st.caption(
        "Registre aqui lançamentos feitos manualmente "
        "no sistema Domínio. Eles serão incluídos "
        "na exportação Excel para conferência."
    )

    all_cats_lista = (
        get_all_categorias(
            st.session_state[
                "plano_extra_cats"
            ]
        )
    )

    all_obras_lista = (
        get_all_obras(
            st.session_state[
                "plano_extra_obras"
            ]
        )
    )

    # ═══════════════════════════════════════════════════════════════
    # NOVO LANÇAMENTO
    # ═══════════════════════════════════════════════════════════════

    with st.expander(
        "➕ Novo Lançamento Manual",
        expanded=True,
    ):

        with st.form(
            "form_lancamento_manual",
            clear_on_submit=True,
        ):

            r1c1, r1c2, r1c3 = st.columns(3)

            data_lanc = (
                r1c1.date_input(
                    "Data do Documento",
                    value=datetime.date.today()
                )
            )

            vencimento_lanc = (
                r1c2.date_input(
                    "Vencimento",
                    value=datetime.date.today()
                )
            )

            nr_doc = (
                r1c3.text_input(
                    "Nº Documento / NF"
                )
            )

            r2c1, r2c2 = st.columns(
                [2, 1]
            )

            fornecedor_lanc = (
                r2c1.text_input(
                    "Fornecedor / Credor"
                )
            )

            cnpj_lanc = (
                r2c2.text_input(
                    "CNPJ (opcional)",
                    max_chars=18,
                )
            )

            r3c1, r3c2, r3c3 = st.columns(
                3
            )

            valor_lanc = (
                r3c1.number_input(
                    "Valor (R$)",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                )
            )

            forma_pag_lanc = (
                r3c2.selectbox(
                    "Forma Pagamento",
                    [
                        "Boleto",
                        "PIX",
                        "Transferencia",
                        "Cheque",
                        "Dinheiro",
                        "Cartao Credito",
                        "Outros",
                    ],
                )
            )

            cliente_lanc = (
                r3c3.text_input(
                    "Cliente / Tomador (opcional)"
                )
            )

            r4c1, r4c2 = st.columns(
                2
            )

            cat_lanc = (
                r4c1.selectbox(
                    "Categoria de Despesa",
                    all_cats_lista,
                )
            )

            obra_lanc = (
                r4c2.selectbox(
                    "Obra / Centro de Custo (Segmento)",
                    OBRA_OPTIONS,
                )
            )

            codigo_lanc, lanc_info = (
                _resolve_codigo_contabil(
                    cat_lanc,
                    obra_lanc,
                )
            )

            cno_auto = (
                lanc_info.get(
                    "cno"
                )
                or ""
            )

            cno_lanc = st.text_input(
                "CNO",
                value=cno_auto,
                max_chars=20,
            )

            obs_lanc = st.text_area(
                "Observação / Histórico",
                max_chars=300,
                height=80,
            )

            sub_cls = (
                lanc_info.get(
                    "classificacao",
                    ""
                )
            )

            sub_cls_str = (
                f" ({sub_cls})"
                if sub_cls
                else ""
            )

            st.markdown(
                f"""
                <div class="manual-header">
                🏛️ Conta Analítica:
                <strong>
                {codigo_lanc.lstrip("~") or "não mapeado"}
                </strong>
                {sub_cls_str}
                — {cat_lanc}
                """
                + (
                    ' &nbsp;<small>'
                    '(⚠️ fallback Obra Geral)'
                    '</small>'
                    if codigo_lanc.startswith("~")
                    else ""
                )
                + """
                </div>
                """,
                unsafe_allow_html=True,
            )

            submit_lanc = (
                st.form_submit_button(
                    "💾 Salvar Lançamento",
                    type="primary",
                    use_container_width=True,
                )
            )

        if submit_lanc:

            if (
                not fornecedor_lanc
                or valor_lanc <= 0
            ):

                st.error(
                    "Fornecedor e Valor são obrigatórios."
                )

            else:

                novo_lanc = {
                    "id":
                        len(
                            st.session_state[
                                "lancamentos_manuais"
                            ]
                        ) + 1,

                    "data":
                        str(data_lanc),

                    "vencimento":
                        str(vencimento_lanc),

                    "nr_documento":
                        nr_doc,

                    "fornecedor":
                        fornecedor_lanc
                        .strip()
                        .upper(),

                    "cnpj":
                        cnpj_lanc,

                    "valor":
                        valor_lanc,

                    "forma_pagamento":
                        forma_pag_lanc,

                    "cliente":
                        cliente_lanc,

                    "categoria":
                        cat_lanc,

                    "obra":
                        obra_lanc,

                    "cno":
                        cno_lanc,

                    "codigo_contabil":
                        codigo_lanc,

                    "observacao":
                        obs_lanc,
                }

                st.session_state[
                    "lancamentos_manuais"
                ].append(
                    novo_lanc
                )

                st.success(
                    f"✅ Lançamento de "
                    f"{_fmt_brl(valor_lanc)} "
                    f"({fornecedor_lanc}) salvo!"
                )

                st.rerun()

    # ═══════════════════════════════════════════════════════════════
    # LISTAGEM
    # ═══════════════════════════════════════════════════════════════

    lancamentos = (
        st.session_state[
            "lancamentos_manuais"
        ]
    )

    st.divider()

    st.markdown(
        f"### Lançamentos Registrados "
        f"({len(lancamentos)})"
    )

    if not lancamentos:

        st.info(
            "Nenhum lançamento manual registrado ainda."
        )

    else:

        total_manual = sum(
            float(
                m.get(
                    "valor",
                    0
                )
                or 0
            )
            for m in lancamentos
        )

        lm1, lm2, lm3 = st.columns(3)

        lm1.metric(
            "Total de Lançamentos",
            len(lancamentos)
        )

        lm2.metric(
            "Valor Total",
            _fmt_brl(
                total_manual
            )
        )

        obras_man = len(
            set(
                m.get(
                    "obra",
                    ""
                )
                for m in lancamentos
            )
        )

        lm3.metric(
            "Obras Envolvidas",
            obras_man
        )

        st.markdown("---")

        for i, m in enumerate(
            lancamentos
        ):

            codigo_m = (
                m.get(
                    "codigo_contabil",
                    ""
                )
                .lstrip("~")
            )

            with st.container(
                border=True
            ):

                mc1, mc2, mc3 = st.columns(
                    [4, 2, 1]
                )

                with mc1:

                    st.markdown(
                        f"**#{m['id']} — "
                        f"{m['fornecedor']}**  \n"
                        f"📅 Doc: {m['data']} | "
                        f"Venc: {m['vencimento']} | "
                        f"NF/Doc: "
                        f"{m.get('nr_documento', '—')}"
                    )

                    st.caption(
                        f"🏗️ {m['obra']} | "
                        f"📂 {m['categoria']} | "
                        f"💳 {m['forma_pagamento']}"
                        + (
                            f" | CNO: {m['cno']}"
                            if m.get("cno")
                            else ""
                        )
                    )

                with mc2:

                    st.metric(
                        "Valor",
                        _fmt_brl(
                            m.get(
                                "valor",
                                0
                            )
                        ),
                    )

                    if codigo_m:

                        st.caption(
                            f"Cod. Contábil: "
                            f"**{codigo_m}**"
                        )

                with mc3:

                    if st.button(
                        "🗑️",
                        key=(
                            f"del_lanc_{i}"
                        ),
                        help=(
                            "Excluir este lançamento"
                        ),
                    ):

                        st.session_state[
                            "lancamentos_manuais"
                        ].pop(i)

                        st.rerun()

                if m.get(
                    "observacao"
                ):

                    st.caption(
                        f"📝 "
                        f"{m['observacao']}"
                    )

        st.divider()

        if lancamentos:

            df_lanc = pd.DataFrame(
                lancamentos
            )

            csv_lanc = (
                df_lanc
                .to_csv(
                    index=False
                )
                .encode(
                    "utf-8-sig"
                )
            )

            st.download_button(
                "⬇️ Exportar Lançamentos Manuais (CSV)",
                data=csv_lanc,
                file_name=(
                    "hikari_lancamentos_manuais.csv"
                ),
                mime="text/csv",
                use_container_width=True,
            )

        if st.button(
            "🗑️ Limpar Todos os Lançamentos",
            type="secondary",
        ):

            st.session_state[
                "lancamentos_manuais"
            ] = []

            st.rerun()
