"""Seeded bag selection, plain A4 pages and multipage raster PDF."""
import json, random
from pathlib import Path
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont


def render(text_file,font_dir,out,seed=20261013,dpi=300):
    if dpi<72 or dpi>600: raise ValueError("dpi must be between 72 and 600")
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    text=Path(text_file).read_text(encoding="utf-8-sig").replace("\r\n","\n").replace("\r","\n").replace("\t","    ")
    paths=[Path(font_dir)/f"V{i}.ttf" for i in range(5)]
    cmaps=[]
    for path in paths:
        with TTFont(path) as font:cmaps.append(font.getBestCmap())
    missing=sorted({ch for ch in text if not ch.isspace() and any(ord(ch) not in cmap for cmap in cmaps)})
    if missing: raise ValueError("Missing glyphs; extend font first: "+"".join(missing))
    scale=dpi/300;width=round(2480*scale);height=round(3508*scale)
    margin=round(236*scale);line_height=round(132*scale);size=round(76*scale)
    fonts=[ImageFont.truetype(str(p),size) for p in paths];rng=random.Random(seed);bags=defaultdict(list)
    pages=[];page=Image.new("RGB",(width,height),"white");x=margin;y=margin;records=[]
    for index,ch in enumerate(text):
        if ch=="\n":x=margin;y+=line_height
        elif ch.isspace():x+=fonts[0].getlength(" ")
        else:
            if not bags[ch]:bags[ch]=list(range(5));rng.shuffle(bags[ch])
            v=bags[ch].pop();font=fonts[v];advance=font.getlength(ch)
            if x+advance>width-margin:x=margin;y+=line_height
            if y+size*1.4>height-margin:pages.append(page);page=Image.new("RGB",(width,height),"white");x=margin;y=margin
            # Draw into a padded tile so tiny rotations cannot cut off glyph strokes.
            bbox=font.getbbox(ch);pad=round(12*scale)
            tile=Image.new("RGBA",(bbox[2]-bbox[0]+2*pad,bbox[3]-bbox[1]+2*pad),(255,255,255,0))
            ImageDraw.Draw(tile).text((pad-bbox[0],pad-bbox[1]),ch,font=font,fill=(20,20,20,255))
            angle=rng.uniform(-.25,.25);tile=tile.rotate(angle,resample=Image.Resampling.BICUBIC,expand=True)
            px=round(x+bbox[0]-pad);py=round(y+bbox[1]-pad+rng.uniform(-1.2,1.2)*scale)
            page.paste(tile,(px,py),tile)
            records.append({"index":index,"char":ch,"variant":v,"page":len(pages)+1,"x":round(x,2),"y":y,"angle":round(angle,4)})
            x+=advance
        if y+size*1.4>height-margin:
            pages.append(page);page=Image.new("RGB",(width,height),"white");x=margin;y=margin
    # Avoid adding an empty final page after a newline at the page boundary.
    if page.getextrema()!=((255,255),(255,255),(255,255)) or not pages:pages.append(page)
    for i,p in enumerate(pages):p.save(out/f"page-{i+1:03}.png",dpi=(dpi,dpi))
    pages[0].save(out/"manuscript.pdf",save_all=True,append_images=pages[1:],resolution=dpi)
    (out/"layout.json").write_text(json.dumps({"seed":seed,"dpi":dpi,"pages":len(pages),"size":[width,height],"source_text":text,"placements":records},ensure_ascii=False,indent=2),encoding="utf-8")
    return {"pages":len(pages),"characters":len(records),"pdf":str(out/"manuscript.pdf")}
