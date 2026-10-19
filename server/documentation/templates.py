import json
from pathlib import Path
TEMPLATES=json.loads(Path(__file__).with_name('templates.json').read_text())
TEMPLATES['network']['pages']=json.loads(Path(__file__).with_name('chapters.json').read_text())

NETWORK_SUBNET_PAGES=json.loads(json.dumps(TEMPLATES['network']['pages']))
for page in NETWORK_SUBNET_PAGES:
    for section in page['sections']:
        for field in section['fields']:
            if field['id']=='dcName':field['label']='Network name / CIDR'


def chapters(form):
    if form.get('templateId','network')=='network' and form.get('scopeSpec',{}).get('kind')=='subnet':return NETWORK_SUBNET_PAGES
    return TEMPLATES[form.get('templateId','network')]['pages']


def fields(form):return [f for page in chapters(form) for section in page['sections'] for f in section['fields']]


def value(form,field):return form.get('templateNotes',{}).get(field['id'],'') if field.get('note') else form.get(field['id'],'')


def completeness(document):
    form=document['form'];blocking=[]
    for key,label in [('title','Document title'),('purpose','Purpose'),('ownerTeam','Responsible team')]:
        if not str(form.get(key,'')).strip():blocking.append({'field':key,'message':label+' is required for review.','chapter':'general'})
    if form.get('templateId','network')!='runbook' and not form.get('dcName','').strip():blocking.append({'field':'dcName','message':'Documented DC / device name is required.','chapter':'general'})
    for page in chapters(form):
        for section in page['sections']:
            for field in section['fields']:
                if field.get('requiredForReview') and not str(value(form,field)).strip():blocking.append({'field':field['id'],'message':field['label']+' is required for review.','chapter':page['id']})
    return {'blocking':blocking,'advisories':document.get('snapshot',{}).get('warnings',[]),'ready':not blocking}
