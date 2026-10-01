"""
contas_db.py — Hikari Construções LTDA EPP
Plano de Contas Oficial (Contas.xlsx - Domínio Contábil):
  - Segmento / Obras (Grau 4, classificação 3.1.1.XX) com Código, Classificação e CNO
  - Subclasses / Despesas Analíticas (Grau 5, classificação 3.1.1.XX.YYY) com Código e Classificação

Estrutura do Contas.xlsx:
  Col A (0):  Código da conta (ex: 271, 273, 1022, 277...)
  Col D (3):  Tipo (S = Sintética, vazio = Analítica)
  Col H (7):  Classificação (ex: 3.1.1, 3.1.1.01, 3.1.1.02, 3.1.1.02.001...)
  Col L-R:    Nome da conta
  Col V/W:    Grau (1.0, 2.0, 3.0, 4.0, 5.0)
"""
import re
import os
import json
import pandas as pd
from typing import Optional, List, Dict, Any

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_BASE_DIR, "contas_cache.json")

# Candidatos a caminho do Contas.xlsx
_CONTAS_CANDIDATES = [
    os.path.join(_BASE_DIR, "data", "Contas.xlsx"),
    os.path.join(_BASE_DIR, "Contas.xlsx"),
    os.path.join(_BASE_DIR, "..", "exemplo conf", "Contas.xlsx"),
    os.path.join(_BASE_DIR, "..", "drive-download-20260929T105212Z-1-001", "Contas.xlsx"),
    os.path.join(_BASE_DIR, "..", "Contas.xlsx"),
]

# Regex para CNO (XX.XXX.XXXXX/XX ou com dígitos)
_CNO_RE = re.compile(r"(?:cno\s*[:\-\/]?\s*)?(\d{2}\.\d{3}\.\d{5}/\d{2})", re.IGNORECASE)


def _find_contas_path() -> Optional[str]:
    for p in _CONTAS_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def clean_cno_digits(cno: Optional[str]) -> str:
    """Retorna apenas dígitos do CNO (12 dígitos)."""
    if not cno:
        return ""
    return re.sub(r"\D", "", str(cno))


def format_cno(cno: Optional[str]) -> Optional[str]:
    """Formata CNO como XX.XXX.XXXXX/XX."""
    digits = clean_cno_digits(cno)
    if len(digits) == 12:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:10]}/{digits[10:]}"
    return str(cno).strip() if cno else None


def _extract_cno(nome: str) -> Optional[str]:
    """Extrai CNO formatado do nome da conta."""
    m = _CNO_RE.search(str(nome))
    if m:
        return format_cno(m.group(1))
    # Tenta achar 12 dígitos consecutivos
    m2 = re.search(r"(\d{2}[\.\s]?\d{3}[\.\s]?\d{5}[\.\/\s]?\d{2})", str(nome))
    if m2:
        d = re.sub(r"\D", "", m2.group(1))
        if len(d) == 12:
            return format_cno(d)
    return None


def _clean_nome(nome: str) -> str:
    """Remove trecho de CNO e pontuações do final do nome da obra."""
    cleaned = re.sub(r"(?:cno\s*[:\-\/]?\s*)?(\d{2}\.\d{3}\.\d{5}/\d{2})", "", str(nome), flags=re.IGNORECASE)
    cleaned = re.sub(r"[\/\-\s]+$", "", cleaned).strip()
    return cleaned


def _clean_tokens(text: str) -> set:
    """Extrai conjunto de tokens normalizados (sem acentos/pontuação)."""
    t = str(text).lower()
    for a, b in [("á","a"),("à","a"),("â","a"),("ã","a"),("é","e"),("ê","e"),
                 ("í","i"),("ó","o"),("ô","o"),("õ","o"),("ú","u"),("ç","c")]:
        t = t.replace(a, b)
    words = re.findall(r"[a-z0-9]+", t)
    stop = {"com", "para", "dos", "das", "de", "em", "por", "que", "despesas", "despesa", "material", "materiais"}
    return {w for w in words if w not in stop and len(w) >= 3}


