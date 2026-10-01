"""
app.py — Catraca Fiscal v2
Streamlit dashboard for NF-e XML triage.
Hikari expense codes + obra centers from balancete.
Google Gemini AI integration for intelligent categorization.

Novidades v2:
 - Identificação de Notas de Retorno/Devolução (badge laranja)
 - Filtro por Tipo NF (Entrada / Saída / Retorno)
 - Aba "Plano de Contas" — gerenciamento dinâmico de categorias e obras
 - Aba "Lançamento Manual" — registro de lançamentos para conferência Domínio
 - Correção de bugs: paginação, texto IA, código contábil fallback
"""
import streamlit as st
import zipfile
import pandas as pd
import datetime
from xml_processor import parse_nfe
from categorizer import (
    categorize_invoice, suggest_project,
    HIKARI_DESPESAS_LISTA, HIKARI_OBRAS_LISTA,
    get_codigo_contabil, get_all_categorias, get_all_obras,
    load_plano_json, save_plano_json,
    HIKARI_DESPESAS, HIKARI_OBRAS, CODIGO_POR_OBRA,
)
from exporter import export_to_excel
from ai_classifier import classify_batch, is_available as ai_available
import fornecedor_db
import contas_db
from dominio_exporter import export_to_dominio_excel


# ─── Helpers ────────────────────────────────────────────────────────────────

def _matches_filters(doc, f_status, f_cat, f_obra, f_tipo, state):
    uid    = doc["uid"]
    status = state["approvals"].get(uid, "Pendente")
    cat    = state["categories"].get(uid, "DESPESAS COM MATERIAL DIVERSOS")
    obra   = state["obras"].get(uid, "CUSTO DA OBRA GERAL")
    tipo   = doc.get("tipo_nf_classificado", "Entrada")

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
        return f"R$ {float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


# ═══════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Catraca Fiscal v2 — Triagem NF-e Hikari",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }

