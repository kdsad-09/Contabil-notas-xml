"""
ai_classifier.py — Gemini AI integration for NF-e classification.
Configured with Hikari Construções' actual expense codes and obra centers.
"""
import json
import re
import os
from typing import List, Dict, Optional, Any

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# Hikari expense sub-codes (within each obra center)
HIKARI_DESPESAS = [
    "DESPESAS COM COMBUSTIVEIS E LUBRIFICANTES",
    "DESPESAS COM CIMENTO CAL FERRO ARAME",
    "DESPESAS COM MATERIAL ELETRICO",
    "DESPESAS COM AREIA BRITA E SEIXO",
    "DESPESAS COM MADEIRA",
    "DESPESAS COM TINTAS E VERNIZACAO",
    "DESPESAS COM FERRAMENTAS",
    "DESPESAS COM TIJOLOS",
    "DESPESAS COM MATERIAL DIVERSOS",
    "DESPESAS COM PRODUTOS DE LIMPEZA",
    "DESPESAS COM LOCACAO DE MAQUINAS E EQUIPAMENTOS",
    "DESPESAS COM REVESTIMENTOS E ACABAMENTOS",
    "DESPESAS COM SERVICOS DE TERCEIRO",
    "DESPESAS COM MATERIAL HIDRAULICO",
    "DESPESAS COM TELHAS",
    "DESPESAS COM ALIMENTACAO",
    "DESPESAS COM PISOS EM GERAL",
]

# Hikari obra centers from balancete
HIKARI_OBRAS = [
    "CETEC SENAI ARAGUAINA",
    "ANFITEATRO SESI ARAGUAINA",
    "SEDE SESI SENAI PALMAS-TO",
    "ETI TAQUARI",
    "ETI PORTO LUZIMANGUES",
    "SESI DR GURUPI",
    "BLOCO IFTO ARAGUAINA",
    "REFORMA DUQUE DE CAXIAS II",
    "AMPLIACAO SEDE CREA PALMAS",
    "CICLOVIA CESAMAR",
    "CENTRO DE CONVENCOES PARAISO",
    "CENTRO DE ATENDIMENTO SOCIOEDUCATIVO DE ARAGUAINA",
    "GUARITA SENAI CT GURUPI",
]

SYSTEM_PROMPT = """Você é um assistente contábil da empresa HIKARI CONSTRUÇÕES LTDA EPP (CNPJ 14.193.573/0001-93).
Sua tarefa é analisar notas fiscais (NF-e) e classificar cada uma usando o plano de contas oficial da empresa.

## CATEGORIAS DE DESPESA (obrigatórias, use EXATAMENTE estes nomes):
{categorias}

Se nenhuma se aplica, use "DESPESAS COM MATERIAL DIVERSOS".

## CENTROS DE CUSTO / OBRAS (use se identificar a obra):
{obras}

## REGRAS:
1. Classifique a CATEGORIA baseado nos itens, NCM e descrição dos produtos
2. Identifique a OBRA baseado nas informações complementares (infAdic/infCompl):
   - Procure o número CNO (Cadastro Nacional de Obras)
   - Procure nomes de obras conhecidas da Hikari
   - Se NÃO identificar a obra, use "CUSTO DA OBRA GERAL"
3. Justifique brevemente cada classificação

RESPONDA EXCLUSIVAMENTE em JSON válido, com a seguinte estrutura exata:

{{
  "classificacoes": [
    {{
      "nf": "NUMERO_DA_NF",
      "categoria": "DESPESAS COM ...",
      "motivo_categoria": "Justificativa baseada nos itens",
      "obra_sugerida": "NOME_DA_OBRA ou CUSTO DA OBRA GERAL",
      "cno_identificado": "NUMERO_CNO ou null",
      "motivo_obra": "Como identificou a obra"
    }}
  ]
}}
"""

def _build_invoice_summary(invoices):
    """Build concise text summary of all invoices for the AI prompt."""
    lines = []
    for inv in invoices:
        nf = inv.get("nNF", "?")
        forn = inv.get("fornecedor", "?")
        val = inv.get("valor_formatted", "?")
        items_desc = []
        for it in inv.get("itens", [])[:10]:
            desc = it.get("descricao", "")
            ncm = it.get("ncm", "")
            vt = it.get("valor_total", "")
            items_desc.append(f"  - {desc} (NCM:{ncm}, R${vt})")
        items_str = "\n".join(items_desc) if items_desc else "  (sem itens)"

        inf_adic = inv.get("infAdic", "") or ""
        inf_fisco = inv.get("infAdFisco", "") or ""
        info = inf_adic
        if inf_fisco:
            info += f" | InfAdFisco: {inf_fisco}"

        lines.append(
            f"--- NF {nf} ---\n"
            f"Fornecedor: {forn}\n"
            f"Valor: {val}\n"
            f"Itens:\n{items_str}\n"
            f"Info Adicional: {info[:500]}\n"
        )
    return "\n".join(lines)

def classify_batch(invoices, api_key, model_name="gemini-1.5-flash"):
    """
    Classifies a batch of invoices using Google Gemini API.
    """
    if not HAS_GEMINI or not api_key or not invoices:
        return None

    try:
        # Clean API key to remove artifacts
        api_key = re.sub(r'[^a-zA-Z0-9\-_]', '', api_key)
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"response_mime_type": "application/json"}
        )

        cat_list = "\n".join(f"   - {c}" for c in HIKARI_DESPESAS)
        obra_list = "\n".join(f"   - {o}" for o in HIKARI_OBRAS)
        
        system_instructions = SYSTEM_PROMPT.format(categorias=cat_list, obras=obra_list)
        invoice_text = _build_invoice_summary(invoices)
        
        full_prompt = f"{system_instructions}\n\nNotas fiscais para classificar:\n\n{invoice_text}"

        response = model.generate_content(full_prompt)
        text = response.text.strip()
        
        # Clean text if wrapped in quotes/code blocks
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        parsed = json.loads(text)
        results = []
        if isinstance(parsed, dict):
            if "classificacoes" in parsed:
                results = parsed["classificacoes"]
            else:
                results = [parsed]
        elif isinstance(parsed, list):
            results = parsed

        classified = {}
        for item in results:
            nf = str(item.get("nf", ""))
            if not nf: continue
            classified[nf] = {
                "categoria": item.get("categoria", "DESPESAS COM MATERIAL DIVERSOS"),
                "motivo_categoria": item.get("motivo_categoria", ""),
                "obra_sugerida": item.get("obra_sugerida", "CUSTO DA OBRA GERAL"),
                "cno_identificado": item.get("cno_identificado"),
                "motivo_obra": item.get("motivo_obra", ""),
            }
        return classified

    except Exception as e:
        return {"_error": str(e)}

def is_available():
    """Check if the google-generativeai package is installed."""
    return HAS_GEMINI
