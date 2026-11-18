"""Prepare a per-part review of independent K7222 parts-list OCR passes.

The inventory locates the expected page and reference, but never supplies a
missing OCR value. This report is evidence for review, not a transcription
approval: even three identical readings need comparison with the inventory.
"""
import argparse
import collections
import csv
import io
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT / 'reference/k7222-11/inventory.json'
PAGES = (6, 7, 8, 12, 13, 14, 15, 17)
TAGS = ('primary', 'r300', 'alt', 'alt2', 'cropL', 'cropR', 'struct')
# The extra gemma3 full-page run repeated unrelated capacitor rows on page 12
# and truncated before the inductors. Keep it visible to reviewers, but never
# let its agreement promote an entry through the machine gate.
REVIEW_ONLY_TAGS = frozenset(('alt2',))
REF = re.compile(r'(?<![A-Za-z0-9])([ACFLPRTV]\d+(?::\d+)?)(?![A-Za-z0-9])', re.I)
ARTICLE = re.compile(r'^(?:\d\.\d{2,}|\d{5,6}\s+\d{3,4}\.\d+/\d{2})')
SOURCE_CONFLICTS = {
    '012-6931:V22': ('Page 15 groups V19 through V25 as 1 AE 15 diodes, including V22; '
                     'the page-10 schematic and waveform annotation use V22 in the converter.'),
}


def _readings(path):
    with path.open(newline='') as source:
        raw = source.read()
        if path.name.endswith('.raw.txt'):
            raw = ''.join(line for line in raw.splitlines(keepends=True)
                          if not line.startswith('<<<'))
        stream = io.StringIO(raw)
        header = stream.readline()
        stream.seek(0)
        delimiter = ';' if 'Kurzzeichen;' in header else ','
        for number, row in enumerate(csv.reader(stream, delimiter=delimiter), 1):
            quantity = next((i for i, cell in enumerate(row[:5])
                             if re.fullmatch(r'\s*[1-9]\d?\s*', cell)), None)
            if quantity is None or quantity == 0:
                continue
            label = ','.join(row[:quantity])
            references = list(dict.fromkeys(x.upper() for x in REF.findall(label)))
            if not references:
                continue
            count = int(row[quantity].strip())
            if len(references) == 1 and count > 1 and '...' in label:
                start = re.fullmatch(r'([A-Z]+\d+):(\d+)', references[0])
                if start:
                    references = [f'{start[1]}:{n}' for n in
                                  range(int(start[2]), int(start[2]) + count)]
                else:
                    start = re.fullmatch(r'([A-Z]+)(\d+)', references[0])
                    end = re.search(r'\.\.\.\s*(\d+)\b', label)
                    if start and end and int(end[1]) - int(start[2]) + 1 == count:
                        references = [f'{start[1]}{n}' for n in
                                      range(int(start[2]), int(end[1]) + 1)]
            if len(references) == 2 and count > 2:
                a, b = references
                a_match = re.fullmatch(r'([A-Z]+\d+):(\d+)', a)
                b_match = re.fullmatch(r'([A-Z]+\d+):(\d+)', b)
                if (a_match and b_match and a_match[1] == b_match[1]
                        and int(b_match[2]) - int(a_match[2]) + 1 == count):
                    references = [f'{a_match[1]}:{n}' for n in
                                  range(int(a_match[2]), int(b_match[2]) + 1)]
            # A comma in a German decimal may have been emitted as a CSV
            # separator. Rejoin description fragments until the article code.
            description = []
            article = None
            for cell in row[quantity + 1:]:
                if ARTICLE.match(cell.strip()):
                    article = cell.strip()
                    break
                if cell.strip():
                    description.append(cell.strip())
            yield dict(line=number, references=references, quantity=count,
                       quantity_consistent=len(references) == count,
                       description=','.join(description), article=article)


def _key(description):
    return re.sub(r'[^a-z0-9]+', '', description.lower())


def _primary_article(article):
    return re.sub(r'\s+\d{3}-\d-\d{3}-\d{3}.*$', '', article or '')


def _number_forms(number):
    value = format(number, '.12g')
    return (value, value.replace('.', ',')) if '.' in value else (value,)


