"""Convert all Japanese manual sections to phone-sized PDF pages."""
from html.parser import HTMLParser
from html import escape
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether

ROOT = Path(__file__).resolve().parents[1]

class Node:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = Node('root')
        self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in ('meta', 'br', 'hr', 'img', 'link', 'input'):
            self.stack.append(node)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break
    def handle_data(self, text):
        self.stack[-1].children.append(text)

def find(node, tag):
    for child in node.children:
        if isinstance(child, Node):
            if child.tag == tag:
                yield child
            yield from find(child, tag)

def plain(node):
    return node if isinstance(node, str) else ''.join(plain(c) for c in node.children)

def inline(node):
    if isinstance(node, str):
        return escape(node)
    body = ''.join(inline(c) for c in node.children)
    if node.tag in ('b', 'strong'):
        return '<b>' + body + '</b>'
    if node.tag == 'br':
        return '<br/>'
    if node.tag == 'a' and node.attrs.get('href', '').startswith('https://'):
        return f'<a href="{escape(node.attrs["href"], quote=True)}" color="#087165">{body}</a>'
    return body

def build():
    output = ROOT / 'output/pdf/F1テレメトリー_使い方_日本語_v0.3.1.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont('JP', 'C:/Windows/Fonts/meiryo.ttc', subfontIndex=0))
    pdfmetrics.registerFont(TTFont('JPBold', 'C:/Windows/Fonts/meiryob.ttc', subfontIndex=0))
    pdfmetrics.registerFontFamily('JP', normal='JP', bold='JPBold', italic='JP', boldItalic='JPBold')
    body = ParagraphStyle('body', fontName='JP', fontSize=11, leading=18, spaceAfter=10, wordWrap='CJK',
                          allowWidows=False, allowOrphans=False)
    heading = ParagraphStyle('heading', parent=body, fontName='JPBold', fontSize=18, leading=27,
                             textColor=colors.HexColor('#087165'), spaceAfter=18, keepWithNext=True)
    title = ParagraphStyle('title', parent=heading, fontSize=23, leading=34)
    label = ParagraphStyle('label', parent=body, fontName='JPBold', spaceAfter=5, textColor=colors.HexColor('#087165'))
    note = ParagraphStyle('note', parent=body, fontSize=10, leading=17, backColor=colors.HexColor('#fff7df'),
                          borderPadding=8, spaceBefore=10, spaceAfter=18)
    parser = Parser()
    parser.feed((ROOT / 'docs/manual-ja.html').read_text(encoding='utf-8'))
    sections = list(find(parser.root, 'section'))
    assert len(sections) == 8
    story = [Paragraph('F1テレメトリー<br/>使い方マニュアル', title),
             Paragraph('日本語版 / v0.3.1 プレビュー', body), Paragraph('走る・記録する・比較する', body),
             Spacer(1, 20), Paragraph('目次', heading)]
    for i, section in enumerate(sections, 1):
        h = next(find(section, 'h2'))
        story.append(Paragraph(f'<a href="#{section.attrs["id"]}" color="#087165">{i}. {inline(h)}</a>', body))
    story += [Spacer(1, 20), Paragraph('Windowsアプリの説明書です。iPhoneでは、このPDFを確認用に閲覧できます。', body)]
    story.append(PageBreak())
    for section in sections:
        story.append(Spacer(1, 18))
        h = next(find(section, 'h2'))
        story.append(Paragraph(f'<a name="{section.attrs["id"]}"/>{inline(h)}', heading))
        for child in section.children:
            if not isinstance(child, Node) or child.tag == 'h2':
                continue
            if child.tag in ('p', 'aside'):
                paragraph = Paragraph(inline(child), note if child.tag == 'aside' else body)
                story.append(KeepTogether([paragraph]) if child.tag == 'aside' else paragraph)
            elif child.tag in ('ol', 'ul'):
                for i, item in enumerate(find(child, 'li'), 1):
                    story.append(Paragraph((f'{i}. ' if child.tag == 'ol' else '・ ') + inline(item), body))
            elif child.tag == 'table':
                rows = list(find(child, 'tr'))
                headers = [inline(c) for c in rows[0].children if isinstance(c, Node)]
                story.append(Paragraph(' / '.join(headers), label))
                for row in rows[1:]:
                    cells = [c for c in row.children if isinstance(c, Node)]
                    parts = [Paragraph(inline(cells[0]), label)]
                    for i, cell in enumerate(cells[1:], 1):
                        key = f'<b>{headers[i]}：</b>' if len(cells) > 2 else ''
                        parts.append(Paragraph(key + inline(cell), body))
                    story.append(KeepTogether(parts))
                    story.append(Spacer(1, 5))
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('JP', 8)
        canvas.setFillColor(colors.HexColor('#546d75'))
        canvas.drawString(26, 17, 'F1 Telemetry / v0.3.1')
        canvas.drawRightString(334, 17, str(doc.page))
        canvas.restoreState()
    doc = SimpleDocTemplate(str(output), pagesize=(360, 720), rightMargin=26, leftMargin=26,
                            topMargin=30, bottomMargin=36, title='F1テレメトリー 使い方マニュアル 日本語 v0.3.1',
                            author='F1 Telemetry')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    from pypdf import PdfReader
    reader = PdfReader(output)
    text = ''.join('\n'.join(page.extract_text().splitlines()[2:]) for page in reader.pages)
    normalize = lambda s: ''.join(s.split())
    for section in sections:
        assert normalize(plain(next(find(section, 'h2')))) in normalize(text)
        for tag in ('p', 'aside', 'li', 'th', 'td'):
            for node in find(section, tag):
                assert normalize(plain(node)) in normalize(text), plain(node)[:40]
    print(f'PDF complete: {len(reader.pages)} pages; all eight sections and full source content verified; {output.stat().st_size} bytes')

if __name__ == '__main__':
    build()
