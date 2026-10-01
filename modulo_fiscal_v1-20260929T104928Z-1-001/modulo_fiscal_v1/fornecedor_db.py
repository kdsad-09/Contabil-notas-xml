"""
fornecedor_db.py — Hikari Construcoes
Le a planilha de fornecedores (xls/xlsx) e indexa por nome normalizado.
Match feito por nome do emitente buscando similaridade com razao social.

Formato esperado (lote hikari custos 08.xlsx, aba Fornecedores):
  Col 0: codigo_contabil  (ex: 505, 512, ...)
  Col 1: nome_fornecedor  (ex: "MUNDO DOS FERROS DIST...")
"""
import re
import os
import pandas as pd
from typing import Optional

_BASE_DIR = os.path.dirname(__file__)
_EXEMPLO_DIR = os.path.join(_BASE_DIR, "..", "exemplo conf")

_FORNECEDORES_XLS = os.path.join(_EXEMPLO_DIR, "fornecedores.xls")
_LOTE_HIKARI_XLSX = os.path.join(_EXEMPLO_DIR, "lote hikari custos 08.xlsx")


def _normalize(text: str) -> str:
    if not text:
        return ""
    t = str(text).lower().strip()
    for a, b in [("a","a"),("a","a"),("a","a"),("a","a"),
                 ("e","e"),("e","e"),("i","i"),("o","o"),
                 ("o","o"),("o","o"),("u","u"),("c","c")]:
        pass  # mantido por compatibilidade de logica
    replacements = [
        ("\xe1","a"),("\xe0","a"),("\xe2","a"),("\xe3","a"),
        ("\xe9","e"),("\xea","e"),("\xed","i"),("\xf3","o"),
        ("\xf4","o"),("\xf5","o"),("\xfa","u"),("\xe7","c"),
    ]
    for a, b in replacements:
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _load_df() -> pd.DataFrame:
    # Tenta lote hikari primeiro (xlsx sem xlrd)
    try:
        df = pd.read_excel(_LOTE_HIKARI_XLSX, sheet_name="Fornecedores", header=None)
        df.columns = ["codigo_contabil", "nome_fornecedor"]
        df = df[df["codigo_contabil"].apply(lambda x: str(x).strip().isdigit())]
        df["codigo_contabil"] = df["codigo_contabil"].astype(int)
        df["nome_fornecedor"] = df["nome_fornecedor"].astype(str).str.strip()
        return df
    except Exception:
        pass
    # Fallback: fornecedores.xls
    try:
        df = pd.read_excel(_FORNECEDORES_XLS, header=None)
        df.columns = ["codigo_contabil", "nome_fornecedor"]
        df = df[df["codigo_contabil"].apply(lambda x: str(x).strip().isdigit())]
        df["codigo_contabil"] = df["codigo_contabil"].astype(int)
        df["nome_fornecedor"] = df["nome_fornecedor"].astype(str).str.strip()
        return df
    except Exception:
        pass
    return pd.DataFrame(columns=["codigo_contabil", "nome_fornecedor"])


_df_cache: Optional[pd.DataFrame] = None
_index_cache: dict = {}


def _build_index(df: pd.DataFrame) -> dict:
    index = {}
    for _, row in df.iterrows():
        key = _normalize(str(row["nome_fornecedor"]))
        if key:
            index[key] = {
                "codigo_contabil": int(row["codigo_contabil"]),
                "nome_original": str(row["nome_fornecedor"]).strip(),
            }
    return index


def load_fornecedores(force_reload: bool = False) -> pd.DataFrame:
    global _df_cache
    if _df_cache is None or force_reload:
        _df_cache = _load_df()
    return _df_cache


def get_index(force_reload: bool = False) -> dict:
    global _index_cache
    if not _index_cache or force_reload:
        df = load_fornecedores(force_reload)
        _index_cache = _build_index(df)
    return _index_cache


def lookup_fornecedor_por_nome(nome_emitente: str, threshold: float = 0.55) -> Optional[dict]:
    """
    Busca fornecedor pelo nome do emitente da NF.
    Retorna dict {codigo_contabil, nome_original, score} ou None.
    """
    if not nome_emitente:
        return None
    index = get_index()
    query = _normalize(nome_emitente)

    # Match exato
    if query in index:
        return {**index[query], "score": 1.0}

    # Match por tokens (Jaccard + containment)
    query_tokens = set(q for q in query.split() if len(q) > 2)
    best_match = None
    best_score = 0.0

    for key, value in index.items():
        key_tokens = set(k for k in key.split() if len(k) > 2)
        if not query_tokens or not key_tokens:
            continue
        intersection = query_tokens & key_tokens
        union = query_tokens | key_tokens
        jaccard = len(intersection) / len(union) if union else 0
        smaller = min(len(query_tokens), len(key_tokens))
        containment = len(intersection) / smaller if smaller else 0
        score = max(jaccard, containment * 0.85)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = {**value, "score": round(score, 3)}

    return best_match


def get_all_fornecedores() -> list:
    df = load_fornecedores()
    return df.to_dict("records")


def reload():
    load_fornecedores(force_reload=True)
    get_index(force_reload=True)
