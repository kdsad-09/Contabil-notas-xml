"""
dominio_exporter.py — Exportacao para o formato oficial do Dominio Contabil
Gera a planilha identica ao modelo 'Lancamentos Contabeis (Partidas Simples.Multiplas)(3.1).xlsm'
Aba 'Plan1':
  Linha 5 (cabecalho):
    Col A: Data
    Col B: Cod. Conta Debito
    Col C: Cod. Conta Credito
    Col D: Valor
    Col E: Cod. Historico
    Col F: Complemento Historico
    Col G: Inicia Lote
    Col H: codigo Matriz/Filial
    Col I: Centro de Custo Debito
    Col J: Centro de Custo Credito

Regras contabeis:
  - Para Notas de Entrada (custos de obra):
      Debito:  Codigo da Categoria/Obra (ex: 1021, 913, 277)
      Credito: Codigo Contabil do Fornecedor (ex: 512, 516, etc.) ou fallback (5 = Fornecedores diversos)
      Complemento Historico: "COMPRAS DE MERCADORIAS NESTA DATA NF {nNF} {nome_fornecedor}"
  - Para Notas de Retorno / Devolucao:
      Debito:  Codigo do Fornecedor (ou 5)
      Credito: Codigo de Devolucao de Custos (ou Categoria)
      Complemento Historico: "DEVOLUCAO DE COMPRAS NF {nNF}"
"""
import io
import datetime
import pandas as pd
from typing import Optional

try:
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    _OPENPYXL = True
except ImportError:
    _OPENPYXL = False


import contas_db

def build_dominio_dataframe(invoices: list, categories: dict, obras: dict,
                            codigos: dict, approvals: dict,
                            fornecedores_map: Optional[dict] = None) -> pd.DataFrame:
    """
    Constroi o DataFrame formatado exatamente como a aba Plan1 do Dominio.
    """
    fornecedores_map = fornecedores_map or {}
    rows = []

    for doc in invoices:
        uid = doc.get("uid", "")
        # Apenas notas aprovadas (ou pendentes se aprovadas nao forem filtradas)
        status = approvals.get(uid, "Pendente") if approvals else "Pendente"
        if status == "Rejeitado":
            continue

        tipo_nf = doc.get("tipo_nf_classificado", "Entrada")
        obra_val = obras.get(uid, doc.get("obra_sugerida", "CUSTO DA OBRA GERAL"))
        cat_val = categories.get(uid, doc.get("categoria", "DESPESAS COM MATERIAL DIVERSOS"))

        cod_debito_str = str(codigos.get(uid, "")).replace("~", "").strip()
        if cod_debito_str.isdigit():
            cod_debito = int(cod_debito_str)
        else:
            resolved_cod = contas_db.get_codigo_para_obra_e_categoria(obra_val, cat_val)
            cod_debito = int(resolved_cod) if resolved_cod else 1027

        # Regra da Conta Credito:
        # Se for pagamento À VISTA (dinheiro, pix, debito ou sem parcelas a prazo): Conta 5 (Caixa)
        # Se for a prazo / com parcelas: usa o codigo contábil do fornecedor cadastrado (ou 5 como fallback)
        fornec_info = fornecedores_map.get(uid, {})
        cod_fornecedor = fornec_info.get("codigo_contabil") if isinstance(fornec_info, dict) else None
        is_a_vista = doc.get("is_a_vista", False)

        if is_a_vista:
            cod_credito = 5  # Conta 5 Caixa / Pagamento à vista
        else:
            cod_credito = cod_fornecedor if cod_fornecedor else 5

        dt_str = doc.get("data_emissao", "")
        try:
            dt = datetime.datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
        except Exception:
            dt = dt_str

        # Se houver parcelas, exporta cada parcela com seu vencimento e valor
        parcelas = doc.get("parcelas", [])
        if not parcelas:
            parcelas = [{
                "nDup": "1",
                "dVenc": doc.get("data_emissao"),
                "vDup": doc.get("valor_total", 0.0)
            }]

        for p in parcelas:
            val = float(p.get("vDup", 0.0) or 0.0)
            if val <= 0:
                continue

            n_nf = doc.get("nNF", "")
            fornec_nome = doc.get("fornecedor", "")
            cfop_tag = f" CFOP {doc['cfop_destaque']}" if doc.get("cfop_destaque") else ""

            if tipo_nf == "Retorno/Devolucao":
                # Inverte debito e credito
                d_acc = cod_credito
                c_acc = cod_debito or 467
                compl = f"DEVOLUCAO DE COMPRAS NF {n_nf}{cfop_tag} - {fornec_nome}"
            else:
                d_acc = cod_debito
                c_acc = cod_credito
                compl = f"COMPRAS DE MERCADORIAS NESTA DATA NF {n_nf}{cfop_tag} - {fornec_nome}"

            rows.append({
                "Data": dt,
                "Cod. Conta Debito": d_acc,
                "Cod. Conta Credito": c_acc,
                "Valor": val,
                "Cod. Historico": "",
                "Complemento Historico": compl,
                "Inicia Lote": "",
                "codigo Matriz/Filial": 1,
                "Centro de Custo Debito": "",
                "Centro de Custo Credito": "",
                "NF": n_nf,
                "Fornecedor": fornec_nome,
                "Obra": obras.get(uid, ""),
                "Categoria": categories.get(uid, ""),
            })

    return pd.DataFrame(rows)


