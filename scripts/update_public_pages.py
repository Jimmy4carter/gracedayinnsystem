import re
from pathlib import Path

root = Path(r'c:/Users/USER/Documents/GitHub/gracedayinnsystem/downloadedtemplates/public site')
files = sorted(root.glob('*.html'))

print('Found', len(files), 'HTML pages')

for path in files:
    text = path.read_text(encoding='utf-8')
    orig = text

    body_match = re.search(r'<body[^>]*>', text)
    header_match = re.search(r'<header[^>]*>', text)
    if body_match and header_match and body_match.end() < header_match.start():
        text = text[:body_match.end()] + '\n\n' + text[header_match.start():]

    while True:
        start = text.find('<div class="top-nav">')
        if start == -1:
            break
        level = 0
        i = start
        while i < len(text):
            if text.startswith('<div', i):
                level += 1
                end_tag = text.find('>', i)
                if end_tag == -1:
                    i += 4
                else:
                    i = end_tag + 1
            elif text.startswith('</div>', i):
                level -= 1
                i += len('</div>')
                if level == 0:
                    text = text[:start] + text[i:]
                    break
            else:
                i += 1
        else:
            break

    text = re.sub(r'\s*<div class="nav-right search-switch">\s*<i class="icon_search"></i>\s*</div>\s*', '\n', text, flags=re.DOTALL)

    insertion = (
        '            <div class="row">\n'
        '                <div class="col-lg-12 text-right">\n'
        '                    <div class="search-icon search-switch">\n'
        '                        <i class="icon_search"></i>\n'
        '                        <span>Search</span>\n'
        '                    </div>\n'
        '                </div>\n'
        '            </div>\n'
        '        </div>\n'
        '    </header>'
    )

    if '<div class="search-icon search-switch">' not in text:
        text = text.replace('</header>', insertion, 1)

    if text != orig:
        path.write_text(text, encoding='utf-8')
        print('Updated', path.name)
    else:
        print('No changes needed for', path.name)
