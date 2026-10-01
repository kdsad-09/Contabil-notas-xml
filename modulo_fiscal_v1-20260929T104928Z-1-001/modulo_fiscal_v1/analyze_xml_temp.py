import os
import xml.etree.ElementTree as ET
import re

directory = r"C:\Users\Usuario\Downloads\teste xml\teste xml\xml da hikari\qRNb1Oq8-part-1"

total_files = 0
files_with_cobr = 0
files_with_dup = 0
files_with_infcpl = 0
files_with_cno_in_infcpl = 0
files_with_detpag = 0
cno_patterns_found = set()

ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

for filename in os.listdir(directory):
    if filename.endswith(".xml"):
        total_files += 1
        filepath = os.path.join(directory, filename)
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            
            # cobr and dup
            cobr = root.find('.//nfe:cobr', ns)
            if cobr is not None:
                files_with_cobr += 1
                if cobr.findall('.//nfe:dup', ns):
                    files_with_dup += 1
                    
            # infCpl and CNO
            infcpl = root.find('.//nfe:infCpl', ns)
            if infcpl is not None and infcpl.text:
                files_with_infcpl += 1
                text = infcpl.text.upper()
                if "CNO" in text:
                    files_with_cno_in_infcpl += 1
                    # try to extract CNO pattern
                    match = re.search(r'CNO\s*[:\-]?\s*([0-9\.\/\-]+)', text)
                    if match:
                        cno_patterns_found.add(match.group(1).strip())
                        
            # pag
            pag = root.find('.//nfe:pag', ns)
            if pag is not None:
                if pag.findall('.//nfe:detPag', ns):
                    files_with_detpag += 1

        except Exception as e:
            print(f"Error parsing {filename}: {e}")

print(f"Total XMLs processed: {total_files}")
print(f"XMLs with <cobr>: {files_with_cobr}")
print(f"XMLs with <dup> (parcelas): {files_with_dup}")
print(f"XMLs with <pag><detPag>: {files_with_detpag}")
print(f"XMLs with <infCpl> (additional info): {files_with_infcpl}")
print(f"XMLs with 'CNO' mentioned in <infCpl>: {files_with_cno_in_infcpl}")
print(f"Unique CNO patterns found (sample of 10): {list(cno_patterns_found)[:10]}")
