import os
import xml.etree.ElementTree as ET
import re

directory = r'C:\Users\Usuario\Downloads\teste xml\teste xml\xml da hikari\qRNb1Oq8-part-1'

def extract_cno_test(inf_adic):
    if not inf_adic:
        return None
    # 1. Look for CNO keyword with up to 30 chars of distance to a 12 digit number (allowing dots/slashes/dashes)
    match = re.search(r'(?:C\.?N\.?O\.?|CEI|MATR[IÍ]CULA)(?:.{0,30}?)([\d]{2}[.\s]?[\d]{3}[.\s]?[\d]{4,5}[/.\-\s]?[\d]{2})', inf_adic, re.IGNORECASE)
    if match:
        digits = re.sub(r'[^\d]', '', match.group(1))
        # Depending on format it might capture slightly more or less, but normally CNO is 12.
        if len(digits) >= 11:
            return digits[:12]
    
    # 2. Look for explicit typical formatting like 90.018.83297/70
    match2 = re.search(r'([\d]{2}\.[\d]{3}\.[\d]{4,5}[/.\-][\d]{2})', inf_adic)
    if match2:
        digits = re.sub(r'[^\d]', '', match2.group(1))
        return digits[:12]
        
    # 3. Look for explicit keyword exact match without space like CNO900224033370
    match3 = re.search(r'(?:CNO|CEI)([\d]{12})\b', inf_adic, re.IGNORECASE)
    if match3:
        return match3.group(1)

    return None

found = 0
for filename in os.listdir(directory):
    if not filename.endswith('.xml'): continue
    path = os.path.join(directory, filename)
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        content = re.sub(r'\sxmlns(?::\w+)?="[^"]*"', '', content)
        content = re.sub(r'<(/?)(\w+):', r'<\1\2_', content)
        root = ET.fromstring(content)
        infNFe = root.find('.//infNFe')
        if infNFe is None: continue
        
        node = infNFe.find('infAdic/infCpl')
        inf_adic = (node.text or '').strip() if node is not None else ''
        
        cno = extract_cno_test(inf_adic)
        if cno:
            found += 1
            print(filename, '->', cno)
    except Exception as e:
        pass
print('Total found:', found)
