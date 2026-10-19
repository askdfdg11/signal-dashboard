"""Allowlisted static build; do not publish scripts, credentials, or Git metadata."""
import json
import re
import shutil

from common import ROOT, read


def main():
    source = (ROOT / 'index.html').read_text()
    for element, file in [('seed-data', 'briefings.json'), ('seed-market-data', 'market-history.json')]:
        value = json.dumps(read(ROOT / 'data' / file), ensure_ascii=False, separators=(',', ':'))
        value = value.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
        pattern = r'(<script[^>]*id="' + element + r'"[^>]*>).*?(</script>)'
        source, count = re.subn(pattern, lambda m: m[1] + value + m[2], source, flags=re.S)
        assert count == 1, element
    target = ROOT / 'dist'
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    (target / 'index.html').write_text(source)
    (target / '.nojekyll').touch()
    shutil.copytree(ROOT / 'data', target / 'data')
    print('Static site ready in dist/')


if __name__ == '__main__':
    main()
