"""Local, deterministic PNG/SVG output from the application's shared JS layout.

No browsers, live reads, network requests, user paths or runtime screenshots.
"""
import hashlib
import io
import json
import subprocess
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version

LAYOUT = Path(__file__).with_name('diagram-layout.mjs')
FONT = Path(__file__).with_name('fonts')/'DejaVuSans.ttf'
MAX_PAGES = 512
MAX_ASSET_BYTES = 64 * 1024 * 1024


@lru_cache(maxsize=32)
def font(size):
    return ImageFont.truetype(str(FONT), size)


def fit(value, width, size):
    value = str(value).replace('\n', ' ').replace('\r', ' ')
    selected = font(size)
    if selected.getlength(value) <= width:
        return value
    # Ellipsis is visual only. Full labels remain in Markdown and SVG titles.
    low, high = 0, len(value)
    while low < high:
        mid = (low + high + 1) // 2
        if selected.getlength(value[:mid] + '…') <= width:
            low = mid
        else:
            high = mid - 1
    return value[:low] + '…'


def render(scene):
    width, height = scene['width'], scene['height']
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise ValueError('Diagram dimensions exceed the local renderer limit')
    image = Image.new('RGB', (width, height), '#ffffff')
    draw = ImageDraw.Draw(image)
    svg = ET.Element('svg', xmlns='http://www.w3.org/2000/svg', width=str(width), height=str(height), viewBox=f'0 0 {width} {height}', role='img')
    ET.SubElement(svg, 'title').text = scene['title']
    ET.SubElement(svg, 'rect', width='100%', height='100%', fill='#ffffff')
    for item in scene['items']:
        kind = item['type']
        if kind == 'rect':
            x, y, w, h = (item[k] for k in ('x', 'y', 'w', 'h'))
            draw.rectangle((x, y, x+w, y+h), fill=item['fill'], outline=item['stroke'])
            ET.SubElement(svg, 'rect', x=str(x), y=str(y), width=str(w), height=str(h), fill=item['fill'], stroke=item['stroke'])
        elif kind == 'line':
            points = [(p['x'], p['y']) for p in item['points']]
            draw.line(points, fill=item['color'], width=item['width'])
            ET.SubElement(svg, 'polyline', points=' '.join(f'{x},{y}' for x,y in points), fill='none', stroke=item['color'], **{'stroke-width':str(item['width'])})
        elif kind == 'text':
            label = fit(item['text'], item['width'], item['size'])
            draw.text((item['x'], item['y']), label, font=font(item['size']), fill=item['color'], anchor='lt')
            node = ET.SubElement(svg, 'text', x=str(item['x']), y=str(item['y']+item['size']), fill=item['color'], **{'font-size':str(item['size']), 'font-family':'DejaVu Sans, sans-serif'})
            node.text = label
            ET.SubElement(node, 'title').text = item['text']
    output = io.BytesIO()
    image.save(output, format='PNG', optimize=False, compress_level=6)
    return {'png':output.getvalue(), 'svg':ET.tostring(svg, encoding='utf-8', xml_declaration=True)}


def generate(snapshot):
    from .repository import Invalid
    data = snapshot.get('diagramData')
    if not data or not any(data.get(key) for key in ('racks','devices','connections','networks')):
        return [], {}, {'layoutVersion':1,'rendererVersion':3}
    try:
        result = subprocess.run(['node', str(LAYOUT)], input=json.dumps(data), text=True,
                                capture_output=True, timeout=30, check=True)
        output = json.loads(result.stdout)
        scenes = output['pages']
        if len(scenes) > MAX_PAGES:
            raise Invalid('This export exceeds 512 diagram pages. Choose a smaller rack, device or network scope.')
        assets, files, total = [], {}, 0
        for scene in scenes:
            rendered = render(scene)
            asset = {key:scene[key] for key in ('id','title','chapter','references')}
            asset['files'] = {}
            for extension, content in rendered.items():
                digest = hashlib.sha256(content).hexdigest()
                path = f'assets/{scene["id"]}-{digest[:16]}.{extension}'
                files[path] = content
                total += len(content)
                if total > MAX_ASSET_BYTES:
                    raise Invalid('Diagram assets exceed 64 MiB. Choose a smaller scope.')
                asset['files'][extension] = path
            assets.append(asset)
        # Pin the renderer and every imported geometry dependency with this revision.
        dependencies = [LAYOUT, LAYOUT.parents[2]/'src/tools/dc-inventory/connectionLayout.js', LAYOUT.parents[2]/'src/tools/dc-inventory/rackLogic.js']
        metadata = {'layoutVersion':data.get('layoutVersion',1),'rendererVersion':3,'pillowVersion':pillow_version,'nodeVersion':output['nodeVersion'],
                    'rendererSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'fontSha256':hashlib.sha256(FONT.read_bytes()).hexdigest(),
                    'layoutSha256':hashlib.sha256(b''.join(p.read_bytes() for p in dependencies)).hexdigest()}
        return assets, files, metadata
    except subprocess.CalledProcessError as exc:
        if 'Diagram page limit exceeded' in (exc.stderr or ''):
            raise Invalid('This export exceeds 512 diagram pages. Choose a smaller rack, device or network scope.') from exc
        raise Invalid('Local diagram layout failed; no version was saved. Check the installed application files and Node.js.') from exc
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise Invalid('Local diagram rendering failed. Check Node.js, Pillow and the DejaVu Sans font; no version was saved.') from exc
