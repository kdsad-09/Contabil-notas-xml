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
