#!/usr/bin/env python3
"""Derive actual Xcursor pixels; never changes desktop settings."""
import argparse, hashlib, json, struct
from pathlib import Path
from PIL import Image, ImageFilter
MAGIC=0x72756358
IMAGE=0xfffd0002

def transform(data):
    if len(data)>16*1024*1024 or len(data)<16: raise ValueError('cursor size')
    magic,header,version,count=struct.unpack_from('<4I',data)
    if magic!=MAGIC or header<16 or count>1024 or header+count*12>len(data): raise ValueError('cursor header')
    out=bytearray(data); frames=[]
    for i in range(count):
        kind,size,offset=struct.unpack_from('<3I',data,header+i*12)
        if kind!=IMAGE: continue
        if offset+36>len(data): raise ValueError('image header')
        ch,ct,sub,cv,w,h,x,y,delay=struct.unpack_from('<9I',data,offset)
        if ch<36 or ct!=IMAGE or not 0<w<=512 or not 0<h<=512 or x>=w or y>=h: raise ValueError('image geometry')
        start=offset+ch; end=start+w*h*4
        if end>len(data): raise ValueError('truncated pixels')
        raw=data[start:end]
        # Xcursor pixels are little-endian premultiplied ARGB (BGRA bytes).
        rgba=bytearray()
        for b,g,r,a in struct.iter_unpack('4B',raw):
            rgba.extend((min(255,round(r*255/a)) if a else 0,min(255,round(g*255/a)) if a else 0,min(255,round(b*255/a)) if a else 0,a))
        image=Image.frombytes('RGBA',(w,h),bytes(rgba)); alpha=image.getchannel('A')
        if not alpha.getbbox(): raise ValueError('blank source cursor')
        glow=Image.new('RGBA',(w,h),(30,190,255,0)); glow.putalpha(alpha.filter(ImageFilter.GaussianBlur(max(1,size/12))).point(lambda v: min(190,round(v*1.7))))
        merged=Image.alpha_composite(glow,image); pixels=bytearray()
        for r,g,b,a in getattr(merged,'get_flattened_data',merged.getdata)(): pixels.extend((round(b*a/255),round(g*a/255),round(r*a/255),a))
        out[start:end]=pixels; frames.append(dict(size=size,width=w,height=h,hotspot=[x,y],delay=delay))
    if not frames: raise ValueError('no cursor frames')
    return bytes(out),frames

def build(source,dest,name):
    source=Path(source).resolve(); dest=Path(dest)
    if dest.exists(): raise ValueError('destination exists')
    entries=list((source/'cursors').iterdir())
    if len(entries)>4096: raise ValueError('too many cursor files')
    dest.mkdir(parents=True); (dest/'cursors').mkdir(); manifest={}
    for entry in entries:
        resolved=entry.resolve()
        if not resolved.is_relative_to(source): raise ValueError('external cursor alias')
        if entry.is_symlink():
            # Resolve aliases to a local filename; no absolute or escaping links.
            (dest/'cursors'/entry.name).symlink_to(resolved.name); continue
        if entry.stat().st_size>16*1024*1024:raise ValueError('cursor size')
        data=entry.read_bytes()
        if len(data)>16*1024*1024: raise ValueError('cursor size')
        if data[:4]!=b'Xcur':
            if entry.suffix not in ('.cur','.ani'):raise ValueError('unknown cursor format')
            (dest/'cursors'/entry.name).write_bytes(data);continue
        result,frames=transform(data)
        (dest/'cursors'/entry.name).write_bytes(result)
        manifest[entry.name]={'source_sha256':hashlib.sha256(data).hexdigest(),'frames':frames}
    (dest/'index.theme').write_text('[Icon Theme]\nName='+name+'\nComment=Temporary actual cursor glow derived from Yaru\n')
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('source');p.add_argument('dest');p.add_argument('--name',required=True);a=p.parse_args();build(a.source,a.dest,a.name)
