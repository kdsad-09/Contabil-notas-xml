"""Quick end-to-end test: parse + categorize all XMLs in both zips."""
import zipfile, py_compile
from xml_processor import parse_nfe
from categorizer import categorize_invoice, suggest_project

def test_zip(path, label, limit=None):
    print(f"=== {label} ===")
    z = zipfile.ZipFile(path, "r")
    names = sorted(z.namelist())
    if limit:
        names = names[:limit]
    for fname in names:
        with z.open(fname) as f:
            data_rows = parse_nfe(f.read())
        if data_rows and "error" in data_rows[0]:
            print(f"  ERROR {fname}: {data_rows[0]['error']}")
            continue
        elif not data_rows:
            continue
            
        data = data_rows[0]
        items_text = [it["descricao"] for it in data.get("itens", [])]
        cat, _ = categorize_invoice(items_text, data.get("infAdic"), data.get("cno_sugerido"))
        proj, _ = suggest_project(data.get("infAdic"), data.get("cno_sugerido"))
        nf = data["nNF"]
        val = data["valor_formatted"]
        n_items = data["qtd_itens"]
        cno = data.get("cno_sugerido") or "SEM CNO"
        print(f"  NF:{nf:>5} | {val:>12} | {n_items} itens | Cat: {cat:<24} | Obra: {proj}")
    z.close()
    print()

test_zip("lote_teste_obras.zip", "LOTE TESTE (10 NFs construcao)", None)
test_zip("xml_nfe_1771077455.zip", "LOTE REAL (primeiras 5)", 5)

# Syntax check all files
for f in ["app.py", "xml_processor.py", "categorizer.py", "exporter.py"]:
    py_compile.compile(f, doraise=True)
print("Todos os arquivos compilam OK!")
