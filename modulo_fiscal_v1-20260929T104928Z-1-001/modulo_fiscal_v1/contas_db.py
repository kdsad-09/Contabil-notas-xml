"""Plano de contas multiempresa do Catraca Fiscal.
Dados consolidados dos planos oficiais fornecidos pelo usuário.
A empresa ativa é definida por set_empresa() no app.py.
"""
import json, os, re, unicodedata
from typing import Optional, List, Dict, Any

_BASE_DIR=os.path.dirname(os.path.abspath(__file__))
_DATA_FILE=os.path.join(_BASE_DIR,'planos_empresas.json')
_EMPRESA_ATIVA='irka'

def _load_all():
    with open(_DATA_FILE,'r',encoding='utf-8') as f: return json.load(f)['empresas']

def get_empresas():
    return _load_all()

def get_empresa_options():
    return {v['nome']:k for k,v in _load_all().items()}

def set_empresa(empresa_slug:str):
    global _EMPRESA_ATIVA
    if empresa_slug in _load_all(): _EMPRESA_ATIVA=empresa_slug
    return _EMPRESA_ATIVA

def get_empresa_ativa(): return _EMPRESA_ATIVA

def get_empresa_info(): return _load_all()[_EMPRESA_ATIVA]

def clean_cno_digits(cno): return re.sub(r'\D','',str(cno or ''))

def format_cno(cno):
    d=clean_cno_digits(cno)
    return f'{d[:2]}.{d[2:5]}.{d[5:10]}/{d[10:]}' if len(d)==12 else (str(cno).strip() if cno else None)

def _norm(s):
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def _tokens(s):
    stop={'com','para','dos','das','de','em','por','que','despesas','despesa','material','materiais','aplicado','obra','custo','custos'}
    aliases={'hidraulico':'encanamento','hidraulicos':'encanamento','canos':'encanamento','cano':'encanamento','encanamentos':'encanamento',
             'ferros':'ferro','ferragens':'ferro','ferragem':'ferro','eletricos':'eletrico','madeiras':'madeira',
             'pisos':'piso','telhas':'telha','tijolos':'tijolo','combustiveis':'combustivel','lubrificantes':'lubrificante'}
    out=set()
    for x in _norm(s).split():
        if len(x)<3 or x in stop: continue
        out.add(aliases.get(x,x))
    return out

def load_plano(force_reload=False):
    info=get_empresa_info(); obras=info.get('obras',[])
    geral=next((o for o in obras if 'GERAL' in o.get('nome_display','').upper()), obras[0] if obras else None)
    especificas=[o for o in obras if o is not geral and 'MÃO-DE-OBRA' not in o.get('nome_display','').upper()]
    return {'empresa':_EMPRESA_ATIVA,'empresa_nome':info['nome'],'cnpj':info['cnpj'],'obra_geral':geral,'obras':especificas,'todas_obras':obras,'source_file':_DATA_FILE}

def get_all_obras():
    return load_plano().get('todas_obras',[])

def get_obra_geral(): return load_plano().get('obra_geral')

def get_obra_geral_label():
    o=get_obra_geral(); return o.get('dropdown_label') if o else 'CUSTO OBRA GERAL'

def get_obra_names_for_dropdown():
    return [o['dropdown_label'] for o in get_all_obras() if o.get('dropdown_label') and 'MÃO-DE-OBRA' not in o.get('nome_display','').upper()]

def lookup_obra_por_cno(cno):
    d=clean_cno_digits(cno)
    if not d: return None
    for o in get_all_obras():
        od=o.get('cno_digits') or clean_cno_digits(o.get('cno'))
        if od and (d==od or (len(d)>=8 and d in od) or (len(od)>=8 and od in d)): return o
    return None

def get_obra_by_identifier(identifier):
    if not identifier: return None
    s=str(identifier).strip(); n=_norm(s); digits=clean_cno_digits(s)
    for o in get_all_obras():
        if s==o.get('dropdown_label') or n==_norm(o.get('nome_display')) or s==str(o.get('codigo')) or s==o.get('classificacao'): return o
    if len(digits)>=8:
        for o in get_all_obras():
            od=o.get('cno_digits','')
            if od and (digits in od or od in digits): return o
    for o in get_all_obras():
        on=_norm(o.get('nome_display'))
        if on and (on in n or n in on): return o
    return None

def get_subclasses_for_obra(obra_ident):
    o=get_obra_by_identifier(obra_ident) or get_obra_geral()
    return sorted(list((o or {}).get('categorias',{}).values()), key=lambda x:x.get('nome',''))

def _find_cat(o,nome_categoria):
    if not o: return None
    cats=o.get('categorias',{})
    nk=_norm(nome_categoria); nt=_tokens(nome_categoria)
    best=None; score=-1
    for v in cats.values():
        vn=_norm(v.get('nome'))
        if vn==nk: return v
        vt=_tokens(v.get('nome')); common=len(nt & vt)
        # penaliza categorias semanticamente opostas frequentes
        if common>score: score=common; best=v
    return best if score>=1 else None

def get_codigo_info_para_obra_e_categoria(obra_ident,nome_categoria):
    target=get_obra_by_identifier(obra_ident) or get_obra_geral(); res=_find_cat(target,nome_categoria); fallback=False
    if not res:
        geral=get_obra_geral()
        if geral and geral is not target:
            res=_find_cat(geral,nome_categoria); fallback=bool(res)
    o=get_obra_geral() if fallback else target
    if res:
        return {'codigo':res['codigo'],'classificacao':res['classificacao'],'nome_categoria':res.get('nome',nome_categoria),'label_subclasse':f"{res.get('nome',nome_categoria)} — Cód. {res['codigo']} ({res['classificacao']})",'obra_codigo':o.get('codigo'),'obra_classificacao':o.get('classificacao'),'obra_nome':o.get('nome_display'),'cno':o.get('cno'),'is_fallback':fallback,'empresa':_EMPRESA_ATIVA}
    return {'codigo':None,'classificacao':'','nome_categoria':str(nome_categoria or '').upper(),'label_subclasse':str(nome_categoria or '').upper(),'obra_codigo':target.get('codigo') if target else None,'obra_classificacao':target.get('classificacao') if target else '','obra_nome':target.get('nome_display') if target else '','cno':target.get('cno') if target else None,'is_fallback':False,'empresa':_EMPRESA_ATIVA}

def get_codigo_para_obra_e_categoria(nome_obra_display,nome_categoria):
    return get_codigo_info_para_obra_e_categoria(nome_obra_display,nome_categoria).get('codigo')

def reload(): return load_plano(True)
