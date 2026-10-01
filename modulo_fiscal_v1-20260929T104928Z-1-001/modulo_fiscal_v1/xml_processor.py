"""
xml_processor.py — NF-e XML Parser (Robust)
Strips XML namespaces before parsing so that tag paths like
'ide/nNF' work regardless of whether the XML uses xmlns or not.
"""
import xml.etree.ElementTree as ET
import re

NS = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

# ══════════════════════════════════════════════════════════════
# CFOPs de Retorno / Devolução
# ══════════════════════════════════════════════════════════════
CFOPS_RETORNO = {
    # Devoluções de compra (entrada)
    "1201", "1202", "1410", "1411", "1413",
    "2201", "2202", "2410", "2411", "2413",
    # Devoluções de venda (saída)
    "5201", "5202", "5410", "5411", "5413",
    "6201", "6202", "6410", "6411", "6413",
    # Retornos de remessa
    "1503", "1504", "2503", "2504",
    "5503", "5504", "6503", "6504",
}

# Palavras-chave na natureza de operação que indicam retorno
_NATOP_RETORNO_RE = re.compile(
    r'\b(devol|retorno|devolu|cancelamento|estorno)\b',
    re.IGNORECASE
)


def detect_tipo_nf(tp_nf: str, nat_op: str, cfops: list[str]) -> str:
    """
    Classifica o tipo real da NF-e:
      - "Retorno/Devolução" se houver CFOP de devolução ou natOp indicar retorno
      - "Entrada"  se tpNF == "0"
      - "Saída"    se tpNF == "1"
    """
    # Verifica CFOPs de retorno (remove pontos para comparação)
    cfops_clean = [c.replace(".", "") for c in cfops if c]
    if any(c in CFOPS_RETORNO for c in cfops_clean):
        return "Retorno/Devolução"

    # Verifica palavras-chave na natureza da operação
    if nat_op and _NATOP_RETORNO_RE.search(nat_op):
        return "Retorno/Devolução"

    if tp_nf == "0":
        return "Entrada"
    if tp_nf == "1":
        return "Saída"
    return "Entrada"  # fallback seguro


def _find_text(elem, path):
    """Safely extract text from an XML element path using proper namespaces."""
    if elem is None:
        return ""

    # Se o caminho usar namespace "nfe:", vamos deixar passar,
    # senão, prepend "nfe:" automaticamente para manter o código menor
    ns_path = "/".join(f"nfe:{p}" if ":" not in p else p for p in path.split("/"))

    node = elem.find(ns_path, NS)
    return (node.text or "").strip() if node is not None else ""


def extract_cno(inf_adic):
    """
    Robustly extracts CNO from text.
    Handles cases where text exists between 'CNO' label and the number.
    CNO is exactly 12 digits: XX.XXX.XXXXX/XX
    """
    if not inf_adic:
        return None

    # Normalize spaces for easier regex
    text = " ".join(inf_adic.split())

    # 1. Look for the "CNO" keyword and then search for a 12-digit pattern nearby
    cno_label = re.search(r"(?i)CNO", text)
    if cno_label:
        search_start = cno_label.end()
        search_area = text[search_start:search_start + 100]
        match = re.search(r"(\d{2}[\.\s]?\d{3}[\.\s]?\d{5}[\.\/\s]?\d{2})", search_area)
        if match:
            digits = re.sub(r"\D", "", match.group(1))
            if len(digits) == 12:
                return f"{digits[:2]}.{digits[2:5]}.{digits[5:10]}/{digits[10:]}"

    # 2. Fallback: Search for the specific XX.XXX.XXXXX/XX pattern anywhere
    pattern_strict = re.search(r"(\d{2}\.\d{3}\.\d{5}/\d{2})", text)
    if pattern_strict:
        d = re.sub(r"\D", "", pattern_strict.group(1))
        if len(d) == 12:
            return f"{d[:2]}.{d[2:5]}.{d[5:10]}/{d[10:]}"
        return pattern_strict.group(1).strip()

    # 3. Last attempt: any sequence of digits that looks like a CNO (12 digits)
    all_digit_sequences = re.findall(r"\d[\d\.\-\/]{10,20}\d", text)
    for seq in all_digit_sequences:
        digits = re.sub(r"\D", "", seq)
        if len(digits) == 12:
            return f"{digits[:2]}.{digits[2:5]}.{digits[5:10]}/{digits[10:]}"

    return None


