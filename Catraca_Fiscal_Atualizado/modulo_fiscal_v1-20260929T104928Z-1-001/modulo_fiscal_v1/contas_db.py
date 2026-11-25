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
        if len(d)==12 and d==od: return o
    return None

def get_obra_by_identifier(identifier):
    if not identifier: return None
    s=str(identifier).strip(); n=_norm(s); digits=clean_cno_digits(s)
    for o in get_all_obras():
        if s==o.get('dropdown_label') or n==_norm(o.get('nome_display')) or s==str(o.get('codigo')) or s==o.get('classificacao'): return o
    if len(digits)>=8:
        for o in get_all_obras():
            od=o.get('cno_digits','')
            if len(digits)==12 and digits==od: return o
    return None

def get_subclasses_for_obra(obra_ident):
    o=get_obra_by_identifier(obra_ident) or get_obra_geral()
    return sorted(list((o or {}).get('categorias',{}).values()), key=lambda x:x.get('nome',''))

def _familia(nome):
    n = _norm(nome)
    # Ordem é relevante quando o plano reúne vários materiais na mesma conta.
    grupos = [
      ('hidraulico', ('hidraul', 'encanamento', 'canos')),
      ('eletrico', ('eletric',)), ('ferro', ('ferro', 'ferragen', 'arame', 'aco')),
      ('cimento', ('cimento',)), ('areia', ('areia', 'brita', 'seixo')),
      ('limpeza', ('limpeza', 'limeza')), ('seguranca', ('equipamento de seguranca', 'epi')),
      ('informatica', ('informatica',)), ('ferramentas', ('ferramenta',)),
      ('combustivel', ('combust', 'lubrificant')), ('madeira', ('madeira',)),
      ('tintas', ('tinta', 'verniz')), ('tijolos', ('tijolo',)),
      ('diversos', ('diverso', 'diversos', 'materais diversos')),
      ('locacao', ('locacao', 'aluguel')), ('servicos', ('servico',)),
      ('concreto', ('concreto', 'pre moldado')), ('argamassa', ('argamassa', 'massas')),
      ('piso', ('piso', 'ceramica', 'marmore')), ('revestimento', ('revestimento', 'acabamento')),
      ('telha', ('telha',)), ('alimentacao', ('alimentacao',)), ('vidro', ('vidro',)),
      ('forro', ('forro', 'dry wall')), ('adesivo', ('adesivo', 'plastificante', 'teck bond')),
    ]
    for grupo, termos in grupos:
        if any(t in n for t in termos): return grupo
    return None

def _find_cat(o,nome_categoria):
    if not o or not nome_categoria: return None
    values=list(o.get('categorias',{}).values()); nk=_norm(nome_categoria)
    exact=[v for v in values if _norm(v.get('nome'))==nk]
    if len(exact)==1: return exact[0]
    if len(exact)>1: return None
    family=_familia(nome_categoria)
    matches=[v for v in values if family and _familia(v.get('nome'))==family]
    return matches[0] if len(matches)==1 else None

def get_codigo_info_para_obra_e_categoria(obra_ident,nome_categoria):
    # Uma obra informada não pode ser trocada silenciosamente pela obra geral.
    target = get_obra_by_identifier(obra_ident) if obra_ident else get_obra_geral()
    res = _find_cat(target, nome_categoria)
    base={'obra_codigo':target.get('codigo') if target else None,
          'obra_classificacao':target.get('classificacao','') if target else '',
          'obra_nome':target.get('nome_display') if target else '',
          'cno':target.get('cno') if target else None,'is_fallback':False,'empresa':_EMPRESA_ATIVA}
    if res:
        return {**base,'codigo':res['codigo'],'classificacao':res.get('classificacao',''),
                'nome_categoria':res.get('nome',nome_categoria),
                'label_subclasse':f"{res.get('nome',nome_categoria)} — Cód. {res['codigo']}"}
    return {**base,'codigo':None,'classificacao':'','nome_categoria':str(nome_categoria or '').upper(),
            'label_subclasse':'Sem correspondência segura — revisar'}

def get_codigo_para_obra_e_categoria(nome_obra_display,nome_categoria):
    return get_codigo_info_para_obra_e_categoria(nome_obra_display,nome_categoria).get('codigo')

def reload(): return load_plano(True)