def _parse_excel(xlsx_path: str) -> dict:
    """Lê Contas.xlsx e compila a estrutura hierárquica completa."""
    try:
        df = pd.read_excel(xlsx_path, sheet_name="Contas", header=None, engine="openpyxl")
    except Exception as e:
        return {"obras": [], "obra_geral": None, "error": str(e)}

    obras = []
    obra_atual = None
    obra_geral = None

    for _, row in df.iterrows():
        try:
            # Grau pode estar na coluna 21 (V) ou 22 (W)
            grau = None
            if len(row) > 21 and pd.notna(row.iloc[21]):
                try:
                    grau = int(float(str(row.iloc[21]).strip()))
                except Exception:
                    pass
            if grau is None and len(row) > 22 and pd.notna(row.iloc[22]):
                try:
                    grau = int(float(str(row.iloc[22]).strip()))
                except Exception:
                    pass

            classif = str(row.iloc[7]).strip() if pd.notna(row.iloc[7]) else ""
            tipo = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""

            # Coleta o nome da conta em colunas 11 a 17
            nome_parts = []
            for col_idx in range(11, min(18, len(row))):
                v = row.iloc[col_idx]
                if pd.notna(v) and str(v).strip() not in ("", "nan"):
                    nome_parts.append(str(v).strip())
            nome = " ".join(nome_parts).strip()

            codigo = row.iloc[0]
            codigo_int = int(float(codigo)) if pd.notna(codigo) and str(codigo).strip().replace(".","").isdigit() else None

            # Grau 4 + 3.1.1. -> SEGMENTO / OBRA (Conta Sintética)
            if grau == 4 and classif.startswith("3.1.1."):
                cno_fmt = _extract_cno(nome)
                cno_dig = clean_cno_digits(cno_fmt)
                nome_disp = _clean_nome(nome)

                # Formata label para dropdown: Nome e Número (Código e Classificação) + CNO
                cno_tag = f" — CNO {cno_fmt}" if cno_fmt else ""
                dropdown_label = f"{nome_disp} — Cód. {codigo_int} ({classif}){cno_tag}"

                obra_atual = {
                    "codigo": codigo_int,
                    "classificacao": classif,
                    "nome_completo": nome,
                    "nome_display": nome_disp,
                    "cno": cno_fmt,
                    "cno_digits": cno_dig,
                    "dropdown_label": dropdown_label,
                    "categorias": {},
                }

                if "OBRA GERAL" in nome.upper() or classif == "3.1.1.01":
                    obra_geral = obra_atual
                else:
                    obras.append(obra_atual)

            # Grau 5 + 3.1.1. -> SUBCLASSE / CONTA ANALÍTICA (Despesa da obra atual)
            elif grau == 5 and obra_atual and classif.startswith("3.1.1."):
                if nome and codigo_int:
                    cat_key = nome.upper().strip()
                    subclasse_label = f"{cat_key} — Cód. {codigo_int} ({classif})"
                    obra_atual["categorias"][cat_key] = {
                        "codigo": codigo_int,
                        "classificacao": classif,
                        "nome": cat_key,
                        "label": subclasse_label,
                    }

        except (ValueError, TypeError):
            continue

    return {
        "obras": obras,
        "obra_geral": obra_geral,
        "source_file": xlsx_path,
    }


_plano_cache: Optional[dict] = None