def _printed_value_matches(part, reading):
    description = reading['description']
    expected = part['description']
    kind = part['kind']
    if kind in ('resistor', 'potentiometer', 'thermistor') and part['value'] is not None:
        value = part['value']
        scales = ((1e6, 'MOhm'), (1e3, 'kOhm'), (1, 'Ohm'))
        matches = any(re.search(r'(?<!\d)' + re.escape(form) + r'\s*' + unit + r'\b',
                                description, re.I)
                      for scale, unit in scales if value >= scale
                      for form in _number_forms(value / scale))
    elif kind == 'capacitor':
        match = re.match(r'^(\d+(?:\.\d+)?)(?:e-\d+ F| nF)', expected)
        if match:
            matches = any(re.search(r'(?<!\d)' + re.escape(form) + r'(?=[/\-\s]|$)',
                                    description, re.I)
                          for form in _number_forms(float(match[1])))
        else:
            matches = _key(expected) in _key(description + ' ' + (reading['article'] or ''))
    else:
        matches = (expected != 'None' and
                   _key(expected) in _key(description + ' ' + (reading['article'] or '')))
    tolerance = part.get('tolerance_percent')
    if matches and tolerance is not None:
        number = format(tolerance, '.12g')
        if kind == 'capacitor':
            matches = bool(re.search(r'/' + re.escape(number) + r'(?=[/\-\s]|$)', description)
                           or re.search(r'\b' + re.escape(number) + r'\s*%', description))
        else:
            matches = bool(re.search(r'\b' + re.escape(number) + r'\s*%', description))
    return bool(matches)


def audit(inventory, ocr_root):
    parts = inventory['parts']
    if len(parts) != 260 or len({p['id'] for p in parts}) != 260:
        raise ValueError('inventory no longer contains 260 unique entries')
    by_page = collections.defaultdict(list)
    for part in parts:
        by_page[part['source']['page']].append(part)
    result = []
    for page, entries in sorted(by_page.items()):
        sources = {}
        if page in PAGES:
            for tag in TAGS:
                name = f'page_{page:03d}' + ('' if tag == 'primary' else f'.{tag}') + '.csv'
                path = ocr_root / name
                if tag == 'alt' and (ocr_root / f'page_{page:03d}.alt.raw.txt').is_file():
                    path = ocr_root / f'page_{page:03d}.alt.raw.txt'
                if path.is_file():
                    sources[tag] = list(_readings(path))
        for part in entries:
            matches = {}
            for tag, rows in sources.items():
                candidates = [r for r in rows if part['reference'] in r['references']
                              and r['quantity_consistent']]
                if len(candidates) == 1 and candidates[0]['description']:
                    row = candidates[0]
                    matches[tag] = dict(line=row['line'], description=row['description'],
                                        article=row['article'])
                elif len(candidates) > 1:
                    matches[tag] = dict(ambiguous_lines=[r['line'] for r in candidates])
            groups = collections.defaultdict(list)
            descriptions = collections.defaultdict(list)
            articles = collections.defaultdict(list)
            blank_articles = []
            for tag, reading in matches.items():
                if tag in REVIEW_ONLY_TAGS:
                    continue
                if 'description' in reading:
                    groups[_key(reading['description']+' '+_primary_article(reading['article']))].append(tag)
                    descriptions[_key(reading['description'])].append(tag)
                    if reading['article']:
                        articles[_key(_primary_article(reading['article']))].append(tag)
                    elif tag in ('primary', 'r300', 'alt', 'alt2', 'struct'):
                        blank_articles.append(tag)
            largest = max(groups.values(), key=len, default=[])
            description_passes = max(descriptions.values(), key=len, default=[])
            article_passes = max(articles.values(), key=len, default=[])
            article_suspect = bool(article_passes and not re.match(
                r'^\d\.\d{2,}', matches[article_passes[0]]['article']))
            article_agrees = ((len(article_passes) >= 3 and not article_suspect)
                              or (not articles and len(blank_articles) >= 3))
            cell_agreement = len(description_passes) >= 3 and article_agrees
            voted_reading = (dict(description=matches[description_passes[0]]['description'],
                                  article=matches[article_passes[0]]['article'] if article_passes else None)
                             if cell_agreement else None)
            comparison = _printed_value_matches(part, voted_reading) if voted_reading else None
            source_conflict = SOURCE_CONFLICTS.get(part['id'])
            result.append(dict(id=part['id'], source_page=page,
                               inventory_description=part['description'],
                               inventory_evidence=part['evidence'], readings=matches,
                               review_only_passes=sorted(set(matches) & REVIEW_ONLY_TAGS),
                               source_conflict=source_conflict,
                               exact_agreement_passes=largest,
                               description_agreement_passes=description_passes,
                               article_agreement_passes=article_passes,
                               article_format_suspect=article_suspect,
                               blank_article_agreement_passes=blank_articles if not articles else [],
                               inventory_value_or_type_matches=comparison,
                               status=('needs-schematic-review' if page not in PAGES else
                                       'needs-source-review' if source_conflict else
                                       'confirmed-by-3-passes' if comparison is True else
                                       'needs-inventory-comparison' if comparison is False else
                                       'needs-source-review')))
    return dict(format='dac-monitor-inventory-ocr-audit-v1',
                inventory_entries=len(parts),
                source_pages=list(PAGES),
                entries=result,
                counts=dict(collections.Counter(entry['status'] for entry in result)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ocr-root', type=Path, required=True,
                        help='directory containing page_NNN[.tag].csv files')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(json.loads(INVENTORY.read_text()), args.ocr_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(result['counts'], sort_keys=True))


if __name__ == '__main__':
    main()
