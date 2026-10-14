"""Few-shot MX-Font inference and optional structure-preserving personal fine-tuning.

Adapted from the original project experiments. The pretrained network is supplied
separately. Geometric variation is implemented elsewhere and is never training.
"""
import copy, hashlib, json, random
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from .samples import characters, load_manifest


def learn(manifest,checkpoint,source_font,chars_file,out,steps=0,seed=19,batch_size=4):
    import torch
    from ._mxfont.models import Generator
    if steps<0 or batch_size<1: raise ValueError("steps >= 0 and batch-size >= 1 required")
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    records=load_manifest(manifest)
    # All repeated exemplars of one character belong to the same split.
    labels=sorted({r["char"] for r in records});rng=random.Random(seed);rng.shuffle(labels)
    if steps and len(labels)<10: raise ValueError("Fine-tuning needs at least 10 distinct reviewed sample characters")
    held=max(1,len(labels)//10) if steps else 0
    val=set(labels[:held]);test=set(labels[held:2*held]);train=set(labels[2*held:])
    training=[r for r in records if r["char"] in train]
    targets=characters(chars_file)
    if not targets: raise ValueError("Character list is empty")
    with TTFont(source_font) as font:
        supported=font.getBestCmap()
        missing=[c for c in set(targets)|set(labels) if ord(c) not in supported]
    if missing: raise ValueError("Source font lacks: "+"".join(sorted(missing)))
    device="cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(4);torch.manual_seed(seed)
    if device=="cuda": torch.cuda.manual_seed_all(seed)
    base={"norm":"in","activ":"relu","pad_type":"zero","skip_scale_var":False}
    gen=Generator(1,32,1,style_enc=base,experts=dict(base,n_experts=6),emb_num=2,dec={"norm":"in","activ":"relu","pad_type":"zero","out":"sigmoid"}).to(device).eval()
    weights=torch.load(checkpoint,map_location="cpu",weights_only=True)
    if "generator_ema" in weights: weights=weights["generator_ema"]
    gen.load_state_dict(weights)
    font=ImageFont.truetype(str(source_font),150)
    def tensor(image):
        a=np.asarray(image.convert("L").resize((128,128)),dtype=np.float32)/255
        return torch.from_numpy(a.copy()).unsqueeze(0).to(device)*2-1
    def source(ch):
        width=int(font.getlength(ch));height=font.getbbox(ch)[3];m=max(width,height)
        image=Image.new("L",(m+40,m+40),255)
        x=(height-width)//2+20 if width<height else 20
        y=20 if width<height else (width-height)//2+20
        ImageDraw.Draw(image).text((x,y),ch,font=font,fill=0)
        return image.resize((128,128),Image.Resampling.BILINEAR)
    with torch.no_grad():
        style_parts={}
        for start in range(0,min(64,len(training)),batch_size):
            facts=gen.factorize(gen.encode(torch.stack([tensor(r["image"]) for r in training[start:min(start+batch_size,64)]])),0)
            for key,value in facts.items(): style_parts.setdefault(key,[]).append(value)
        style={key:torch.cat(value).mean(0,keepdim=True).detach() for key,value in style_parts.items()}
    def predict(chars,decoder=None):
        with torch.no_grad():
            content=gen.factorize(gen.encode(torch.stack([tensor(source(ch)) for ch in chars])),1)
            expanded={k:v.expand(len(chars),*v.shape[1:]) for k,v in style.items()}
            feats=gen.defactorize([expanded,content])
        dec=decoder or gen.decoder
        return dec(feats["last"],feats["skip"])
    # Decoder API takes expert features: identical to Generator.decode in upstream.
    teacher=copy.deepcopy(gen.decoder).eval()
    for p in gen.parameters(): p.requires_grad=False
    for p in teacher.parameters(): p.requires_grad=False
    for layer in list(gen.decoder.layers)[4:]:
        for p in layer.parameters(): p.requires_grad=True
    def loss_fn(pred,truth):
        ink=1-truth
        pixel=((pred-truth).abs()*(1+2*ink)).mean()
        mass=((1-pred).mean((1,2,3))-ink.mean((1,2,3))).abs().mean()
        dx=(pred[:,:,:,1:]-pred[:,:,:,:-1]-truth[:,:,:,1:]+truth[:,:,:,:-1]).abs().mean()
        dy=(pred[:,:,1:,:]-pred[:,:,:-1,:]-truth[:,:,1:,:]+truth[:,:,:-1,:]).abs().mean()
        return pixel+.6*mass+.2*(dx+dy)
    @torch.no_grad()
    def evaluate(split):
        selected=[r for r in records if r["char"] in split]
        total=0.;count=0
        for start in range(0,len(selected),batch_size):
            batch=selected[start:start+batch_size];pred=predict([r["char"] for r in batch])
            truth=torch.stack([(tensor(r["image"])+1)/2 for r in batch])
            total+=float(loss_fn(pred,truth))*len(batch);count+=len(batch)
        return total/count if count else None
    before={"validation":evaluate(val),"test":evaluate(test)}
    history=[]
    if steps:
        opt=torch.optim.Adam([p for p in gen.parameters() if p.requires_grad],lr=.00006)
        best_loss=before["validation"];best=copy.deepcopy(gen.decoder.state_dict())
        for step in range(1,steps+1):
            batch=rng.sample(training,min(batch_size,len(training)));chars=[r["char"] for r in batch]
            truth=torch.stack([(tensor(r["image"])+1)/2 for r in batch])
            opt.zero_grad();pred=predict(chars);fit=loss_fn(pred,truth)
            anchors=rng.sample(targets,min(batch_size,len(targets)))
            with torch.no_grad(): prior=predict(anchors,teacher)
            anchor=predict(anchors)
            preserve=(anchor-prior).abs().mean()
            mass=((1-anchor).mean((1,2,3))-(1-prior).mean((1,2,3))).abs().mean()
            fuzz=torch.relu((anchor*(1-anchor)).mean()-(prior*(1-prior)).mean())
            total=fit+.2*preserve+.8*mass+.8*fuzz
            total.backward();torch.nn.utils.clip_grad_norm_([p for p in gen.parameters() if p.requires_grad],.5);opt.step()
            if step%25==0 or step==steps:
                metric=evaluate(val);event={"step":step,"loss":float(total.detach()),"validation":metric};history.append(event);print(event,flush=True)
                if metric<best_loss:best_loss=metric;best=copy.deepcopy(gen.decoder.state_dict())
        gen.decoder.load_state_dict(best)
    glyph_dir=out/"glyphs";glyph_dir.mkdir(exist_ok=True)
    with torch.no_grad():
        for start in range(0,len(targets),batch_size):
            chars=targets[start:start+batch_size];pred=predict(chars)
            for i,ch in enumerate(chars):
                a=pred[i,0].cpu().numpy().copy()
                if not np.isfinite(a).all(): raise ValueError(f"Non-finite glyph {ch}")
                a[a>.8]=1;a[:2]=1;a[-2:]=1;a[:,:2]=1;a[:,-2:]=1
                Image.fromarray((a.clip(0,1)*255).astype("uint8")).save(glyph_dir/f"U{ord(ch):04X}.png")
            print(f"Generated {min(start+batch_size,len(targets))}/{len(targets)}",flush=True)
    torch.save({"decoder":gen.decoder.state_dict(),"style":style,"seed":seed},out/"personal.pt")
    record={"method":"decoder_finetuning" if steps else "pretrained_few_shot_inference","steps":steps,"seed":seed,"device":device,"sample_characters":len(labels),"train_characters":sorted(train),"validation_characters":sorted(val),"test_characters":sorted(test),"generated_characters":len(targets),"before":before,"after":{"validation":evaluate(val),"test":evaluate(test)},"history":history,"checkpoint_sha256":hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest(),"note":"Synthetic source characters preserve structure; only supplied handwriting is real supervision. Best validation decoder is selected; no quality guarantee."}
    (out/"training.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