def load_plano(force_reload: bool = False) -> dict:
    """Carrega o plano com cache em memória e em arquivo JSON para altíssima performance."""
    global _plano_cache
    if _plano_cache is not None and not force_reload:
        return _plano_cache

    # 1. Tenta carregar do cache JSON se válido
    contas_path = _find_contas_path()
    if not force_reload and os.path.exists(_CACHE_FILE):
        try:
            cache_mtime = os.path.getmtime(_CACHE_FILE)
            xlsx_mtime = os.path.getmtime(contas_path) if contas_path and os.path.exists(contas_path) else 0
            if cache_mtime >= xlsx_mtime:
                with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                    _plano_cache = json.load(f)
                    return _plano_cache
        except Exception:
            pass

    # 2. Se não há cache ou force_reload, faz o parse do Excel
    if not contas_path:
        # Se não achou Excel mas tem cache, usa o cache como fallback
        if os.path.exists(_CACHE_FILE):
            try:
                with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                    _plano_cache = json.load(f)
                    return _plano_cache
            except Exception:
                pass
        return {"obras": [], "obra_geral": None, "error": "Contas.xlsx não encontrado"}

    data = _parse_excel(contas_path)
    if not data.get("error"):
        try:
            with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    _plano_cache = data
    return _plano_cache


def get_all_obras() -> List[Dict[str, Any]]:
    """Retorna todas as obras (Obra Geral + obras específicas com CNO e suas subclasses)."""
    plano = load_plano()
    result = []
    if plano.get("obra_geral"):
        result.append(plano["obra_geral"])
    for o in plano.get("obras", []):
        result.append(o)
    return result


def get_obra_names_for_dropdown() -> List[str]:
    """
    Retorna strings formatadas no padrão:
    'NOME OBRA — Cód. XXX (3.1.1.XX) — CNO XX.XXX.XXXXX/XX'
    Apresenta nome e número da obra de forma clara.
    """
    obras = get_all_obras()
    return [o["dropdown_label"] for o in obras if o.get("dropdown_label")]


def lookup_obra_por_cno(cno: str) -> Optional[Dict[str, Any]]:
    """
    Busca obra pelo número de CNO com normalização total de dígitos.
    Compatível com formatos com e sem pontuação (ex: '900188329770' ou '90.018.83297/70').
    """
    if not cno:
        return None
    cno_digits = clean_cno_digits(cno)
    if not cno_digits:
        return None

    plano = load_plano()
    for obra in plano.get("obras", []):
        obra_cno_dig = obra.get("cno_digits") or clean_cno_digits(obra.get("cno"))
        if not obra_cno_dig:
            continue
        # Match exato de 12 dígitos ou continência
        if cno_digits == obra_cno_dig or (len(cno_digits) >= 8 and cno_digits in obra_cno_dig) or (len(obra_cno_dig) >= 8 and obra_cno_dig in cno_digits):
            return obra

    return plano.get("obra_geral")


