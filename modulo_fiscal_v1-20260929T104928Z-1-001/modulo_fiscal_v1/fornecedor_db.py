"""Cadastro de fornecedores multiempresa do Catraca Fiscal.

- Hikari Construções original: preserva o cadastro XLS/XLSX já existente.
- H K Engenharia, IRKA e Consórcios: usam fornecedores_empresas.json.
- A empresa ativa é obtida de contas_db.get_empresa_ativa().
"""
import os
import re
import json
import unicodedata
import pandas as pd
from typing import Optional

import contas_db

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_EXEMPLO_DIR = os.path.join(_BASE_DIR, "..", "exemplo conf")
_DATA_DIR = os.path.join(_BASE_DIR, "data")

_FORNECEDORES_JSON = os.path.join(_BASE_DIR, "fornecedores_empresas.json")
_FORNECEDORES_XLS = os.path.join(_EXEMPLO_DIR, "fornecedores.xls")
_LOTE_HIKARI_XLSX = os.path.join(_EXEMPLO_DIR, "lote hikari custos 08.xlsx")
_FORNECEDORES_XLS_DATA = os.path.join(_DATA_DIR, "fornecedores.xls")

_df_cache: dict[str, pd.DataFrame] = {}
_index_cache: dict[str, dict] = {}


def _normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = t.encode("ascii", "ignore").decode("ascii").lower().strip()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _empresa_ativa() -> str:
    try:
        return contas_db.get_empresa_ativa()
    except Exception:
        return "hikari_construcoes_original"


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["codigo_contabil", "classificacao", "nome_fornecedor"]
    )


def _padronizar_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_df()

    df = df.copy()

    if "classificacao" not in df.columns:
        df["classificacao"] = ""

    df = df[["codigo_contabil", "classificacao", "nome_fornecedor"]]

    df["codigo_contabil"] = pd.to_numeric(
        df["codigo_contabil"], errors="coerce"
    )
    df = df.dropna(subset=["codigo_contabil", "nome_fornecedor"])
    df["codigo_contabil"] = df["codigo_contabil"].astype(int)
    df["classificacao"] = df["classificacao"].fillna("").astype(str).str.strip()
    df["nome_fornecedor"] = (
        df["nome_fornecedor"].fillna("").astype(str).str.strip()
    )
    df = df[df["nome_fornecedor"] != ""]

    return df.reset_index(drop=True)


def _load_hikari_original() -> pd.DataFrame:
    """Mantém o comportamento anterior para a Hikari Construções original."""

    try:
        df = pd.read_excel(
            _LOTE_HIKARI_XLSX,
            sheet_name="Fornecedores",
            header=None,
            usecols=[0, 1],
        )
        df.columns = ["codigo_contabil", "nome_fornecedor"]
        df["classificacao"] = ""
        return _padronizar_df(df)
    except Exception:
        pass

    for caminho in (_FORNECEDORES_XLS, _FORNECEDORES_XLS_DATA):
        try:
            df = pd.read_excel(caminho, header=None, usecols=[0, 1])
            df.columns = ["codigo_contabil", "nome_fornecedor"]
            df["classificacao"] = ""
            return _padronizar_df(df)
        except Exception:
            continue

    return _empty_df()


def _load_multiempresa(empresa_slug: str) -> pd.DataFrame:
    try:
        with open(_FORNECEDORES_JSON, "r", encoding="utf-8") as f:
            dados = json.load(f)

        registros = dados.get("empresas", {}).get(empresa_slug, [])
        if not registros:
            return _empty_df()

        return _padronizar_df(pd.DataFrame(registros))
    except Exception:
        return _empty_df()


def _load_df(empresa_slug: Optional[str] = None) -> pd.DataFrame:
    empresa_slug = empresa_slug or _empresa_ativa()

    if empresa_slug == "hikari_construcoes_original":
        return _load_hikari_original()

    return _load_multiempresa(empresa_slug)


def _build_index(df: pd.DataFrame) -> dict:
    index = {}

    for _, row in df.iterrows():
        key = _normalize(str(row["nome_fornecedor"]))
        if not key:
            continue

        registro = {
            "codigo_contabil": int(row["codigo_contabil"]),
            "nome_original": str(row["nome_fornecedor"]).strip(),
            "classificacao": str(row.get("classificacao", "") or "").strip(),
        }

        # Se houver nomes idênticos no plano, preserva o primeiro cadastro.
        # O match exato por CNPJ não existe no plano fornecido; portanto não
        # sobrescrevemos silenciosamente um fornecedor homônimo.
        if key not in index:
            index[key] = registro

    return index


def load_fornecedores(
    force_reload: bool = False,
    empresa_slug: Optional[str] = None,
) -> pd.DataFrame:
    empresa_slug = empresa_slug or _empresa_ativa()

    if force_reload or empresa_slug not in _df_cache:
        _df_cache[empresa_slug] = _load_df(empresa_slug)

    return _df_cache[empresa_slug]


def get_index(
    force_reload: bool = False,
    empresa_slug: Optional[str] = None,
) -> dict:
    empresa_slug = empresa_slug or _empresa_ativa()

    if force_reload or empresa_slug not in _index_cache:
        df = load_fornecedores(
            force_reload=force_reload,
            empresa_slug=empresa_slug,
        )
        _index_cache[empresa_slug] = _build_index(df)

    return _index_cache[empresa_slug]


def lookup_fornecedor_por_nome(
    nome_emitente: str,
    threshold: float = 0.55,
    empresa_slug: Optional[str] = None,
) -> Optional[dict]:
    """Busca o fornecedor somente no plano da empresa ativa."""

    if not nome_emitente:
        return None

    empresa_slug = empresa_slug or _empresa_ativa()
    index = get_index(empresa_slug=empresa_slug)
    query = _normalize(nome_emitente)

    if not query:
        return None

    # 1) Match exato.
    if query in index:
        return {
            **index[query],
            "score": 1.0,
            "empresa": empresa_slug,
        }

    # 2) Match por tokens: Jaccard + containment.
    query_tokens = {q for q in query.split() if len(q) > 2}
    best_match = None
    best_score = 0.0

    for key, value in index.items():
        key_tokens = {k for k in key.split() if len(k) > 2}

        if not query_tokens or not key_tokens:
            continue

        intersection = query_tokens & key_tokens
        union = query_tokens | key_tokens

        jaccard = len(intersection) / len(union) if union else 0.0
        smaller = min(len(query_tokens), len(key_tokens))
        containment = len(intersection) / smaller if smaller else 0.0
        score = max(jaccard, containment * 0.85)

        if score > best_score and score >= threshold:
            best_score = score
            best_match = {
                **value,
                "score": round(score, 3),
                "empresa": empresa_slug,
            }

    return best_match


def get_all_fornecedores(
    empresa_slug: Optional[str] = None,
) -> list:
    df = load_fornecedores(empresa_slug=empresa_slug)
    return df.to_dict("records")


def reload(empresa_slug: Optional[str] = None):
    """Limpa o cache da empresa informada ou de todas as empresas."""

    if empresa_slug:
        _df_cache.pop(empresa_slug, None)
        _index_cache.pop(empresa_slug, None)
        return load_fornecedores(
            force_reload=True,
            empresa_slug=empresa_slug,
        )

    _df_cache.clear()
    _index_cache.clear()
    return load_fornecedores(force_reload=True)
