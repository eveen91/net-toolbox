"""Typed, offline references and lossless paginated tables for the ZIP renderer."""
import csv
import io
import re

TABLE_PAGE_ROWS = 100


def safe_id(value):
    # Never turn inventory names or user-entered paths into filenames/anchors.
    return re.sub('[^a-zA-Z0-9_-]', '-', str(value))


def entity_id(source):
    return '-'.join(safe_id(source[key]) for key in ('module','type','id'))


def link_label(value):
    from .exports import cell
    return cell(value).replace('[','&#91;').replace(']','&#93;')


def table_lines(table, rows, start=0, linked=False):
    from .exports import cell
    lines=['| '+' | '.join(cell(c) for c in table['columns'])+' |',
           '| '+' | '.join('---' for _ in table['columns'])+' |']
    for index,row in enumerate(rows,start):
        values=[cell(c) for c in row]
        refs=table.get('rowReferences',[])
        if linked and index<len(refs):
            column=table.get('referenceColumn',0)
            values[column]=f'[{link_label(row[column])}](references.md#{entity_id(refs[index])})'
        lines.append('| '+' | '.join(values)+' |')
    return lines+['']


def supplements(document, diagrams):
    from .exports import heading
    files={};snapshot=document.get('snapshot',{})
    sources={entity_id(s):s for s in snapshot.get('sources',[])}
    lines=['# Source references','','Saved identities only. External objects are not recursively included.','']
    diagram_refs={}
    modules={'device':'device-visualization','rack':'dc-inventory','connection':'dc-inventory','subnet':'ipam'}
    for asset in diagrams:
        for reference in asset['references']:
            key=entity_id({'module':modules[reference['type']],**reference})
            diagram_refs.setdefault(key,[]).append(asset)
            if key not in sources:
                sources[key]={'module':modules[reference['type']],**reference,'name':'Missing source reference','missing':True}
    for table in snapshot.get('tables',[]):
        for ref in table.get('rowReferences',[]):
            key=entity_id(ref)
            if key not in sources:sources[key]={**ref,'name':'Missing source reference','missing':True}
    for key,source in sorted(sources.items()):
        status='Outside document scope; endpoint context only.' if source['type']=='external-device' else 'Source reference is missing; identity retained.' if source.get('missing') else 'Included in the saved source snapshot.'
        lines.extend([f'<a id="{key}"></a>',f"## {heading(source['name'])}",'',
                      f"Module: {heading(source['module'])} · Type: {heading(source['type'])} · ID: {heading(source['id'])}", '',status,''])
        for asset in {a['id']:a for a in diagram_refs.get(key,[])}.values():
            lines.append(f"- [Diagram: {link_label(asset['title'])}](diagrams.md#{asset['id']})")
        lines.append('')
    if sources:files['documents/references.md']='\n'.join(lines).encode()
    for table in snapshot.get('tables',[]):
        if len(table['rows'])<=TABLE_PAGE_ROWS:continue
        stem='table-'+safe_id(table['id'])
        total=(len(table['rows'])+TABLE_PAGE_ROWS-1)//TABLE_PAGE_ROWS
        for page in range(total):
            start=page*TABLE_PAGE_ROWS
            rows=table['rows'][start:start+TABLE_PAGE_ROWS]
            content=[f"# {heading(table['title'])} · page {page+1} / {total}",'',f'[Back to document](dc-{document["id"]}.md)','',
                     f'Rows {start+1}–{start+len(rows)} of {len(table["rows"])}.','']
            content+=[' · '.join(f'[{i+1}]({stem}-{i+1}.md)' for i in range(total)),'']
            content+=table_lines(table,rows,start,linked=True)
            files[f'documents/{stem}-{page+1}.md']='\n'.join(content).encode()
        output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow(table['columns'])
        # Keep CSV safe to open in a spreadsheet; exact values remain in Markdown.
        writer.writerows([("'"+str(v) if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else '' if v is None else v) for v in row] for row in table['rows'])
        files[f'documents/{stem}.csv']=output.getvalue().encode('utf-8-sig')
    if diagrams:
        lines=['# Diagram index','','PNG images work offline without extensions. SVG alternatives retain full labels in titles.',
               'Schematics describe saved records, not live link state. Full endpoint labels and facts are in the document tables.','',f'[Back to document](dc-{document["id"]}.md)','']
        lines += [f"- [{link_label(a['title'])}](#{a['id']})" for a in diagrams]+['']
        for asset in diagrams:
            lines += [f'<a id="{asset["id"]}"></a>',f"## {heading(asset['title'])}",'',
                      f"![{link_label(asset['title'])}](../{asset['files']['png']})",'',f"[Open SVG](../{asset['files']['svg']})",'']
        files['documents/diagrams.md']='\n'.join(lines).encode()
    return files