def get_obra_by_identifier(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Identifica a obra por qualquer identificador:
    dropdown_label, nome_display, nome_completo, CNO, código ou classificação.
    """
    if not identifier:
        return None
    ident_str = str(identifier).strip()
    ident_up = ident_str.upper()
    ident_digits = clean_cno_digits(ident_str)

    obras = get_all_obras()

    # 1. Match exato por dropdown_label ou nome_display
    for o in obras:
        if ident_str == o.get("dropdown_label") or ident_up == o.get("nome_display", "").upper():
            return o

    # 2. Match por CNO (se tiver dígitos de CNO)
    if len(ident_digits) >= 8:
        for o in obras:
            if o.get("cno_digits") and ident_digits in o["cno_digits"]:
                return o

    # 3. Match por código da obra
    if ident_str.isdigit():
        cod_int = int(ident_str)
        for o in obras:
            if o.get("codigo") == cod_int:
                return o

    # 4. Match por classificação (ex: 3.1.1.02)
    for o in obras:
        if o.get("classificacao") == ident_str:
            return o

    # 5. Match parcial por nome
    for o in obras:
        if o.get("nome_display", "").upper() in ident_up or ident_up in o.get("nome_completo", "").upper():
            return o

    return None


def get_subclasses_for_obra(obra_ident: str) -> List[Dict[str, Any]]:
    """
    Retorna a lista de subclasses (contas analíticas de Grau 5) para a obra especificada.
    Se a obra não tiver categorias cadastradas, retorna as subclasses da Obra Geral.
    """
    obra = get_obra_by_identifier(obra_ident)
    if not obra or not obra.get("categorias"):
        plano = load_plano()
        obra = plano.get("obra_geral")

    if not obra:
        return []

    subclasses = list(obra.get("categorias", {}).values())
    subclasses.sort(key=lambda s: s.get("nome", ""))
    return subclasses


def get_codigo_info_para_obra_e_categoria(obra_ident: str, nome_categoria: str) -> Dict[str, Any]:
    """
    Retorna dicionário completo com os dados da conta analítica (subclasse):
      - codigo: Código contábil numérico (ex: 277)
      - classificacao: Classificação contábil (ex: 3.1.1.02.001)
      - nome_categoria: Nome da categoria/subclasse
      - label_subclasse: 'DESPESAS COM AREIA... — Cód. 277 (3.1.1.02.001)'
      - obra_codigo: Código da obra
      - obra_classificacao: Classificação da obra
      - obra_nome: Nome da obra
      - cno: CNO da obra (se houver)
      - is_fallback: True se a categoria foi pega da Obra Geral
    """
    plano = load_plano()
    target_obra = get_obra_by_identifier(obra_ident) or plano.get("obra_geral")
    cat_key = str(nome_categoria or "").strip().upper()
    cat_tokens = _clean_tokens(nome_categoria)

    # Função interna para buscar na obra
    def _find_in_obra(obra_dict):
        if not obra_dict or "categorias" not in obra_dict:
            return None
        cats = obra_dict["categorias"]
        # Match exato de chave
        if cat_key in cats:
            return cats[cat_key]
        # Match exato de chave simplificada
        for k, v in cats.items():
            if k.replace(";", "").replace(",", "") == cat_key.replace(";", "").replace(",", ""):
                return v
        # Match por maior sobreposição de tokens
        best_score = 0
        best_cat = None
        for k, v in cats.items():
            k_tokens = _clean_tokens(k)
            common = cat_tokens & k_tokens
            if len(common) > best_score:
                best_score = len(common)
                best_cat = v
        if best_cat and best_score >= 1:
            return best_cat
        return None

    # 1. Busca na obra alvo
    res = _find_in_obra(target_obra)
    is_fallback = False

    # 2. Fallback: Obra Geral se não encontrou na obra alvo
    if not res:
        og = plano.get("obra_geral")
        if og and og != target_obra:
            res = _find_in_obra(og)
            if res:
                is_fallback = True

    if res:
        o = target_obra if not is_fallback else plano.get("obra_geral", {})
        return {
            "codigo": res["codigo"],
            "classificacao": res["classificacao"],
            "nome_categoria": res.get("nome", cat_key),
            "label_subclasse": f"{res.get('nome', cat_key)} — Cód. {res['codigo']} ({res['classificacao']})",
            "obra_codigo": o.get("codigo"),
            "obra_classificacao": o.get("classificacao"),
            "obra_nome": o.get("nome_display"),
            "cno": o.get("cno"),
            "is_fallback": is_fallback,
        }

    # Se nada encontrado
    return {
        "codigo": None,
        "classificacao": "",
        "nome_categoria": cat_key,
        "label_subclasse": cat_key,
        "obra_codigo": target_obra.get("codigo") if target_obra else None,
        "obra_classificacao": target_obra.get("classificacao") if target_obra else "",
        "obra_nome": target_obra.get("nome_display") if target_obra else "",
        "cno": target_obra.get("cno") if target_obra else None,
        "is_fallback": False,
    }


def get_codigo_para_obra_e_categoria(nome_obra_display: str, nome_categoria: str) -> Optional[int]:
    """Retorna apenas o código inteiro da conta analítica (compatibilidade reversa)."""
    info = get_codigo_info_para_obra_e_categoria(nome_obra_display, nome_categoria)
    return info.get("codigo")


def reload():
    load_plano(force_reload=True)
