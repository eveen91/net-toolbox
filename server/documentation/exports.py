"""Portable artifacts generated once when a version is created."""
import hashlib
import html
import io
import json
import zipfile
from pathlib import Path
from .templates import value as field_value
from .export_links import TABLE_PAGE_ROWS,safe_id,table_lines,supplements,link_label

CATALOG = json.loads(Path(__file__).with_name('chapters.json').read_text())


def text(value):
    # Keep Markdown syntax and fenced examples, but neutralize raw HTML outside fences.
    output=[]; fenced=False; marker=None
    for line in str(value).replace('\r\n','\n').replace('\r','\n').split('\n'):
        stripped=line.lstrip()
        if stripped.startswith(('```','~~~')):
            current=stripped[:3]
            if not fenced: fenced=True;marker=current
            elif current==marker: fenced=False;marker=None
            output.append(line)
        else: output.append(line if fenced else html.escape(line,quote=False))
    if fenced: output.append(marker)
    return '\n'.join(output)


def heading(value):
    return html.escape(str(value).replace('\n',' ').replace('\r',' '),quote=False).replace('#','\\#')


def cell(value):
    if value is None or value=='':return 'Not recorded'
    if isinstance(value,(list,dict)):value=json.dumps(value,ensure_ascii=False)
    value=html.escape(str(value),quote=False).replace('\\','&#92;')
    for char,entity in [('`','&#96;'),('[','&#91;'),(']','&#93;'),('*','&#42;'),('_','&#95;'),('~','&#126;')]:value=value.replace(char,entity)
    return value.replace('|','\\|').replace('\r','').replace('\n','<br>')


def markdown(document, number, created_at, description, *, packaged=False):
    form=document['form']
    chapters=document.get('chapters',CATALOG)
    lines=[f"# {heading(form['title'])}", '',f"**Subject:** {heading(form.get('dcName',''))}",
           f"**Document:** {document['id']} · **Version:** {number} · **Saved draft revision:** {document['version']}",
           f'**Version created:** {created_at}', f"**Status:** {document.get('status','draft')}", '',
           '> Saved documentation version. This export contains the recorded form; it does not collect live inventory.', '']
    if description: lines.extend(['**Version note**', '',text(description),''])
    lines.extend(['## Contents','']+[f"- [{heading(page['label'])}](#{page['id']})" for page in chapters]+[''])
    if document.get('assets'):
        lines.extend(['## Diagrams',''])
        if packaged:lines.extend(['[Open diagram index](diagrams.md) · Local PNG and SVG files.',''])
        else:lines.extend(['The ZIP download includes frozen PNG/SVG diagrams. This standalone Markdown contains their equivalent recorded equipment, port and connection tables.',''])
    for page in chapters:
        # Stable HTML anchors work in common Markdown viewers and on-premises wiki imports.
        lines.extend([f'<a id="{page["id"]}"></a>',f'## {page["label"]}',''])
        has_content=False
        for section in page['sections']:
            fields=[field for field in section['fields'] if str(field_value(form,field)).strip()]
            if not fields:continue
            has_content=True
            lines.extend([f'### {section["title"]}',''])
            for field in fields:
                value=field_value(form,field)
                if field.get('options'):value=dict(field['options']).get(value,value)
                lines.extend([f'#### {field["label"]}','',text(value),''])
        for table in document.get('snapshot',{}).get('tables',[]):
            target=document.get('sourceChapterMap',{}).get(table.get('chapter'),table.get('chapter'))
            if target not in {p['id'] for p in chapters}:target=chapters[0]['id']
            if target!=page['id']:continue
            has_content=True
            lines.extend([f"### {heading(table['title'])}",''])
            rows=table['rows']
            if packaged and len(rows)>TABLE_PAGE_ROWS:
                stem='table-'+safe_id(table['id'])
                lines.extend([f'{len(rows)} rows. Showing the first {TABLE_PAGE_ROWS}. [All pages]({stem}-1.md) · [CSV]({stem}.csv).',''])
                rows=rows[:TABLE_PAGE_ROWS]
            lines.extend(table_lines(table,rows,linked=packaged))
        for asset in document.get('assets',[]) if packaged else []:
            target=document.get('sourceChapterMap',{}).get(asset['chapter'],asset['chapter'])
            if target not in {p['id'] for p in chapters}:target=chapters[0]['id']
            if target==page['id']:
                has_content=True
                lines.extend([f"### {heading(asset['title'])}",'',f"![{link_label(asset['title'])}](../{asset['files']['png']})",'',f"[SVG](../{asset['files']['svg']}) · [All diagrams](diagrams.md#{asset['id']})",''])
        if not has_content:lines.extend(['Not recorded.',''])
    snapshot=document.get('snapshot',{})
    if snapshot:
        if packaged and snapshot.get('sources'):lines.extend(['[Source reference index](references.md)',''])
        lines.extend(['## Source provenance','',f"Collected: {heading(snapshot.get('collectedAt','Not recorded'))}",''])
        for source in snapshot.get('sources',[]):lines.append(f"- {heading(source['module'])}: {heading(source['name'])} (ID {source['id']}; version {source.get('version')}; updated {heading(source.get('updatedAt') or 'Not recorded')}).")
        lines.extend(['']+['- '+heading(warning) for warning in snapshot.get('warnings',[])]+[''])
    return '\n'.join(lines).encode('utf-8')