.cno-tag {
    background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
    border-left: 4px solid #2e7d32; padding: 10px 14px;
    border-radius: 6px; margin: 8px 0; font-size: 13px; font-weight: 500;
}
.alert-missing {
    background: #fff3cd; border-left: 4px solid #ffc107;
    padding: 10px 14px; border-radius: 6px; margin: 8px 0; font-size: 13px;
}
.ai-tag {
    background: linear-gradient(135deg, #e3f2fd, #bbdefb);
    border-left: 4px solid #1565c0; padding: 10px 14px;
    border-radius: 6px; margin: 8px 0; font-size: 13px;
}
.badge { display: inline-block; padding: 4px 12px; border-radius: 12px;
         font-size: 12px; font-weight: 600; letter-spacing: 0.3px; }
.badge-pending  { background: #FFF3CD; color: #856404; }
.badge-approved { background: #D4EDDA; color: #155724; }
.badge-rejected { background: #F8D7DA; color: #721C24; }
.badge-retorno  { background: #FFE0B2; color: #BF360C; }
.badge-entrada  { background: #E8F5E9; color: #1B5E20; }
.badge-saida    { background: #FBE9E7; color: #BF360C; }
.obras-gerais-tag {
    background: #f8d7da; border-left: 4px solid #dc3545;
    padding: 10px 14px; border-radius: 6px; margin: 8px 0; font-size: 13px;
    font-weight: 500;
}
.retorno-tag {
    background: linear-gradient(135deg, #FFF3E0, #FFE0B2);
    border-left: 4px solid #E65100; padding: 10px 14px;
    border-radius: 6px; margin: 8px 0; font-size: 13px; font-weight: 600;
}
.codigo-tag {
    background: linear-gradient(135deg, #ede7f6, #d1c4e9);
    border-left: 4px solid #5e35b1; padding: 10px 14px;
    border-radius: 6px; margin: 8px 0; font-size: 14px; font-weight: 600;
    font-family: 'Courier New', monospace; letter-spacing: 0.5px;
}
.codigo-tag .code-value {
    background: #5e35b1; color: white; padding: 2px 10px;
    border-radius: 4px; font-size: 15px;
}
.codigo-fallback-tag {
    background: linear-gradient(135deg, #fff8e1, #fff3cd);
    border-left: 4px solid #f9a825; padding: 10px 14px;
    border-radius: 6px; margin: 8px 0; font-size: 14px; font-weight: 600;
    font-family: 'Courier New', monospace; letter-spacing: 0.5px;
}
.codigo-fallback-tag .code-value {
    background: #f9a825; color: #333; padding: 2px 10px;
    border-radius: 4px; font-size: 15px;
}
.manual-header {
    background: linear-gradient(135deg, #e8eaf6, #c5cae9);
    border-left: 4px solid #3949ab; padding: 12px 16px;
    border-radius: 8px; margin: 10px 0; font-size: 14px; font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════════
_plano_json = load_plano_json()

for key, default in [
    ("processed_data",      []),
    ("approvals",           {}),
    ("categories",          {}),
    ("obras",               {}),
    ("codigos",             {}),
    ("codigos_info",        {}),
    ("fornecedores_map",    {}),
    ("ai_reasons",          {}),
    ("deepseek_key",        ""),
    ("ai_classified",       False),
    ("plano_extra_cats",    _plano_json.get("categorias_extras", [])),
    ("plano_extra_obras",   _plano_json.get("obras_extras", [])),
    ("lancamentos_manuais", []),
    ("filter_status",       "Todos"),
    ("filter_cat",          "Todas"),
    ("filter_obra",         "Todas"),
    ("filter_tipo",         "Todos"),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def _resolve_codigo_contabil(categoria: str, obra: str) -> tuple:
    """
    Resolve o código e detalhes da subclasse (conta analítica de despesa)
    dentro do segmento (obra com CNO). Retorna (codigo_str, info_dict).
    """
    info = contas_db.get_codigo_info_para_obra_e_categoria(obra, categoria)
    cod = info.get("codigo")
    if cod:
        prefix = "~" if info.get("is_fallback") else ""
        return f"{prefix}{cod}", info
    legacy_code = get_codigo_contabil(categoria, obra, st.session_state.get("plano_extra_cats"))
    return legacy_code, info


# Listas dinamicas (base + extras)
CATEGORY_OPTIONS = get_all_categorias(st.session_state["plano_extra_cats"]) + ["OUTRA (digitar)"]
# Obras reais do Contas.xlsx com Nome, Código, Classificação e CNO
contas_obras_list = contas_db.get_obra_names_for_dropdown()
base_obras = get_all_obras(st.session_state["plano_extra_obras"])
# Unifica obras do plano oficial com eventuais custom
OBRA_OPTIONS = list(contas_obras_list)
for bo in base_obras:
    if bo not in OBRA_OPTIONS and bo != "CUSTO DA OBRA GERAL":
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
        ["Triagem", "Exportacao", "Fornecedores & Obras", "Plano de Contas", "Lancamento Manual"],
        label_visibility="collapsed",
    )

    st.divider()

    # ── Upload ──
    st.markdown("#### Upload de XMLs")
    uploaded_file = st.file_uploader("Arquivo ZIP", type="zip", label_visibility="collapsed")

    if uploaded_file:
        with zipfile.ZipFile(uploaded_file, "r") as z:
            xml_files = [f for f in z.namelist() if f.lower().endswith(".xml")]
            st.info(f"{len(xml_files)} arquivos XML encontrados")

            if st.button("Processar Lote", use_container_width=True, type="primary"):
                st.session_state["processed_data"] = []
                st.session_state["approvals"]      = {}
                st.session_state["categories"]     = {}
                st.session_state["obras"]          = {}
                st.session_state["codigos"]        = {}
                st.session_state["fornecedores_map"] = {}
                st.session_state["ai_reasons"]     = {}
                st.session_state["ai_classified"]  = False

                progress = st.progress(0, text="Processando...")
                errors   = []

                for i, xml_file in enumerate(xml_files):
                    with z.open(xml_file) as f:
                        data_rows = parse_nfe(f.read())

                    if data_rows and "error" in data_rows[0]:
                        errors.append(f"{xml_file}: {data_rows[0]['error']}")
                        continue
                    elif not data_rows:
                        continue

                    # Agrupa data_rows por CFOP para desmembrar a nota se houver múltiplos CFOPs
                    cfop_groups = {}
                    for row in data_rows:
                        cfop_k = row.get("cfop_destaque") or ""
                        if cfop_k not in cfop_groups:
                            cfop_groups[cfop_k] = []
                        cfop_groups[cfop_k].append(row)

                    for cfop_sub_idx, (cfop_val, rows_for_cfop) in enumerate(cfop_groups.items()):
                        base_data = rows_for_cfop[0].copy()

                        parcelas = []
                        for row in rows_for_cfop:
                            parcelas.append({
                                "nDup":  row.get("parcela_numero", "1"),
                                "dVenc": row.get("parcela_vencimento", base_data.get("data_emissao")),
                                "vDup":  row.get("parcela_valor", base_data.get("valor_total")),
                            })
                        base_data["parcelas"] = parcelas

                        # 1. Lookup Fornecedor por Nome Emitente (da planilha fornecedores)
                        fornec_match = fornecedor_db.lookup_fornecedor_por_nome(base_data.get("fornecedor", ""))
                        base_data["fornecedor_contabil"] = fornec_match

                        # 2. Categorizacao de despesas
                        items_text = [item["descricao"] for item in base_data.get("itens", [])]
                        cat, cat_reason = categorize_invoice(
                            items_text, base_data.get("infAdic"), base_data.get("cno_sugerido")
                        )

                        # 3. Sugestao de Obra via CNO em Contas.xlsx
                        cno_xml = base_data.get("cno_sugerido")
                        obra_sugerida = "CUSTO DA OBRA GERAL — Cód. 271 (3.1.1.01)"
                        proj_reason = "Obra Geral padrão"

                        if cno_xml:
                            obra_contas = contas_db.lookup_obra_por_cno(cno_xml)
                            if obra_contas:
                                obra_sugerida = obra_contas.get("dropdown_label") or obra_contas["nome_display"]
                                proj_reason = f"Identificado via CNO {cno_xml} ({obra_contas['nome_display']})"

                        if "CUSTO DA OBRA GERAL" in obra_sugerida:
                            p_legacy, r_legacy = suggest_project(base_data.get("infAdic"), cno_xml)
                            if p_legacy != "CUSTO DA OBRA GERAL":
                                o_legacy = contas_db.get_obra_by_identifier(p_legacy)
                                obra_sugerida = o_legacy.get("dropdown_label") if o_legacy else p_legacy
                                proj_reason = r_legacy

                        base_data["categoria"]    = cat
                        base_data["obra_sugerida"] = obra_sugerida
                        base_data["filename"]     = xml_file
                        # Se houver múltiplos CFOPs, diferencia no UID e no nNF
                        if len(cfop_groups) > 1:
                            base_data["uid"] = f"{base_data['nNF']}_{cfop_val}_{i}_{cfop_sub_idx}"
                            base_data["cfop_info"] = f"CFOP {cfop_val}"
                        else:
                            base_data["uid"] = f"{base_data['nNF']}_{i}"
                            base_data["cfop_info"] = f"CFOP {cfop_val}" if cfop_val else ""

                        # 4. Codigo contabil especifico da subclasse para a combinacao obra + despesa
                        codigo, cod_info = _resolve_codigo_contabil(cat, obra_sugerida)

                        st.session_state["processed_data"].append(base_data)
                        st.session_state["approvals"][base_data["uid"]]   = "Pendente"
                        st.session_state["categories"][base_data["uid"]]  = cat
                        st.session_state["obras"][base_data["uid"]]       = obra_sugerida
                        st.session_state["codigos"][base_data["uid"]]     = codigo
                        st.session_state["codigos_info"][base_data["uid"]] = cod_info
                        st.session_state["fornecedores_map"][base_data["uid"]] = fornec_match or {}
                        st.session_state["ai_reasons"][base_data["uid"]]  = f"{cat_reason} | {proj_reason}"

                    progress.progress(
                        (i + 1) / len(xml_files),
                        text=f"Processando {i+1}/{len(xml_files)}...",
                    )

                progress.empty()
                st.success(f"{len(st.session_state['processed_data'])} notas processadas!")
                if errors:
                    for err in errors:
                        st.warning(err)
                st.rerun()

    # ── Gemini AI ──
    st.divider()
    st.markdown("#### Classificacao com IA")
    if ai_available():
        api_key = st.text_input(
            "Chave API Google Gemini",
            type="password",
            value=st.session_state.get("gemini_key", ""),
            help="Insira sua chave da API Google Gemini",
        )
        if api_key:
            st.session_state["gemini_key"] = api_key

        if st.session_state["processed_data"] and api_key:
            if st.button("Classificar com Google Gemini AI", use_container_width=True, type="primary"):
                with st.spinner("Enviando para Google Gemini AI..."):
                    result = classify_batch(st.session_state["processed_data"], api_key)
                if result and "_error" not in result:
                    for doc in st.session_state["processed_data"]:
                        uid = doc["uid"]
                        nf  = doc["nNF"]
                        if nf in result:
                            r    = result[nf]
                            cat  = r.get("categoria", "DESPESAS COM MATERIAL DIVERSOS")
                            st.session_state["categories"][uid] = cat
                            obra = r.get("obra_sugerida", "CUSTO DA OBRA GERAL")
                            o_match = contas_db.get_obra_by_identifier(obra)
                            obra_label = o_match["dropdown_label"] if o_match else obra
                            st.session_state["obras"][uid]      = obra_label
                            cod, cod_info = _resolve_codigo_contabil(cat, obra_label)
                            st.session_state["codigos"][uid]    = cod
                            st.session_state["codigos_info"][uid] = cod_info
                            reason = r.get("motivo_categoria", "")
                            if reason:
                                st.session_state["ai_reasons"][uid] = f"IA Gemini: {reason}"
                    st.session_state["ai_classified"] = True
                    st.success("Classificacao com Google Gemini AI concluida!")
                    st.rerun()
                elif result and "_error" in result:
                    st.error(f"Erro da API: {result['_error']}")
                else:
                    st.error("Falha na classificacao. Verifique a chave API.")
        elif st.session_state["processed_data"] and not api_key:
            st.caption("Insira a chave API para ativar a IA")
    else:
        st.warning("Instale: pip install google-generativeai")
        st.code("pip install google-generativeai", language="bash")

    # ── Progress ──
    if st.session_state["processed_data"]:
        st.divider()
        st.markdown("#### Progresso")
        total    = len(st.session_state["processed_data"])
        approved = list(st.session_state["approvals"].values()).count("Aprovado")
        rejected = list(st.session_state["approvals"].values()).count("Rejeitado")
        pending  = total - approved - rejected

        pct = (approved + rejected) / total if total > 0 else 0
        st.progress(pct, text=f"{approved + rejected}/{total} triados ({pct:.0%})")

        c1, c2, c3 = st.columns(3)
        c1.metric("Aprovados",  approved)
        c2.metric("Rejeitados", rejected)
        c3.metric("Pendentes",  pending)

        # Resumo por tipo NF
        tipos = {}
        for d in st.session_state["processed_data"]:
            t = d.get("tipo_nf_classificado", "Entrada")
            tipos[t] = tipos.get(t, 0) + 1
        if tipos:
            st.divider()
            st.markdown("#### Por Tipo NF")
            for t, cnt in sorted(tipos.items()):
                icon = "🔄" if "Retorno" in t else ("📥" if t == "Entrada" else "📤")
                st.caption(f"{icon} **{t}** — {cnt}")

        st.divider()
        st.markdown("#### Por Obra")
        obras_dict = {}
        for d in st.session_state["processed_data"]:
            obra = st.session_state["obras"].get(d["uid"], "CUSTO DA OBRA GERAL")
            if obra not in obras_dict:
                obras_dict[obra] = {"count": 0, "total": 0.0}
            obras_dict[obra]["count"] += 1
            obras_dict[obra]["total"] += d.get("valor_total", 0)

        for obra, info in obras_dict.items():
            st.caption(f"**{obra}** — {info['count']} NFs — {_fmt_brl(info['total'])}")


# ═══════════════════════════════════════════════════════════════════
# PAGE 1: TRIAGEM
# ═══════════════════════════════════════════════════════════════════
if page == "Triagem":
    st.markdown("# Triagem de Notas Fiscais")
    st.caption("Revise, classifique com os codigos Hikari, e aprove ou rejeite cada nota.")

    if not st.session_state["processed_data"]:
        st.info("Faca o upload de um arquivo ZIP com XMLs na barra lateral.")
        st.stop()

    if st.session_state.get("ai_classified"):
        st.markdown(
            '<div class="ai-tag"><strong>Classificacao com Google Gemini AI ativa</strong> '
            '— categorias e obras sugeridas pela IA. Revise e ajuste.</div>',
            unsafe_allow_html=True,
        )

    # ── Filtros ──
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        filter_status = st.selectbox(
            "Filtrar Status", ["Todos", "Pendente", "Aprovado", "Rejeitado"],
            key="flt_status",
        )
    with f2:
        all_cats = sorted(set(st.session_state["categories"].values()))
        filter_cat = st.selectbox("Filtrar Categoria", ["Todas"] + all_cats, key="flt_cat")
    with f3:
        all_obras = sorted(set(st.session_state["obras"].values()))
        filter_obra = st.selectbox("Filtrar Obra", ["Todas"] + all_obras, key="flt_obra")
    with f4:
        filter_tipo = st.selectbox(
            "Filtrar Tipo NF",
            ["Todos", "Entrada", "Saída", "Retorno/Devolução"],
            key="flt_tipo",
        )

    # ── Ações em Lote ──
    b1, b2, b3 = st.columns([1, 1, 4])
    if b1.button("Aprovar Todos Visiveis", use_container_width=True):
        for d in st.session_state["processed_data"]:
            if _matches_filters(d, filter_status, filter_cat, filter_obra, filter_tipo, st.session_state):
                st.session_state["approvals"][d["uid"]] = "Aprovado"
        st.rerun()
    if b2.button("Rejeitar Todos Visiveis", use_container_width=True):
        for d in st.session_state["processed_data"]:
            if _matches_filters(d, filter_status, filter_cat, filter_obra, filter_tipo, st.session_state):
                st.session_state["approvals"][d["uid"]] = "Rejeitado"
        st.rerun()

    st.divider()

    # ── Paginação ──
    visible_docs = [
        d for d in st.session_state["processed_data"]
        if _matches_filters(d, filter_status, filter_cat, filter_obra, filter_tipo, st.session_state)
    ]

    items_per_page = 10
    total_pages    = max(1, (len(visible_docs) - 1) // items_per_page + 1) if visible_docs else 1

    if total_pages > 1:
        pag_col1, pag_col2 = st.columns([1, 4])
        with pag_col1:
            # Clamp page_num dentro do range válido ao mudar filtros
            page_num = st.number_input(
                "Pagina", min_value=1, max_value=total_pages, step=1, value=1,
                key=f"pgn_{filter_status}_{filter_cat}_{filter_obra}_{filter_tipo}",
            )
        with pag_col2:
            st.write(f"Exibindo {len(visible_docs)} notas no total ({total_pages} paginas)")
    else:
        page_num = 1
        st.write(f"Exibindo {len(visible_docs)} notas")

    start_idx = (page_num - 1) * items_per_page
    end_idx   = start_idx + items_per_page

    st.divider()

    # ── Cards de Notas ──
    for idx, doc in enumerate(visible_docs[start_idx:end_idx]):
        uid      = doc["uid"]
        status   = st.session_state["approvals"].get(uid, "Pendente")
        cat      = st.session_state["categories"].get(uid, "DESPESAS COM MATERIAL DIVERSOS")
        obra     = st.session_state["obras"].get(uid, "CUSTO DA OBRA GERAL")
        ai_reason = st.session_state["ai_reasons"].get(uid, "")
        tipo_nf  = doc.get("tipo_nf_classificado", "Entrada")

        badge_cls = {
            "Pendente":  "badge-pending",
            "Aprovado":  "badge-approved",
            "Rejeitado": "badge-rejected",
        }
        badge_html = (
            f'<span class="badge {badge_cls.get(status, "badge-pending")}">'
            f'{status}</span>'
        )

        # Badge de tipo NF
        tipo_badge_map = {
            "Entrada":          ("badge-entrada", "📥 Entrada"),
            "Saída":            ("badge-saida",   "📤 Saída"),
            "Retorno/Devolução": ("badge-retorno", "🔄 Retorno/Devolução"),
        }
        tipo_cls, tipo_label = tipo_badge_map.get(tipo_nf, ("badge-entrada", tipo_nf))
        tipo_badge_html = f'<span class="badge {tipo_cls}">{tipo_label}</span>'

        with st.container(border=True):
            # ── Header ──
            h1, h2, h3 = st.columns([5, 2, 1])
            with h1:
                fornec_info = st.session_state.get("fornecedores_map", {}).get(uid, {})
                cod_f_badge = ""
                if fornec_info and fornec_info.get("codigo_contabil"):
                    cod_f_badge = (
                        f'&nbsp;<span style="background:#004d40; color:#a7ffeb; padding:2px 8px; '
                        f'border-radius:4px; font-weight:600; font-size:12px;">'
                        f'🏢 Cód. Fornecedor: {fornec_info["codigo_contabil"]}</span>'
                    )
                else:
                    cod_f_badge = (
                        f'&nbsp;<span style="background:#5d4037; color:#ffccbc; padding:2px 8px; '
                        f'border-radius:4px; font-weight:500; font-size:12px;">'
                        f'🏢 Cód. Fornecedor: 5 (Diversos)</span>'
                    )

                cfop_badge = ""
                if doc.get("cfop_destaque"):
                    cfop_badge = (
                        f'&nbsp;<span style="background:#1a237e; color:#c5cae9; padding:2px 8px; '
                        f'border-radius:4px; font-weight:600; font-size:12px;">'
                        f'📑 CFOP {doc["cfop_destaque"]}</span>'
                    )

                st.markdown(
                    f"**NF {doc['nNF']}** — {doc['fornecedor']} "
                    f"&nbsp;{tipo_badge_html}{cod_f_badge}{cfop_badge}",
                    unsafe_allow_html=True,
                )
                desc_info = f" | Desc: {_fmt_brl(doc.get('valor_desconto', 0))}" if doc.get('valor_desconto', 0) > 0 else ""
                st.caption(
                    f"CNPJ: {doc.get('fornecedor_cnpj', 'N/A')} | "
                    f"{doc.get('fornecedor_cidade', '')}/{doc.get('fornecedor_uf', '')} | "
                    f"{doc.get('natureza_op', '')}{desc_info}"
                )
            with h2:
                st.metric("Valor Total Líquido", _fmt_brl(doc.get("valor_total", 0)))
            with h3:
                st.markdown(badge_html, unsafe_allow_html=True)

            # ── Tag de Retorno/Devolução ──
            if tipo_nf == "Retorno/Devolução":
                cfops_str = ", ".join(doc.get("cfops_nota", [])) or "—"
                st.markdown(
                    f'<div class="retorno-tag">⚠️ <strong>NOTA DE RETORNO / DEVOLUÇÃO</strong>'
                    f' — CFOPs: {cfops_str}. Esta nota representa uma devolução e deve ser '
                    f'tratada como estorno no lançamento contábil.</div>',
                    unsafe_allow_html=True,
                )

            # ── Detalhes + Categoria ──
            d1, d2 = st.columns(2)
            with d1:
                st.markdown(
                    f"**Emissao:** {doc['data_emissao']} | "
                    f"**Pagamento Base:** {doc.get('pagamento', 'N/A')} | "
                    f"**Itens NF:** {doc.get('qtd_itens', 0)} | "
                    f"**Parcelas:** {doc.get('qtd_parcelas', 1)}"
                )
                st.markdown(f"**Cliente:** {doc['cliente']}")
            with d2:
                # Category selector: dropdown + custom text
                opts = list(CATEGORY_OPTIONS)
                if cat not in opts and cat != "OUTRA (digitar)":
                    opts.insert(0, cat)
                cat_idx = opts.index(cat) if cat in opts else len(opts) - 1

                selected_cat = st.selectbox(
                    "Categoria de Despesa",
                    opts,
                    index=cat_idx,
                    key=f"cat_{uid}",
                    help=ai_reason if ai_reason else None,
                )

                if selected_cat == "OUTRA (digitar)":
                    custom_cat = st.text_input(
                        "Digite a categoria",
                        value="" if cat == "OUTRA (digitar)" else cat,
                        key=f"custom_cat_{uid}",
                    )
                    if custom_cat:
                        st.session_state["categories"][uid] = custom_cat.upper()
                        cod, cod_info = _resolve_codigo_contabil(custom_cat.upper(), st.session_state["obras"].get(uid, "CUSTO DA OBRA GERAL"))
                        st.session_state["codigos"][uid] = cod
                        st.session_state["codigos_info"][uid] = cod_info
                elif selected_cat != cat:
                    st.session_state["categories"][uid] = selected_cat
                    cod, cod_info = _resolve_codigo_contabil(selected_cat, st.session_state["obras"].get(uid, "CUSTO DA OBRA GERAL"))
                    st.session_state["codigos"][uid] = cod
                    st.session_state["codigos_info"][uid] = cod_info

            # ── Obra / Centro de Custo (Segmento) ──
            obra_opts = list(OBRA_OPTIONS)
            if obra not in obra_opts and obra != "OUTRA (digitar)":
                obra_opts.insert(0, obra)
            obra_idx = obra_opts.index(obra) if obra in obra_opts else len(obra_opts) - 1

            selected_obra = st.selectbox(
                "Obra / Centro de Custo (Segmento com CNO)",
                obra_opts,
                index=obra_idx,
                key=f"obra_{uid}",
            )

            if selected_obra == "OUTRA (digitar)":
                custom_obra = st.text_input(
                    "Digite o nome da obra",
                    value="" if obra == "OUTRA (digitar)" else obra,
                    key=f"custom_obra_{uid}",
                )
                if custom_obra:
                    st.session_state["obras"][uid] = custom_obra.upper()
                    cod, cod_info = _resolve_codigo_contabil(st.session_state["categories"].get(uid, "DESPESAS COM MATERIAL DIVERSOS"), custom_obra.upper())
                    st.session_state["codigos"][uid] = cod
                    st.session_state["codigos_info"][uid] = cod_info
            elif selected_obra != obra:
                st.session_state["obras"][uid] = selected_obra
                cod, cod_info = _resolve_codigo_contabil(st.session_state["categories"].get(uid, "DESPESAS COM MATERIAL DIVERSOS"), selected_obra)
                st.session_state["codigos"][uid] = cod
                st.session_state["codigos_info"][uid] = cod_info

            # ── Obtenção dos dados contábeis (Segmento e Subclasse) ──
            curr_cat  = st.session_state["categories"].get(uid, "DESPESAS COM MATERIAL DIVERSOS")
            curr_obra = st.session_state["obras"].get(uid, "CUSTO DA OBRA GERAL")

            codigo = st.session_state["codigos"].get(uid, "")
            cod_info = st.session_state.get("codigos_info", {}).get(uid)
            if not codigo or not cod_info:
                codigo, cod_info = _resolve_codigo_contabil(curr_cat, curr_obra)
                st.session_state["codigos"][uid] = codigo
                st.session_state["codigos_info"][uid] = cod_info

            is_fallback = codigo.startswith("~") or cod_info.get("is_fallback", False)
            codigo_display = codigo.lstrip("~") if codigo else ""

            # Objeto de obra do segmento
            obra_obj = contas_db.get_obra_by_identifier(curr_obra)
            obra_nome_disp = obra_obj.get("nome_display", curr_obra) if obra_obj else curr_obra
            obra_cod_disp = obra_obj.get("codigo", 271) if obra_obj else 271
            obra_cls_disp = obra_obj.get("classificacao", "3.1.1.01") if obra_obj else "3.1.1.01"
            obra_cno_disp = obra_obj.get("cno") if obra_obj else doc.get("cno_sugerido")

            # ── 1. SEGMENTO / OBRA (Nome e Número + CNO) ──
            if obra_cno_disp:
                st.markdown(
                    f'<div class="cno-tag">🏗️ <strong>Segmento / Obra:</strong> {obra_nome_disp} &nbsp;|&nbsp; '
                    f'<strong>Cód. Conta:</strong> <span class="code-value" style="background:#2e7d32; color:white; padding:1px 6px; border-radius:3px;">{obra_cod_disp}</span> ({obra_cls_disp}) &nbsp;|&nbsp; '
                    f'<strong>CNO:</strong> {obra_cno_disp}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="obras-gerais-tag">🏗️ <strong>Segmento:</strong> CUSTO DA OBRA GERAL &nbsp;|&nbsp; '
                    f'<strong>Cód. Conta:</strong> <span class="code-value" style="background:#dc3545; color:white; padding:1px 6px; border-radius:3px;">{obra_cod_disp}</span> ({obra_cls_disp}) &nbsp;|&nbsp; '
                    f'<small>Classificada como Obra Geral (sem CNO específico)</small></div>',
                    unsafe_allow_html=True,
                )

            # ── 2. SUBCLASSE / CONTA ANALÍTICA (Abaixo: Nome e Número aparecendo) ──
            subclasse_classif = cod_info.get("classificacao", "")
            classif_str = f" ({subclasse_classif})" if subclasse_classif else ""

            if is_fallback:
                st.markdown(
                    f'<div class="codigo-fallback-tag">⚠️ <strong>Subclasse / Conta Analítica (Fallback Obra Geral):</strong> '
                    f'<span class="code-value">{codigo_display}</span>{classif_str} — {curr_cat}'
                    f'&nbsp;<small>— Subclasse não mapeada nesta obra específica, usando conta da Obra Geral</small></div>',
                    unsafe_allow_html=True,
                )
            elif codigo_display:
                st.markdown(
                    f'<div class="codigo-tag">🏛️ <strong>Subclasse / Conta Analítica:</strong> '
                    f'<span class="code-value">{codigo_display}</span>{classif_str} — {curr_cat}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="alert-missing">⚠️ <strong>Subclasse:</strong> {curr_cat} — Conta contábil não mapeada para esta combinação.</div>',
                    unsafe_allow_html=True,
                )

            # ── Info Adicional ──
            if doc.get("infAdic"):
                with st.expander("Informacoes Adicionais", expanded=False):
                    st.text(doc["infAdic"])

            # ── Parcelas ──
            parcelas = doc.get("parcelas", [])
            if not parcelas:
                parcelas = [{"nDup": "1", "dVenc": doc.get("data_emissao"), "vDup": doc.get("valor_total")}]
            with st.expander(f"Parcelas ({len(parcelas)})", expanded=True):
                parcela_rows = []
                for p in parcelas:
                    parcela_rows.append({
                        "Parcela":     p.get("nDup", "1"),
                        "Vencimento":  p.get("dVenc", doc.get("data_emissao")),
                        "Valor (R$)":  _fmt_brl(float(p.get("vDup") or doc.get("valor_total") or 0)),
                    })
                st.dataframe(pd.DataFrame(parcela_rows), use_container_width=True, hide_index=True)

            # ── Itens ──
            with st.expander(
                f"Itens da Nota ({doc.get('qtd_itens', 0)} produtos)", expanded=True
            ):
                if doc["itens"]:
                    df_items = pd.DataFrame(doc["itens"])
                    cols = [
                        c for c in [
                            "codigo", "descricao", "ncm", "cfop",
                            "qtd", "unidade", "valor_unit", "valor_total",
                        ]
                        if c in df_items.columns
                    ]
                    names = {
                        "codigo": "Codigo", "descricao": "Descricao", "ncm": "NCM",
                        "cfop": "CFOP", "qtd": "Qtd", "unidade": "Un",
                        "valor_unit": "Vl. Unitario", "valor_total": "Vl. Total",
                    }
                    st.dataframe(
                        df_items[cols].rename(columns=names),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.warning("Nenhum item encontrado nesta nota.")

            # ── Botões de Ação ──
            a1, a2, a3, a4 = st.columns([1, 1, 1, 3])
            if a1.button("Aprovar",  key=f"apv_{uid}", type="primary", use_container_width=True):
                st.session_state["approvals"][uid] = "Aprovado"
                st.rerun()
            if a2.button("Rejeitar", key=f"rej_{uid}", use_container_width=True):
                st.session_state["approvals"][uid] = "Rejeitado"
                st.rerun()
            if a3.button("Pendente", key=f"pnd_{uid}", use_container_width=True):
                st.session_state["approvals"][uid] = "Pendente"
                st.rerun()


# ═══════════════════════════════════════════════════════════════════
# PAGE 2: EXPORTACAO
# ═══════════════════════════════════════════════════════════════════
elif page == "Exportacao":
    st.markdown("# Exportacao de Dados")
    st.caption("Visualize e exporte os dados triados para Excel ou CSV.")

    total_items = len(st.session_state["processed_data"]) + len(st.session_state["lancamentos_manuais"])
    if total_items == 0:
        st.info("Nenhum dado processado. Va para a aba Triagem ou Lancamento Manual primeiro.")
        st.stop()

    export_scope = st.radio(
        "Escopo das NFs",
        ["Somente Aprovados", "Todos Processados", "Aprovados + Pendentes"],
        horizontal=True,
    )

    all_data = st.session_state["processed_data"]
    if export_scope == "Somente Aprovados":
        export_list = [d for d in all_data if st.session_state["approvals"].get(d["uid"]) == "Aprovado"]
    elif export_scope == "Aprovados + Pendentes":
        export_list = [d for d in all_data if st.session_state["approvals"].get(d["uid"]) in ("Aprovado", "Pendente")]
    else:
        export_list = list(all_data)

    lancamentos = st.session_state["lancamentos_manuais"]
    incluir_manuais = st.checkbox("Incluir Lancamentos Manuais na exportacao", value=True)

    # Métricas
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    total_val = sum(d.get("valor_total", 0) for d in export_list)
    total_val_manual = sum(float(m.get("valor", 0) or 0) for m in lancamentos) if incluir_manuais else 0

    m1.metric("NFs", len(export_list))
    m2.metric("Lançamentos Manuais", len(lancamentos))
    m3.metric("Valor NFs", _fmt_brl(total_val))
    m4.metric("Valor Manuais", _fmt_brl(total_val_manual))
    m5.metric("Total Geral", _fmt_brl(total_val + total_val_manual))

    retornos = sum(1 for d in export_list if d.get("tipo_nf_classificado") == "Retorno/Devolução")
    m6.metric("Retornos/Devoluções", retornos)

    st.divider()

    # Tabelas de visualização
    rows = []
    for d in export_list:
        uid    = d["uid"]
        cat    = st.session_state["categories"].get(uid, "DESPESAS COM MATERIAL DIVERSOS")
        obra   = st.session_state["obras"].get(uid, "CUSTO DA OBRA GERAL")
        codigo = st.session_state.get("codigos", {}).get(uid, "")
        if not codigo:
            codigo, _ = _resolve_codigo_contabil(cat, obra)
        tipo_nf = d.get("tipo_nf_classificado", "Entrada")

        parcelas = d.get("parcelas", [])
        if not parcelas:
            parcelas = [{"nDup": "1", "dVenc": d.get("data_emissao"), "vDup": d.get("valor_total")}]

        for p in parcelas:
            rows.append({
                "Tipo NF":             tipo_nf,
                "Fornecedor":          d["fornecedor"],
                "Vencimento Parcela":  p.get("dVenc", ""),
                "Valor Parcela":       float(p.get("vDup") or d.get("valor_total") or 0.0),
                "NF":                  d["nNF"],
                "Parcela":             p.get("nDup", "1"),
                "Data Emissão NF":     d["data_emissao"],
                "CNPJ Fornecedor":     d.get("fornecedor_cnpj", ""),
                "Cliente":             d["cliente"],
                "Valor Total NF":      d["valor_total"],
                "Codigo Contabil":     codigo.lstrip("~"),
                "Categoria":           cat,
                "Obra":                obra,
                "CNO":                 d.get("cno_sugerido", ""),
                "Pagamento":           d.get("pagamento", ""),
                "Qtd Itens":           d.get("qtd_itens", 0),
                "Status":              st.session_state["approvals"].get(uid, "Pendente"),
                "Info Adicional":      (d.get("infAdic", "") or "")[:200],
            })

    df_export = pd.DataFrame(rows)

    # Adicionar lançamentos manuais à visualização
    if incluir_manuais and lancamentos:
        manual_rows_view = []
        for m in lancamentos:
            manual_rows_view.append({
                "Tipo NF":            "Manual",
                "Fornecedor":         m.get("fornecedor", ""),
                "Vencimento Parcela": m.get("vencimento", ""),
                "Valor Parcela":      float(m.get("valor", 0) or 0),
                "NF":                 m.get("nr_documento", ""),
                "Parcela":            "1",
                "Data Emissão NF":    m.get("data", ""),
                "CNPJ Fornecedor":    m.get("cnpj", ""),
                "Cliente":            m.get("cliente", ""),
                "Valor Total NF":     float(m.get("valor", 0) or 0),
                "Codigo Contabil":    m.get("codigo_contabil", "").lstrip("~"),
                "Categoria":          m.get("categoria", ""),
                "Obra":               m.get("obra", ""),
                "CNO":                m.get("cno", ""),
                "Pagamento":          m.get("forma_pagamento", ""),
                "Qtd Itens":          0,
                "Status":             "Aprovado",
                "Info Adicional":     m.get("observacao", ""),
            })
        df_manual_view = pd.DataFrame(manual_rows_view)
        df_combined = pd.concat([df_export, df_manual_view], ignore_index=True)
    else:
        df_combined = df_export

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Tabela Geral (Parcelas)", "Por Obra", "Por Categoria",
        "Resumo por Nota", "Retornos/Devoluções",
    ])

    with tab1:
        st.dataframe(df_combined, use_container_width=True, hide_index=True, height=400)

    with tab2:
        df_obra = (
            df_combined.groupby("Obra")
            .agg(Notas=("NF", "nunique"), Valor=("Valor Parcela", "sum"))
            .reset_index()
        )
        df_obra["Valor Fmt"] = df_obra["Valor"].apply(_fmt_brl)
        st.dataframe(df_obra[["Obra", "Notas", "Valor Fmt"]], use_container_width=True, hide_index=True)
        st.bar_chart(df_obra.set_index("Obra")["Valor"])

    with tab3:
        df_cat = (
            df_combined.groupby("Categoria")
            .agg(Notas=("NF", "nunique"), Valor=("Valor Parcela", "sum"))
            .reset_index()
        )
        df_cat["Valor Fmt"] = df_cat["Valor"].apply(_fmt_brl)
        st.dataframe(df_cat[["Categoria", "Notas", "Valor Fmt"]], use_container_width=True, hide_index=True)
        st.bar_chart(df_cat.set_index("Categoria")["Valor"])

    with tab4:
        note_rows = []
        for d in export_list:
            uid    = d["uid"]
            cat    = st.session_state["categories"].get(uid, "DESPESAS COM MATERIAL DIVERSOS")
            obra   = st.session_state["obras"].get(uid, "CUSTO DA OBRA GERAL")
            codigo = st.session_state.get("codigos", {}).get(uid, "").lstrip("~")
            note_rows.append({
                "Tipo NF":        d.get("tipo_nf_classificado", "Entrada"),
                "Fornecedor":     d["fornecedor"],
                "NF":             d["nNF"],
                "Valor Total":    d["valor_total"],
                "Data Emissão":   d["data_emissao"],
                "Obra":           obra,
                "Categoria":      cat,
                "Codigo Contabil": codigo,
                "CNO":            d.get("cno_sugerido", ""),
                "Pagamento":      d.get("pagamento", ""),
                "Qtd Itens":      d.get("qtd_itens", 0),
                "Status":         st.session_state["approvals"].get(uid, "Pendente"),
            })
        df_by_note = pd.DataFrame(note_rows)
        st.dataframe(df_by_note, use_container_width=True, hide_index=True, height=400)

    with tab5:
        df_ret = df_combined[df_combined["Tipo NF"] == "Retorno/Devolução"]
        if df_ret.empty:
            st.success("✅ Nenhuma nota de retorno/devolucao identificada no lote.")
        else:
            st.warning(f"⚠️ {len(df_ret)} parcela(s) de Retorno/Devolucao identificadas:")
            st.dataframe(df_ret, use_container_width=True, hide_index=True, height=300)
            total_ret = df_ret["Valor Parcela"].sum()
            st.metric("Total em Retornos", _fmt_brl(total_ret))

    st.divider()
    st.markdown("### 📥 Opções de Download")

    dc1, dc2, dc3, dc4 = st.columns(4)

    # 1. Modelo oficial Domínio Contábil
    dominio_data = export_to_dominio_excel(
        export_list,
        st.session_state["categories"],
        st.session_state["obras"],
        st.session_state["codigos"],
        st.session_state["approvals"],
        fornecedores_map=st.session_state.get("fornecedores_map", {}),
    )
    if dominio_data:
        dc1.download_button(
            "⭐ Baixar Modelo Domínio (.xlsx)",
            data=dominio_data,
            file_name="lancamentos_dominio_hikari.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
            help="Planilha formatada exatamente conforme o modelo de lançamentos do Domínio Contábil (Plan1)",
        )

    excel_data = export_to_excel(
        export_list,
        st.session_state["categories"],
        st.session_state["obras"],
        st.session_state["approvals"],
        codigos=st.session_state["codigos"],
        lancamentos_manuais=lancamentos if incluir_manuais else [],
    )
    if excel_data:
        dc2.download_button(
            "⬇️ Baixar Relatório Multi-Aba (.xlsx)",
            data=excel_data,
            file_name="hikari_notas_triadas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    if not df_combined.empty:
        csv_data = df_combined.to_csv(index=False).encode("utf-8-sig")
        dc3.download_button(
            "⬇️ Baixar CSV Geral",
            data=csv_data,
            file_name="hikari_notas_triadas.csv",
            mime="text/csv",
            use_container_width=True,
        )

    detail_rows = []
    for d in export_list:
        uid    = d["uid"]
        cat    = st.session_state["categories"].get(uid, "DESPESAS COM MATERIAL DIVERSOS")
        obra   = st.session_state["obras"].get(uid, "CUSTO DA OBRA GERAL")
        codigo = st.session_state.get("codigos", {}).get(uid, "").lstrip("~")
        if not codigo:
            c_res, _ = _resolve_codigo_contabil(cat, obra)
            codigo = c_res.lstrip("~")
        tipo_nf = d.get("tipo_nf_classificado", "Entrada")
        for item in d.get("itens", []):
            detail_rows.append({
                "Tipo NF":        tipo_nf,
                "NF":             d["nNF"],
                "Fornecedor":     d["fornecedor"],
                "Codigo Contabil": codigo,
                "Obra":           obra,
                "Categoria":      cat,
                "CNO":            d.get("cno_sugerido", ""),
                **item,
            })
    if detail_rows:
        df_detail = pd.DataFrame(detail_rows)
        csv_detail = df_detail.to_csv(index=False).encode("utf-8-sig")
        dc4.download_button(
            "⬇️ Baixar Itens Detalhados (CSV)",
            data=csv_detail,
            file_name="hikari_itens_detalhados.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════════════
# PAGE: FORNECEDORES & OBRAS (Lookup Tables)
# ═══════════════════════════════════════════════════════════════════
elif page == "Fornecedores & Obras":
    st.markdown("# Tabela de Fornecedores e Obras")
    st.caption("Consulta das tabelas oficiais de Fornecedores e Plano de Contas com CNO da Hikari.")

    tab_f, tab_o = st.tabs(["🏢 Fornecedores (Códigos Contábeis)", "🏗️ Obras & CNOs (Contas.xlsx)"])

    with tab_f:
        df_fornec = fornecedor_db.load_fornecedores()
        f_search = st.text_input("🔍 Buscar Fornecedor por Nome:", placeholder="Digite o nome da empresa...")
        if f_search:
            mask = df_fornec["nome_fornecedor"].str.contains(f_search, case=False, na=False)
            df_display = df_fornec[mask]
        else:
            df_display = df_fornec

        st.markdown(f"**Total cadastrado:** {len(df_fornec)} fornecedores | **Exibindo:** {len(df_display)}")
        st.dataframe(df_display, use_container_width=True, hide_index=True, height=450)

    with tab_o:
        obras_data = contas_db.get_all_obras()
        o_search = st.text_input("🔍 Buscar Obra ou CNO:", placeholder="Digite nome da obra ou CNO...")
        rows_o = []
        for o in obras_data:
            cno_val = o.get("cno") or "—"
            nome_val = o.get("nome_display") or o.get("display") or ""
            row_dict = {
                "Código Contábil": o.get("codigo"),
                "Classificação": o.get("classificacao"),
                "Nome da Obra": nome_val,
                "CNO": cno_val,
                "Categorias Mapeadas": len(o.get("categorias", {})),
            }
            if o_search:
                if (o_search.lower() in str(nome_val).lower() or
                    o_search in str(cno_val)):
                    rows_o.append(row_dict)
            else:
                rows_o.append(row_dict)

        df_obras_tab = pd.DataFrame(rows_o)
        st.markdown(f"**Total de Obras:** {len(obras_data)} | **Exibindo:** {len(df_obras_tab)}")
        st.dataframe(df_obras_tab, use_container_width=True, hide_index=True, height=350)

        st.markdown("---")
        st.markdown("### 🔎 Detalhamento: Segmento e suas Subclasses (Contas Analíticas)")
        st.caption("Selecione um segmento/obra abaixo para visualizar em detalhes todas as suas subclasses de despesa com nome e número:")
        obra_labels = [o["dropdown_label"] for o in obras_data if o.get("dropdown_label")]
        sel_detalhe = st.selectbox("Selecione a Obra para detalhamento:", obra_labels, key="sel_obra_detalhe")

        if sel_detalhe:
            subclasses = contas_db.get_subclasses_for_obra(sel_detalhe)
            o_info = contas_db.get_obra_by_identifier(sel_detalhe)
            cno_info = f" | **CNO:** {o_info['cno']}" if o_info and o_info.get("cno") else ""
            st.info(f"🏗️ **Segmento / Obra:** {o_info.get('nome_display')} | **Cód. Conta:** {o_info.get('codigo')} ({o_info.get('classificacao')}){cno_info}")

            if subclasses:
                st.markdown(f"**Subclasses / Contas Analíticas Vinculadas ({len(subclasses)} contas):**")
                sub_table = []
                for s in subclasses:
                    sub_table.append({
                        "Código da Subclasse": s.get("codigo"),
                        "Classificação": s.get("classificacao"),
                        "Nome da Subclasse (Despesa)": s.get("nome"),
                    })
                st.dataframe(pd.DataFrame(sub_table), use_container_width=True, hide_index=True)
            else:
                st.warning("Nenhuma subclasse vinculada.")


# ═══════════════════════════════════════════════════════════════════
# PAGE 3: PLANO DE CONTAS
# ═══════════════════════════════════════════════════════════════════
elif page == "Plano de Contas":
    st.markdown("# Plano de Contas")
    st.caption(
        "Gerencie as categorias de despesa e obras/centros de custo. "
        "Adições aqui aparecem nos dropdowns de triagem e são salvas automaticamente."
    )

    tab_cat, tab_obra = st.tabs(["📂 Categorias de Despesa", "🏗️ Obras / Centros de Custo"])

    # ── Tab: Categorias ──────────────────────────────────────────
    with tab_cat:
        st.markdown("### Categorias Base (Plano Hikari)")
        base_cat_rows = []
        for suffix, (nome, _) in sorted(HIKARI_DESPESAS.items()):
            base_cat_rows.append({"Código": suffix, "Descrição": nome, "Tipo": "Base"})
        st.dataframe(pd.DataFrame(base_cat_rows), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Categorias Extras (Personalizadas)")

        extra_cats = st.session_state["plano_extra_cats"]

        if extra_cats:
            extra_cat_df = pd.DataFrame(extra_cats)
            st.dataframe(extra_cat_df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma categoria extra adicionada ainda.")

        st.markdown("#### Adicionar Nova Categoria")
        with st.form("form_add_cat"):
            nc1, nc2 = st.columns([1, 3])
            novo_cod_cat  = nc1.text_input("Código (ex: 019)", max_chars=10)
            novo_nome_cat = nc2.text_input("Nome da Categoria (ex: DESPESAS COM SEGUROS)")
            submit_cat = st.form_submit_button("➕ Adicionar Categoria", type="primary")

        if submit_cat:
            if not novo_cod_cat or not novo_nome_cat:
                st.error("Preencha código e nome antes de adicionar.")
            else:
                nome_up = novo_nome_cat.strip().upper()
                cod_up  = novo_cod_cat.strip()
                # Verifica duplicata
                existentes = [c["nome"] for c in extra_cats] + HIKARI_DESPESAS_LISTA
                if nome_up in existentes:
                    st.warning(f"Categoria '{nome_up}' já existe.")
                else:
                    st.session_state["plano_extra_cats"].append({"codigo": cod_up, "nome": nome_up})
                    # Persiste no JSON
                    save_plano_json({
                        "categorias_extras": st.session_state["plano_extra_cats"],
                        "obras_extras":      st.session_state["plano_extra_obras"],
                    })
                    st.success(f"Categoria '{nome_up}' adicionada e salva!")
                    st.rerun()

        # Remover categoria extra
        if extra_cats:
            st.markdown("#### Remover Categoria Extra")
            nomes_extras = [c["nome"] for c in extra_cats]
            to_remove_cat = st.selectbox("Selecionar para remover", nomes_extras, key="rm_cat")
            if st.button("🗑️ Remover Categoria Selecionada", key="btn_rm_cat"):
                st.session_state["plano_extra_cats"] = [
                    c for c in extra_cats if c["nome"] != to_remove_cat
                ]
                save_plano_json({
                    "categorias_extras": st.session_state["plano_extra_cats"],
                    "obras_extras":      st.session_state["plano_extra_obras"],
                })
                st.success(f"Categoria '{to_remove_cat}' removida.")
                st.rerun()

    # ── Tab: Obras ───────────────────────────────────────────────
    with tab_obra:
        st.markdown("### Obras Base (Plano Hikari)")
        base_obra_rows = []
        for cls, (cod, nome) in sorted(HIKARI_OBRAS.items()):
            base_obra_rows.append({"Classificação": cls, "Código": cod, "Nome": nome, "Tipo": "Base"})
        st.dataframe(pd.DataFrame(base_obra_rows), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Obras Extras (Personalizadas)")

        extra_obras = st.session_state["plano_extra_obras"]

        if extra_obras:
            st.dataframe(pd.DataFrame(extra_obras), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma obra extra adicionada ainda.")

        st.markdown("#### Adicionar Nova Obra")
        with st.form("form_add_obra"):
            no1, no2, no3 = st.columns([1, 1, 3])
            nova_cls_obra  = no1.text_input("Classificação (ex: 3.1.1.22)", max_chars=12)
            novo_cod_obra  = no2.text_input("Código Numérico (ex: 2100)", max_chars=10)
            novo_nome_obra = no3.text_input("Nome da Obra (ex: HOSPITAL REGIONAL PALMAS)")
            submit_obra = st.form_submit_button("➕ Adicionar Obra", type="primary")

        if submit_obra:
            if not novo_nome_obra:
                st.error("O nome da obra é obrigatório.")
            else:
                nome_up = novo_nome_obra.strip().upper()
                existentes = [o["nome"] for o in extra_obras] + HIKARI_OBRAS_LISTA
                if nome_up in existentes:
                    st.warning(f"Obra '{nome_up}' já existe.")
                else:
                    st.session_state["plano_extra_obras"].append({
                        "classificacao": nova_cls_obra.strip(),
                        "codigo":        novo_cod_obra.strip(),
                        "nome":          nome_up,
                    })
                    save_plano_json({
                        "categorias_extras": st.session_state["plano_extra_cats"],
                        "obras_extras":      st.session_state["plano_extra_obras"],
                    })
                    st.success(f"Obra '{nome_up}' adicionada e salva!")
                    st.rerun()

        if extra_obras:
            st.markdown("#### Remover Obra Extra")
            nomes_extras_obra = [o["nome"] for o in extra_obras]
            to_remove_obra = st.selectbox("Selecionar para remover", nomes_extras_obra, key="rm_obra")
            if st.button("🗑️ Remover Obra Selecionada", key="btn_rm_obra"):
                st.session_state["plano_extra_obras"] = [
                    o for o in extra_obras if o["nome"] != to_remove_obra
                ]
                save_plano_json({
                    "categorias_extras": st.session_state["plano_extra_cats"],
                    "obras_extras":      st.session_state["plano_extra_obras"],
                })
                st.success(f"Obra '{to_remove_obra}' removida.")
                st.rerun()

    st.divider()
    st.markdown("#### Mapeamento de Códigos Contábeis (Balancete)")
    st.caption(
        "Para combinações obra+despesa não mapeadas, o sistema usa o código da Obra Geral "
        "como fallback (exibido em amarelo nos cards). Entre em contato com a contabilidade "
        "para adicionar os códigos específicos ao sistema."
    )
    st.info(
        "💡 Os códigos das obras extras ainda não têm mapeamento automático no balancete. "
        "Use o campo 'Código Numérico' ao adicionar a obra para que apareça na exportação."
    )


# ═══════════════════════════════════════════════════════════════════
# PAGE 4: LANÇAMENTO MANUAL
# ═══════════════════════════════════════════════════════════════════
elif page == "Lancamento Manual":
    st.markdown("# Lançamento Manual")
    st.caption(
        "Registre aqui lançamentos feitos manualmente no sistema Domínio. "
        "Eles serão incluídos na exportação Excel para conferência."
    )

    all_cats_lista  = get_all_categorias(st.session_state["plano_extra_cats"])
    all_obras_lista = get_all_obras(st.session_state["plano_extra_obras"])

    # ── Formulário de Novo Lançamento ────────────────────────────
    with st.expander("➕ Novo Lançamento Manual", expanded=True):
        with st.form("form_lancamento_manual", clear_on_submit=True):
            r1c1, r1c2, r1c3 = st.columns(3)
            data_lanc       = r1c1.date_input("Data do Documento", value=datetime.date.today())
            vencimento_lanc = r1c2.date_input("Vencimento", value=datetime.date.today())
            nr_doc          = r1c3.text_input("Nº Documento / NF")

            r2c1, r2c2 = st.columns([2, 1])
            fornecedor_lanc = r2c1.text_input("Fornecedor / Credor")
            cnpj_lanc       = r2c2.text_input("CNPJ (opcional)", max_chars=18)

            r3c1, r3c2, r3c3 = st.columns(3)
            valor_lanc      = r3c1.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f")
            forma_pag_lanc  = r3c2.selectbox("Forma Pagamento", [
                "Boleto", "PIX", "Transferencia", "Cheque", "Dinheiro", "Cartao Credito", "Outros"
            ])
            cliente_lanc    = r3c3.text_input("Cliente / Tomador (opcional)")

            r4c1, r4c2 = st.columns(2)
            cat_lanc  = r4c1.selectbox("Categoria de Despesa", all_cats_lista)
            obra_lanc = r4c2.selectbox("Obra / Centro de Custo (Segmento)", OBRA_OPTIONS)

            # Calcular código contábil automaticamente
            codigo_lanc, lanc_info = _resolve_codigo_contabil(cat_lanc, obra_lanc)
            cno_auto = lanc_info.get("cno") or ""
            cno_lanc = st.text_input("CNO", value=cno_auto, max_chars=20)
            obs_lanc = st.text_area("Observação / Histórico", max_chars=300, height=80)

            sub_cls = lanc_info.get("classificacao", "")
            sub_cls_str = f" ({sub_cls})" if sub_cls else ""

            st.markdown(
                f'<div class="manual-header">🏛️ Conta Analítica: '
                f'<strong>{codigo_lanc.lstrip("~") or "não mapeado"}</strong>{sub_cls_str} — {cat_lanc}'
                + (' &nbsp;<small>(⚠️ fallback Obra Geral)</small>' if codigo_lanc.startswith("~") else "")
                + '</div>',
                unsafe_allow_html=True,
            )

            submit_lanc = st.form_submit_button("💾 Salvar Lançamento", type="primary", use_container_width=True)

        if submit_lanc:
            if not fornecedor_lanc or valor_lanc <= 0:
                st.error("Fornecedor e Valor são obrigatórios.")
            else:
                novo_lanc = {
                    "id":              len(st.session_state["lancamentos_manuais"]) + 1,
                    "data":            str(data_lanc),
                    "vencimento":      str(vencimento_lanc),
                    "nr_documento":    nr_doc,
                    "fornecedor":      fornecedor_lanc.strip().upper(),
                    "cnpj":            cnpj_lanc,
                    "valor":           valor_lanc,
                    "forma_pagamento": forma_pag_lanc,
                    "cliente":         cliente_lanc,
                    "categoria":       cat_lanc,
                    "obra":            obra_lanc,
                    "cno":             cno_lanc,
                    "codigo_contabil": codigo_lanc,
                    "observacao":      obs_lanc,
                }
                st.session_state["lancamentos_manuais"].append(novo_lanc)
                st.success(f"✅ Lançamento de {_fmt_brl(valor_lanc)} ({fornecedor_lanc}) salvo!")
                st.rerun()

    # ── Listagem ─────────────────────────────────────────────────
    lancamentos = st.session_state["lancamentos_manuais"]
    st.divider()
    st.markdown(f"### Lançamentos Registrados ({len(lancamentos)})")

    if not lancamentos:
        st.info("Nenhum lançamento manual registrado ainda.")
    else:
        # Métricas rápidas
        total_manual = sum(float(m.get("valor", 0) or 0) for m in lancamentos)
        lm1, lm2, lm3 = st.columns(3)
        lm1.metric("Total de Lançamentos", len(lancamentos))
        lm2.metric("Valor Total", _fmt_brl(total_manual))
        obras_man = len(set(m.get("obra", "") for m in lancamentos))
        lm3.metric("Obras Envolvidas", obras_man)

        st.markdown("---")

        for i, m in enumerate(lancamentos):
            codigo_m = m.get("codigo_contabil", "").lstrip("~")
            with st.container(border=True):
                mc1, mc2, mc3 = st.columns([4, 2, 1])
                with mc1:
                    st.markdown(
                        f"**#{m['id']} — {m['fornecedor']}**  \n"
                        f"📅 Doc: {m['data']} | Venc: {m['vencimento']} | NF/Doc: {m.get('nr_documento', '—')}"
                    )
                    st.caption(
                        f"🏗️ {m['obra']} | 📂 {m['categoria']} | "
                        f"💳 {m['forma_pagamento']}"
                        + (f" | CNO: {m['cno']}" if m.get('cno') else "")
                    )
                with mc2:
                    st.metric("Valor", _fmt_brl(m.get("valor", 0)))
                    if codigo_m:
                        st.caption(f"Cod. Contábil: **{codigo_m}**")
                with mc3:
                    if st.button("🗑️", key=f"del_lanc_{i}", help="Excluir este lançamento"):
                        st.session_state["lancamentos_manuais"].pop(i)
                        st.rerun()

                if m.get("observacao"):
                    st.caption(f"📝 {m['observacao']}")

        st.divider()
        # Export dos lançamentos manuais
        if lancamentos:
            df_lanc = pd.DataFrame(lancamentos)
            csv_lanc = df_lanc.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Exportar Lançamentos Manuais (CSV)",
                data=csv_lanc,
                file_name="hikari_lancamentos_manuais.csv",
                mime="text/csv",
                use_container_width=True,
            )

        if st.button("🗑️ Limpar Todos os Lançamentos", type="secondary"):
            st.session_state["lancamentos_manuais"] = []
            st.rerun()
