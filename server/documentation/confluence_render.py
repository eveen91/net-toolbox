"""Canonical frozen chapters -> Confluence storage, plain browser preview and PNGs.

We do not translate exported Markdown files or depend on a Confluence renderer.
"""
import hashlib
import html
import json
from xml.etree import ElementTree as ET
from markdown_it import MarkdownIt
from .templates import value as field_value
from .export_links import safe_id,TABLE_PAGE_ROWS

RENDERER_VERSION=1


def esc(value):return html.escape(str(value),quote=True)


def sha(value):return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()


def code_macro(code):
    # Split CDATA terminators to preserve code literally without breaking storage.
    code=code.replace(']]>',']]]]><![CDATA[>')
    return '<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA['+code+']]></ac:plain-text-body></ac:structured-macro>'


def rich_text(value):
    parser=MarkdownIt('commonmark',{'html':False,'breaks':False,'xhtmlOut':True}).enable('table')
    # Narrative image URLs are never fetched or embedded; diagrams are declared
    # frozen PNG attachments only. Relative links remain readable text.
    parser.add_render_rule('image',lambda self,tokens,index,options,env:esc(tokens[index].content))
    default_link=parser.renderer.rules['link_open'] if 'link_open' in parser.renderer.rules else None
    def link(self,tokens,index,options,env):
        href=tokens[index].attrGet('href') or ''
        if not href.startswith(('https://','http://','mailto:')):tokens[index].attrs.pop('href',None)
        return default_link(tokens,index,options,env) if default_link else self.renderToken(tokens,index,options,env)
    parser.add_render_rule('link_open',link)
    preview=parser.render(str(value))
    parser.add_render_rule('fence',lambda self,tokens,index,options,env:code_macro(tokens[index].content))
    parser.add_render_rule('code_block',lambda self,tokens,index,options,env:code_macro(tokens[index].content))
    return parser.render(str(value)),preview


def page_link(title,space,label=None):
    return f'<ac:link><ri:page ri:content-title="{esc(title)}" ri:space-key="{esc(space)}"/><ac:plain-text-link-body><![CDATA[{str(label or title).replace("]]>","]]]]><![CDATA[>")}]]></ac:plain-text-link-body></ac:link>'


def table_markup(table,rows):
    def cell(value):
        if value is None or value=='':return 'Not recorded'
        if isinstance(value,(dict,list)):value=json.dumps(value,ensure_ascii=False)
        return esc(value).replace('\r','').replace('\n','<br />')
    return '<table><thead><tr>'+''.join('<th>'+cell(c)+'</th>' for c in table['columns'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'


def render(document,version,space):
    chapters=document.get('chapters')
    if not chapters:raise ValueError('This version predates frozen chapter definitions. Create a new version before preparing Confluence pages.')
    title=document['form']['title'];snapshot=document.get('snapshot',{});assets=document.get('assets',[])
    pages=[]
    def create(key,label,parent='root'):
        page_title=title if key=='root' else f'{title} — {label}'
        if len(page_title)>255:raise ValueError('A generated Confluence title exceeds 255 characters. Shorten the document title before creating a new version.')
        result={'key':key,'title':page_title,'label':label,'parentKey':parent,'storage':'','previewHtml':'','attachments':[]}
        pages.append(result);return result
    def append(page,storage,preview=None):
        page['storage']+=storage;page['previewHtml']+=storage if preview is None else preview
    root=create('root',title,None)
    append(root,f'<h1>{esc(title)}</h1><p>Document {document["id"]} · immutable published version {version} · source collection: {esc(snapshot.get("collectedAt","Not recorded"))}</p>')
    append(root,'<p>Saved records only; no live link state. Diagram attachments belong to this revision.</p>')
    for warning in snapshot.get('warnings',[]):append(root,'<p>'+esc(warning)+'</p>')
    chapter_pages={p['id']:create('chapter-'+p['id'],p['label']) for p in chapters}
    append(root,'<ul>','<ul>')
    for page in chapter_pages.values():append(root,'<li>'+page_link(page['title'],space,page['label'])+'</li>','<li>'+esc(page['label'])+'</li>')
    append(root,'</ul>','</ul>')
    def target(chapter):
        mapped=document.get('sourceChapterMap',{}).get(chapter,chapter)
        return chapter_pages.get(mapped,next(iter(chapter_pages.values())))
    for chapter in chapters:
        page=chapter_pages[chapter['id']]
        append(page,'<h1>'+esc(chapter['label'])+'</h1>')
        recorded=False
        for section in chapter['sections']:
            fields=[f for f in section['fields'] if str(field_value(document['form'],f)).strip()]
            if not fields:continue
            recorded=True;append(page,'<h2>'+esc(section['title'])+'</h2>')
            for field in fields:
                value=field_value(document['form'],field)
                if field.get('options'):value=dict(field['options']).get(value,value)
                append(page,'<h3>'+esc(field['label'])+'</h3>')
                storage,preview=rich_text(value);append(page,storage,preview)
        page['hasNarrative']=recorded
    # Large tables become child pages rather than a huge parent-page body.
    for table in snapshot.get('tables',[]):
        parent=target(table.get('chapter'));rows=table['rows']
        if len(rows)<=TABLE_PAGE_ROWS:
            append(parent,'<h2>'+esc(table['title'])+'</h2>'+table_markup(table,rows));continue
        append(parent,f'<h2>{esc(table["title"])}</h2><p>{len(rows)} rows; complete data in the following pages.</p>')
        for offset in range(0,len(rows),TABLE_PAGE_ROWS):
            page=create('table-'+safe_id(table['id'])+'-'+str(offset//TABLE_PAGE_ROWS+1),table['title']+' · '+str(offset//TABLE_PAGE_ROWS+1),parent['key'])
            append(page,'<h1>'+esc(table['title'])+'</h1>'+table_markup(table,rows[offset:offset+TABLE_PAGE_ROWS]))
            append(parent,'<p>'+page_link(page['title'],space,page['label'])+'</p>','<p>'+esc(page['label'])+'</p>')
    for asset in assets:
        page=target(asset['chapter']);path=asset['files']['png'];name=path.split('/')[-1]
        page['attachments'].append({'filename':name,'path':path,'sha256':None,'mediaType':'image/png','title':asset['title']})
        append(page,'<h2>'+esc(asset['title'])+'</h2>'+f'<ac:image ac:alt="{esc(asset["title"])}"><ri:attachment ri:filename="{esc(name)}"/></ac:image>',
               '<p>Frozen PNG diagram: '+esc(asset['title'])+'</p>')
    for source in snapshot.get('sources',[]):
        status=' · outside document scope (endpoint only)' if source['type']=='external-device' else ''
        append(root,'<p>'+esc(f"{source['module']}: {source['name']} (ID {source['id']}; version {source.get('version')}){status}")+'</p>')
    if len(pages)>200:raise ValueError('This hierarchy exceeds 200 pages. Choose a smaller scope.')
    for page in pages:
        page.pop('hasNarrative',None)
        if page['storage']=='<h1>'+esc(page['label'])+'</h1>':append(page,'<p>Not recorded.</p>')
        try:ET.fromstring('<root xmlns:ac="http://atlassian.com/content" xmlns:ri="http://atlassian.com/resource/identifier">'+page['storage']+'</root>')
        except ET.ParseError:raise ValueError('The document contains characters that cannot be represented in Confluence storage. Remove control characters and create a new version.')
        page['contentHash']=sha(page['storage'])
    return pages
