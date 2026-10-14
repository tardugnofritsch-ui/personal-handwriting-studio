"""Explicit grid collection and reviewed glyph ingestion; no guessed OCR labels."""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


def characters(path):
    return list(dict.fromkeys(c for c in Path(path).read_text(encoding="utf-8-sig") if not c.isspace()))


def normalize(image):
    image = ImageOps.exif_transpose(image).convert("L")
    a = np.asarray(image)
    y, x = np.where(a < 170)
    if not len(x):
        raise ValueError("Empty handwriting crop")
    crop = image.crop((int(x.min()), int(y.min()), int(x.max())+1, int(y.max())+1))
    crop.thumbnail((104, 104), Image.Resampling.LANCZOS)
    result = Image.new("L", (128, 128), 255)
    result.paste(crop, ((128-crop.width)//2, (128-crop.height)//2))
    return result


def template(chars_file, font_file, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    chars = characters(chars_file)
    if not chars:
        raise ValueError("Character list is empty")
    font = ImageFont.truetype(str(font_file), 38)
    rows, cols, size, left, top = 10, 8, 235, 300, 450
    pages = []
    for start in range(0, len(chars), rows*cols):
        image = Image.new("RGB", (2480,3508), "white"); draw = ImageDraw.Draw(image)
        draw.text((left,180), "Handwriting collection - write inside each empty cell", fill="black")
        cells=[]
        for i, ch in enumerate(chars[start:start+rows*cols]):
            x=left+(i%cols)*size; y=top+(i//cols)*size
            draw.rectangle((x,y,x+size,y+size),outline="#888888",width=2)
            draw.text((x+8,y+5),ch,font=font,fill="#777777")
            cells.append({"char":ch,"box":[x+10,y+60,x+size-10,y+size-10]})
        filename=f"template-{start//(rows*cols)+1:03}.png"
        image.save(out/filename,dpi=(300,300));pages.append(image)
        (out/filename.replace(".png",".json")).write_text(json.dumps({"size":[2480,3508],"cells":cells},ensure_ascii=False,indent=2),encoding="utf-8")
    pages[0].save(out/"templates.pdf",save_all=True,append_images=pages[1:],resolution=300)


def extract(scan, grid, out):
    """Scan must be manually aligned to original template; boxes are explicit."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    spec=json.loads(Path(grid).read_text(encoding="utf-8"))
    image=ImageOps.exif_transpose(Image.open(scan)).convert("L")
    if list(image.size)!=spec["size"]:
        raise ValueError(f"Align scan to {spec['size']} before cropping (got {image.size})")
    manifest=[]
    for i,cell in enumerate(spec["cells"]):
        ch=cell["char"]
        if len(ch)!=1: raise ValueError("Grid labels must contain one Unicode character")
        filename=f"U{ord(ch):04X}-{i:03}.png"
        normalize(image.crop(tuple(cell["box"]))).save(out/filename)
        manifest.append({"char":ch,"file":filename})
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    review(manifest,out,out/"review.png")


def review(records,root,path):
    image=Image.new("RGB",(8*150, max(1,(len(records)+7)//8)*170),"white");draw=ImageDraw.Draw(image)
    for i,r in enumerate(records):
        x=i%8*150;y=i//8*170
        draw.text((x+8,y+2),f"U+{ord(r['char']):04X}",fill="black")
        with Image.open(Path(root)/r["file"]) as crop: image.paste(crop.convert("RGB").resize((128,128)),(x+8,y+24))
    image.save(path)


def load_manifest(path):
    path=Path(path); rows=json.loads(path.read_text(encoding="utf-8")); result=[]
    for row in rows:
        if len(row["char"])!=1 or row["char"].isspace(): raise ValueError("Each sample needs a non-whitespace Unicode character")
        file=(path.parent/row["file"]).resolve()
        if not file.is_relative_to(path.parent.resolve()): raise ValueError("Sample path must stay within manifest directory")
        with Image.open(file) as image: crop=normalize(image)
        result.append({"char":row["char"],"image":crop})
    if not result: raise ValueError("No samples in manifest")
    return result