def extract_obra_name(inf_adic):
    """Tries to extract a human-readable project/obra name from infAdic."""
    if not inf_adic:
        return None
    match = re.search(
        r'(?:referente\s+a\s+obra|obra|projeto|ref\.?\s*obra)\s*[:\-]?\s*([^.;,\n]+)',
        inf_adic, re.IGNORECASE
    )
    if match:
        name = match.group(1).strip()
        name = re.sub(r'\s*CNO.*$', '', name, flags=re.IGNORECASE).strip()
        if len(name) > 3:
            return name
    return None


def fmt_brl(value_str):
    """Formats a numeric string as BRL currency."""
    try:
        v = float(value_str)
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return value_str or "R$ 0,00"


def parse_nfe(xml_content):
    """
    Parses a single NF-e XML (bytes or string) ignoring or respecting namespaces.
    Returns a LIST of dictionaries, where each dict represents one PARCELA (dup).
    If no parcelas are found, it returns a list with a single dictionary representing the invoice.
    """
    try:
        if isinstance(xml_content, str):
            xml_bytes = xml_content.encode("utf-8")
        else:
            xml_bytes = xml_content

        root = ET.fromstring(xml_bytes)

        infNFe = root.find('.//nfe:infNFe', NS)
        if infNFe is None:
            return [{"error": "Estrutura invalida de NF-e - tag <infNFe> com namespace nao encontrada."}]

        # ── IDE (Identificacao) ──
        nNF    = _find_text(infNFe, 'ide/nNF')
        serie  = _find_text(infNFe, 'ide/serie')
        dhEmi  = _find_text(infNFe, 'ide/dhEmi')
        natOp  = _find_text(infNFe, 'ide/natOp')
        tpNF   = _find_text(infNFe, 'ide/tpNF')

        # ── EMIT (Emitente / Fornecedor) ──
        emit_xNome = _find_text(infNFe, 'emit/xNome')
        emit_xFant = _find_text(infNFe, 'emit/xFant')
        emit_CNPJ  = _find_text(infNFe, 'emit/CNPJ')
        emit_IE    = _find_text(infNFe, 'emit/IE')
        emit_UF    = _find_text(infNFe, 'emit/enderEmit/UF')
        emit_Mun   = _find_text(infNFe, 'emit/enderEmit/xMun')

        # ── DEST (Destinatario / Cliente) ──
        dest_xNome = _find_text(infNFe, 'dest/xNome')
        dest_CNPJ  = _find_text(infNFe, 'dest/CNPJ')
        dest_CPF   = _find_text(infNFe, 'dest/CPF')
        dest_UF    = _find_text(infNFe, 'dest/enderDest/UF')
        dest_Mun   = _find_text(infNFe, 'dest/enderDest/xMun')

        # ── TOTAL ──
        vNF    = _find_text(infNFe, 'total/ICMSTot/vNF')
        vProd  = _find_text(infNFe, 'total/ICMSTot/vProd')
        vDesc  = _find_text(infNFe, 'total/ICMSTot/vDesc')
        vFrete = _find_text(infNFe, 'total/ICMSTot/vFrete')
        vICMS  = _find_text(infNFe, 'total/ICMSTot/vICMS')

        # Reforma Tributária (IBS/CBS)
        vIBSCBS = _find_text(infNFe, 'total/ICMSTot/vIBSCBS') or _find_text(infNFe, 'total/IBSCBSTot/vIBSCBS')
        pCBS    = _find_text(infNFe, 'total/ICMSTot/pCBS') or _find_text(infNFe, 'total/IBSCBSTot/pCBS')

        val = 0.0
        try:
            val = float(vNF)
        except (ValueError, TypeError):
            pass

        # ── ITEMS (det/prod) ──
        items = []
        cfops_nota = []
        dets = infNFe.findall('nfe:det', NS)
        total_prod_sum = 0.0
        total_desc_items = 0.0

        for det in dets:
            prod = det.find('nfe:prod', NS)
            if prod is None:
                continue
            cfop = _find_text(prod, 'CFOP')
            if cfop:
                cfops_nota.append(cfop)

            v_prod_val = float(_find_text(prod, 'vProd') or 0.0)
            v_desc_val = float(_find_text(prod, 'vDesc') or 0.0)
            total_prod_sum += v_prod_val
            total_desc_items += v_desc_val

            items.append({
                "codigo":         _find_text(prod, 'cProd'),
                "descricao":      _find_text(prod, 'xProd'),
                "ncm":            _find_text(prod, 'NCM'),
                "cfop":           cfop,
                "qtd":            _find_text(prod, 'qCom'),
                "unidade":        _find_text(prod, 'uCom'),
                "valor_unit":     _find_text(prod, 'vUnCom'),
                "valor_total":    v_prod_val,
                "valor_desconto": v_desc_val,
            })

        # ── CLASSIFICAÇÃO DO TIPO NF ──
        tipo_nf = detect_tipo_nf(tpNF, natOp, cfops_nota)

        # ── PAGAMENTO ──
        pag_tipo  = _find_text(infNFe, 'pag/detPag/tPag')
        pag_valor = _find_text(infNFe, 'pag/detPag/vPag')
        ind_pag   = _find_text(infNFe, 'pag/detPag/indPag') or _find_text(infNFe, 'ide/indPag')

        TIPO_PAG = {
            "01": "Dinheiro", "02": "Cheque", "03": "Cartao Credito",
            "04": "Cartao Debito", "05": "Credito Loja", "10": "Vale Alimentacao",
            "11": "Vale Refeicao", "12": "Vale Presente", "13": "Vale Combustivel",
            "15": "Boleto", "16": "Deposito", "17": "PIX", "18": "Transferencia",
            "90": "Sem Pagamento", "99": "Outros",
        }
        pag_descricao = TIPO_PAG.get(pag_tipo, pag_tipo)

        # Date formatting
        data_emissao = dhEmi[:10] if len(dhEmi) >= 10 else dhEmi
        hora_emissao = dhEmi[11:19] if len(dhEmi) >= 19 else ""

        # ── TRANSPORTE ──
        modFrete = _find_text(infNFe, 'transp/modFrete')
        qVol     = _find_text(infNFe, 'transp/vol/qVol')
        pesoL    = _find_text(infNFe, 'transp/vol/pesoL')
        pesoB    = _find_text(infNFe, 'transp/vol/pesoB')

        # ── ENTREGA ──
        entrega_xLgr    = _find_text(infNFe, 'entrega/xLgr')
        entrega_nro     = _find_text(infNFe, 'entrega/nro')
        entrega_xBairro = _find_text(infNFe, 'entrega/xBairro')
        entrega_xMun    = _find_text(infNFe, 'entrega/xMun')
        entrega_UF      = _find_text(infNFe, 'entrega/UF')

        endereco_entrega = ""
        if entrega_xLgr:
            endereco_entrega = f"{entrega_xLgr}, {entrega_nro} - {entrega_xBairro}, {entrega_xMun}-{entrega_UF}"

        # ── COBRANÇA (Parcelas) ──
        parcelas = []
        cobr = infNFe.find('nfe:cobr', NS)
        if cobr is not None:
            for dup in cobr.findall('nfe:dup', NS):
                parcelas.append({
                    "nDup":  _find_text(dup, 'nDup'),
                    "dVenc": _find_text(dup, 'dVenc') or data_emissao,
                    "vDup":  float(_find_text(dup, 'vDup') or 0.0),
                })

        # Identifica se é pagamento À VISTA
        # indPag == 0: Pagamento a vista
        # Ou pag_tipo em ("01", "04", "17") -> Dinheiro, Cartao Debito, PIX
        # Ou sem parcelas / apenas 1 parcela com vencimento na mesma data de emissao
        is_a_vista = (
            ind_pag == "0" or
            pag_tipo in ("01", "04", "17") or
            (not parcelas and pag_descricao != "Sem Pagamento") or
            (len(parcelas) == 1 and parcelas[0].get("dVenc") == data_emissao)
        )

        pag_label = pag_descricao
        if is_a_vista and "À vista" not in pag_label and pag_descricao != "Sem Pagamento":
            pag_label += " (À vista)"

        # ── INF ADIC ──
        infCpl     = _find_text(infNFe, 'infAdic/infCpl')
        infAdFisco = _find_text(infNFe, 'infAdic/infAdFisco')

        obs_cont_list = []
        obs_nodes = infNFe.findall('nfe:infAdic/nfe:obsCont', NS)
        for obs in obs_nodes:
            x_campo = obs.get('xCampo', '')
            x_texto = _find_text(obs, 'xTexto')
            if x_texto:
                obs_cont_list.append(f"{x_campo}: {x_texto}")
        obsCont = " | ".join(obs_cont_list)

        combined_text = f"{infCpl} {infAdFisco} {obsCont} {endereco_entrega}"
        cno       = extract_cno(combined_text)
        obra_name = extract_obra_name(combined_text)

        # ── PROTOCOLO ──
        chNFe = _find_text(root, 'protNFe/infProt/chNFe')
        nProt = _find_text(root, 'protNFe/infProt/nProt')

        v_desc_total = float(vDesc or 0.0)
        if total_desc_items > 0 and v_desc_total == 0.0:
            v_desc_total = total_desc_items

        base_record = {
            "nNF":               nNF,
            "serie":             serie,
            "chave":             chNFe,
            "protocolo":         nProt,
            "natureza_op":       natOp,
            "tipo":              "Saida" if tpNF == "1" else "Entrada",
            "tipo_nf_classificado": tipo_nf,
            "cfops_nota":        cfops_nota,
            "data_emissao":      data_emissao,
            "hora_emissao":      hora_emissao,
            "fornecedor":        emit_xNome,
            "fornecedor_fantasia": emit_xFant,
            "fornecedor_cnpj":   emit_CNPJ,
            "fornecedor_ie":     emit_IE,
            "fornecedor_uf":     emit_UF,
            "fornecedor_cidade": emit_Mun,
            "cliente":           dest_xNome,
            "cliente_doc":       dest_CNPJ or dest_CPF,
            "cliente_uf":        dest_UF,
            "cliente_cidade":    dest_Mun,
            "valor_produtos":    float(vProd or 0.0),
            "valor_desconto":    v_desc_total,
            "valor_frete":       float(vFrete or 0.0),
            "valor_icms":        float(vICMS or 0.0),
            "valor_total":       val,
            "valor_formatted":   fmt_brl(vNF),
            "itens":             items,
            "qtd_itens":         len(items),
            "qtd_parcelas":      len(parcelas) if parcelas else 1,
            "pagamento":         pag_label,
            "pagamento_tipo_cod": pag_tipo,
            "is_a_vista":        is_a_vista,
            "pagamento_valor":   fmt_brl(pag_valor),
            "modalidade_frete":  modFrete,
            "volume_qtd":        qVol,
            "peso_liquido":      pesoL,
            "peso_bruto":        pesoB,
            "endereco_entrega":  endereco_entrega,
            "imposto_ibscbs":    vIBSCBS,
            "imposto_pcbs":      pCBS,
            "infAdic":           infCpl,
            "infAdFisco":        infAdFisco,
            "obsCont":           obsCont,
            "cno_sugerido":      cno,
            "obra_nome":         obra_name,
        }

        # ── SEPARAÇÃO POR CFOPs DISTINTOS ──
        # Se houver itens com CFOPs diferentes, a nota é desmembrada/duplicada por CFOP
        cfops_distintos = sorted(list(set(c for c in cfops_nota if c)))
        if not cfops_distintos:
            cfops_distintos = [""]

        records = []

        # Agrupa itens por CFOP
        for cfop_curr in cfops_distintos:
            if cfop_curr:
                itens_cfop = [it for it in items if it.get("cfop") == cfop_curr]
            else:
                itens_cfop = items

            prod_cfop_sum = sum(it.get("valor_total", 0.0) for it in itens_cfop)

            # Proporção do desconto e valor líquido para este CFOP
            if total_prod_sum > 0:
                prop = prod_cfop_sum / total_prod_sum
            else:
                prop = 1.0 / len(cfops_distintos)

            desc_cfop = round(v_desc_total * prop, 2)
            # Valor total líquido para este CFOP
            if len(cfops_distintos) > 1:
                val_cfop = round(prod_cfop_sum - desc_cfop, 2)
            else:
                val_cfop = val

            rec_cfop = base_record.copy()
            rec_cfop["cfop_destaque"] = cfop_curr
            rec_cfop["itens"] = itens_cfop
            rec_cfop["qtd_itens"] = len(itens_cfop)
            rec_cfop["valor_produtos"] = prod_cfop_sum
            rec_cfop["valor_desconto"] = desc_cfop
            rec_cfop["valor_total"] = val_cfop
            rec_cfop["valor_formatted"] = fmt_brl(str(val_cfop))

            # Ajusta parcelas para o valor deste CFOP
            if not parcelas:
                rec_cfop_p = rec_cfop.copy()
                rec_cfop_p["parcela_numero"]     = "1"
                rec_cfop_p["parcela_vencimento"] = data_emissao
                rec_cfop_p["parcela_valor"]      = val_cfop
                records.append(rec_cfop_p)
            else:
                for p in parcelas:
                    rec_cfop_p = rec_cfop.copy()
                    p_val_orig = float(p.get("vDup", 0.0) or 0.0)
                    p_val_cfop = round(p_val_orig * prop, 2) if len(cfops_distintos) > 1 else p_val_orig
                    rec_cfop_p["parcela_numero"]     = p.get("nDup", "1")
                    rec_cfop_p["parcela_vencimento"] = p.get("dVenc", data_emissao)
                    rec_cfop_p["parcela_valor"]      = p_val_cfop
                    records.append(rec_cfop_p)

        return records

    except ET.ParseError as e:
        return [{"error": f"XML malformado: {str(e)}"}]
    except Exception as e:
        return [{"error": f"Erro ao processar XML: {str(e)}"}]
