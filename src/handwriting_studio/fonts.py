"""Bitmap font construction and conservative five-way outline variation."""
import copy, json, math
from pathlib import Path
from array import array
import cv2
import numpy as np
from PIL import Image
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from .samples import characters, load_manifest


def build_font(glyph_dir, chars_file, target, manifest=None, family="User Handwriting"):
    glyph_dir=Path(glyph_dir); target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    own={r["char"]:r["image"] for r in load_manifest(manifest)} if manifest else {}
    glyphs={};metrics={};cmap={};provenance={}
    pen=TTGlyphPen(None);glyphs[".notdef"]=pen.glyph();metrics[".notdef"]=(1000,0)
    pen=TTGlyphPen(None);glyphs["space"]=pen.glyph();metrics["space"]=(500,0);cmap[32]="space"
    for ch in characters(chars_file):
        image=own.get(ch)
        if image is None:
            path=glyph_dir/f"U{ord(ch):04X}.png"
            if not path.exists(): raise ValueError(f"Missing glyph {ch} U+{ord(ch):04X}; no silent fallback")
            with Image.open(path) as source: image=source.convert("L")
        mask=(np.asarray(image)<170).astype("uint8")
        yy,xx=np.where(mask)
        if not len(xx): raise ValueError(f"Blank glyph: {ch}")
        contours,hierarchy=cv2.findContours(mask,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
        bx,by=int(xx.min()),int(yy.min());bw,bh=int(xx.max()-bx+1),int(yy.max()-by+1)
        # Retain common canvas scale: punctuation must not inflate to full character height.
        scale=850/max(image.size); left=(1000-image.width*scale)/2; top=900
        pen=TTGlyphPen(None);count=0
        for contour in contours:
            points=cv2.approxPolyDP(contour,.35,True).reshape(-1,2)
            if len(points)<3 or cv2.contourArea(contour)<.5: continue
            pts=[(round(left+float(x)*scale),round(top-float(y)*scale)) for x,y in points]
            pen.moveTo(pts[0])
            for pt in pts[1:]: pen.lineTo(pt)
            pen.closePath();count+=1
        if not count: raise ValueError(f"No usable contours: {ch}")
        name=f"uni{ord(ch):04X}";g=pen.glyph();g.recalcBounds(None)
        glyphs[name]=g;metrics[name]=(1000,g.xMin);cmap[ord(ch)]=name
        provenance[ch]="real_sample" if ch in own else "supplied_glyph_bitmap"
    fb=FontBuilder(1000,isTTF=True);fb.setupGlyphOrder(list(glyphs));fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs);fb.setupHorizontalMetrics(metrics);fb.setupHorizontalHeader(ascent=1000,descent=-200)
    ps="".join(c for c in family if c.isascii() and c.isalnum()) or "UserHandwriting"
    fb.setupNameTable({"familyName":family,"styleName":"Regular","uniqueFontIdentifier":ps+"-0.1","fullName":family+" Regular","psName":ps+"-Regular","version":"Version 0.1"})
    fb.setupOS2(sTypoAscender=1000,sTypoDescender=-200,usWinAscent=1000,usWinDescent=200)
    fb.setupPost();fb.setupMaxp();fb.save(target)
    target.with_suffix(".sources.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding="utf-8")


def variants(font_file,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with TTFont(font_file) as base:
        if "glyf" not in base: raise ValueError("Variants require TrueType glyf outlines; CFF/OTF is not supported")
        units=base["head"].unitsPerEm/1000; specs=[(1,1,0),(.97,1.008,.020),(1.018,.978,-.017),(1.025,1.008,.028),(.977,.983,-.026)]
        for v,(sx,sy,slant) in enumerate(specs):
            font=copy.deepcopy(base)
            # Distinct names prevent browser/OS font cache collisions.
            family=f"Gentle Handwriting V{v}"
            for id_,value in [(1,family),(2,"Regular"),(3,family.replace(" ","")),(4,family),(6,family.replace(" ",""))]:
                font["name"].setName(value,id_,3,1,0x409);font["name"].setName(value,id_,1,0,0)
            if v:
                for name in font.getGlyphOrder():
                    original=base["glyf"][name]
                    if original.isComposite() or not original.numberOfContours: continue
                    coords,ends,flags=original.getCoordinates(base["glyf"]);a=np.asarray(coords,dtype=float)
                    if all(int(f)&1 for f in flags):
                        points=[];newends=[];start=0
                        for end in ends:
                            contour=a[start:end+1]
                            for p,q in zip(contour,np.roll(contour,-1,axis=0)):
                                steps=max(1,math.ceil(float(np.linalg.norm(q-p))/(35*units)))
                                points.extend(p+(q-p)*t/steps for t in range(steps))
                            newends.append(len(points)-1);start=end+1
                        a=np.asarray(points);ends=newends;flags=array("B",[1]*len(a))
                    cx=(original.xMin+original.xMax)/2;cy=(original.yMin+original.yMax)/2
                    w=max(1,original.xMax-original.xMin);h=max(1,original.yMax-original.yMin)
                    phases=np.random.default_rng(sum(map(ord,name))*13+v*271).uniform(-math.pi,math.pi,4)
                    u=(a[:,0]-cx)/w;t=(a[:,1]-cy)/h
                    dx=(a[:,0]-cx)*(sx-1)+slant*(a[:,1]-cy)+min(9*units,w*.019,h*.014)*np.sin(t*math.pi*1.4+phases[0])+min(4*units,w*.009)*np.sin(u*math.pi*1.6+phases[1])
                    dy=(a[:,1]-cy)*(sy-1)+min(8*units,w*.018,h*.012)*np.sin(u*math.pi*1.5+phases[2])+min(4*units,h*.006)*np.sin(t*math.pi*1.3+phases[3])
                    b=np.rint(a+np.column_stack([dx,dy]));aw=base["hmtx"][name][0];margin=15*units
                    if aw>2*margin and (b[:,0].min()<margin or b[:,0].max()>aw-margin):
                        mn=b[:,0].min();span=b[:,0].max()-mn
                        b[:,0]=np.rint(margin+(b[:,0]-mn)*min(1,(aw-2*margin)/max(1,span)))
                    g=font["glyf"][name];g.coordinates=GlyphCoordinates(b.tolist());g.endPtsOfContours=ends;g.flags=flags;g.recalcBounds(None)
                    font["hmtx"][name]=(aw,g.xMin)
            font.save(out/f"V{v}.ttf");font.close()
    (out/"variants.json").write_text(json.dumps({"method":"geometric_variants_not_training","count":5,"wave_max_per_1000_upem":[9,8],"composite_glyphs":"unchanged"},indent=2),encoding="utf-8")


def audit(font_file,chars_file):
    with TTFont(font_file) as font:
        cmap=font.getBestCmap();missing=[ch for ch in characters(chars_file) if ord(ch) not in cmap]
        blank=[ch for ch in characters(chars_file) if ord(ch) in cmap and "glyf" in font and not font["glyf"][cmap[ord(ch)]].numberOfContours]
    result={"missing":missing,"blank":blank,"passed":not missing and not blank}
    if not result["passed"]: raise ValueError(json.dumps(result,ensure_ascii=False))
    return result