def artifacts(document,number,created_at,description):
    from .diagrams import generate
    assets,asset_files,rendering=generate(document.get('snapshot',{}))
    document['assets']=assets
    document['diagramRendering']=rendering
    content=markdown(document,number,created_at,description)
    name=f'documents/dc-{document["id"]}.md'
    packaged=markdown(document,number,created_at,description,packaged=True)
    digest=hashlib.sha256(content).hexdigest()
    files={name:packaged,**asset_files,**supplements(document,assets)}
    files['README.md']=(f'# Documentation package\n\n[Open document]({name})\n\nDocument {document["id"]}, version {number}.\n'
        +'\nKeep this directory structure to preserve offline links. PNG diagrams require no extension or application access.\n'
        +'Long tables are split into pages of 100 rows; CSV text cells are protected against spreadsheet formulas.\n'
        +'The separate Markdown download is self-contained text with all rows; this package adds images and linked pages.\n').encode()
    if assets:files['README.md']+=b'\n[Diagram index](documents/diagrams.md)\n'
    manifest={'schemaVersion':3,'rendererVersion':3,'diagramRendering':rendering,'documentId':document['id'],'version':number,
              'draftRevision':document['version'],'createdAt':created_at,'tenantId':document.get('tenantId'),
              'templateId':document['form'].get('templateId','network'),'templateVersion':document.get('templateVersion',1),
              'status':document.get('status','draft'),'publication':document.get('publication'),
              'title':document['form']['title'],'dcName':document['form'].get('dcName',''),
              'scope':document.get('snapshot',{}).get('scope',{}),'standaloneMarkdownSha256':digest,
              'sourceCollectedAt':document.get('snapshot',{}).get('collectedAt'),'sources':document.get('snapshot',{}).get('sources',[]),
              'requiredPermissions':document.get('snapshot',{}).get('requiredPermissions',[]),
              'limitations':document.get('snapshot',{}).get('warnings',[])+(['No structured diagram data was saved; refresh a draft to collect it.'] if not document.get('snapshot',{}).get('diagramData') else []),
              'assets':assets,'files':[{'path':path,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for path,data in [(name,files[name])]+sorted((p,d) for p,d in files.items() if p!=name)]}
    files['manifest.json']=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    target=io.BytesIO()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for path,data in sorted(files.items()):
            info=zipfile.ZipInfo(path,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,data)
    return content,target.getvalue(),digest