def export_to_dominio_excel(invoices: list, categories: dict, obras: dict,
                            codigos: dict, approvals: dict,
                            fornecedores_map: Optional[dict] = None) -> io.BytesIO:
    """
    Gera arquivo Excel (.xlsx) compativel com o layout de importacao do Dominio.
    """
    df_data = build_dominio_dataframe(
        invoices, categories, obras, codigos, approvals, fornecedores_map
    )

    output = io.BytesIO()

    if not _OPENPYXL:
        # Fallback simples via pandas
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_data.to_excel(writer, sheet_name="Plan1", index=False)
        output.seek(0)
        return output

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Plan1"

    # Cabecalhos de orientacao Dominio (linhas 1-4)
    ws.cell(row=2, column=7, value="Pasta onde o arquivo 'entradas.txt' sera salvo (pode ser alterada):")
    ws.cell(row=3, column=7, value="C:\\Dominio\\Importacao")

    # Linha 5: Cabecalho oficial
    headers = [
        "Data",
        "Cod. Conta Debito",
        "Cod. Conta Credito",
        "Valor",
        "Cod. Historico",
        "Complemento Historico",
        "Inicia Lote",
        "codigo Matriz/Filial",
        "Centro de Custo Debito",
        "Centro de Custo Credito",
        "NF",
        "Fornecedor",
        "Obra",
        "Categoria"
    ]

    header_fill = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")

    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=5, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Linhas de dados a partir da linha 6
    row_idx = 6
    for _, row in df_data.iterrows():
        ws.cell(row=row_idx, column=1, value=row["Data"]).number_format = "yyyy-mm-dd"
        ws.cell(row=row_idx, column=2, value=row["Cod. Conta Debito"])
        ws.cell(row=row_idx, column=3, value=row["Cod. Conta Credito"])
        cell_val = ws.cell(row=row_idx, column=4, value=row["Valor"])
        cell_val.number_format = "#,##0.00"
        ws.cell(row=row_idx, column=5, value="")
        ws.cell(row=row_idx, column=6, value=row["Complemento Historico"])
        ws.cell(row=row_idx, column=7, value="")
        ws.cell(row=row_idx, column=8, value=row["codigo Matriz/Filial"])
        ws.cell(row=row_idx, column=9, value="")
        ws.cell(row=row_idx, column=10, value="")
        ws.cell(row=row_idx, column=11, value=row["NF"])
        ws.cell(row=row_idx, column=12, value=row["Fornecedor"])
        ws.cell(row=row_idx, column=13, value=row["Obra"])
        ws.cell(row=row_idx, column=14, value=row["Categoria"])
        row_idx += 1

    # Auto largura de colunas
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            if cell.row >= 5 and cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    wb.save(output)
    output.seek(0)
    return output
