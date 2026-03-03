import zipfile
import xml.etree.ElementTree as ET

def read_docx(path):
    with zipfile.ZipFile(path) as docx:
        tree = ET.XML(docx.read('word/document.xml'))
        texts = []
        for p in tree.iter():
            if p.tag.endswith('}p'):
                p_text = ''.join([n.text for n in p.iter() if n.tag.endswith('}t') and n.text])
                if p_text:
                    texts.append(p_text)
        return '\n'.join(texts)

content = read_docx(r'c:\Users\Dell Inspiron\Downloads\Nouva PT\plano_implementacao_redis (1).docx')
with open(r'c:\Users\Dell Inspiron\Downloads\Nouva PT\docx_content.txt', 'w', encoding='utf-8') as f:
    f.write(content)
