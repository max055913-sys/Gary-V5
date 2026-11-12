"""Export local d'un instantané DOM de la réponse affichée, sans JavaScript."""
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import re
from .commercial_supervisor import require
from .live_supervisor import ROOT
from .live_evidence import attach_visual

class Snapshot(HTMLParser):
    TAGS={'article','section','div','span','p','h1','h2','h3','h4','h5','h6','a','strong','em','b','i','ul','ol','li','table','thead','tbody','tr','th','td','br','pre','code','blockquote','dl','dt','dd','hr','details','summary'}
    def __init__(self):
        super().__init__(convert_charrefs=True);self.out=[];self.stack=[];self.original=[];self.marked=0
    def handle_starttag(self,tag,attrs):
        require(tag in self.TAGS,'SNAPSHOT_TAG_REFUSED')
        attrs=dict(attrs);marked=attrs.get('data-original-text')=='true'
        if marked:self.marked+=1
        self.stack.append((tag,marked))
        kept=[]
        if 'open' in attrs:kept.append('open')
        for k in ('style','href','colspan','rowspan','start','value','data-original-text','class'):
            if k in attrs:
                v=attrs[k]
                require(type(v) is str and 'url(' not in v.lower() and '@import' not in v.lower(),'SNAPSHOT_STYLE_REFUSED')
                kept.append(k+'="'+escape(v,quote=True)+'"')
        self.out.append('<'+tag+(' '+' '.join(kept) if kept else '')+'>')
        if tag in ('br','hr'):self.stack.pop()
    def handle_endtag(self,tag):
        require(self.stack and self.stack[-1][0]==tag,'SNAPSHOT_STRUCTURE_INVALID')
        self.stack.pop();self.out.append('</'+tag+'>')
    def handle_data(self,data):
        self.out.append(escape(data))
        if any(mark for tag,mark in self.stack):self.original.append(data)

def render_only(directory,html,width,expected_text,*,background,test,pdf_name=None):
    require(type(background) is str and re.fullmatch(r'rgba?\([0-9., %]+\)',background),'SNAPSHOT_BACKGROUND_INVALID')
    require(type(html) is str and len(html)<=2_000_000 and type(width) is int and 200<=width<=4096,'SNAPSHOT_INVALID')
    parser=Snapshot();parser.feed(html);parser.close()
    require(not parser.stack and parser.marked==1 and ''.join(parser.original)==expected_text,'SNAPSHOT_TEXT_MISMATCH')
    p=Path(directory)
    for n in ['presentation_affichee.html','capture_reference.png','Gary_TEST_reponse_originale.pdf','Gary_reponse_originale.pdf','Fiche_patient.pdf']:
        require(not (p/n).exists(),'VISUAL_EXPORT_ALREADY_STARTED')
    (p/'presentation_affichee.html').write_text(''.join(parser.out),encoding='utf8',newline='')
    node=Path(os.environ.get('GARY_PDF_NODE') or ROOT/'runtime/node/node.exe')
    require(node.is_file(),'LOCAL_RENDERER_UNAVAILABLE')
    require(pdf_name in (None,'Fiche_patient.pdf'),'PDF_NAME_INVALID')
    result=subprocess.run([str(node),str(ROOT/'gary_v5/render_snapshot.mjs')],input=json.dumps({'directory':str(p),'width':width,'test':test,'background':background,'pdf_name':pdf_name}),text=True,encoding='utf8',capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    require(result.returncode==0,'VISUAL_EXPORT_FAILED_ORIGINALS_PRESERVED')
    observation=json.loads((p/'render_observation.json').read_text('utf8'))
    return observation


def capture(directory,html,width,expected_text,*,background,test):
    observation=render_only(directory,html,width,expected_text,background=background,test=test)
    p=Path(directory)
    name='Gary_TEST_reponse_originale.pdf' if test else 'Gary_reponse_originale.pdf'
    return attach_visual(p,test=test,pdf=name,captures=['capture_reference.png'],observation=observation)
