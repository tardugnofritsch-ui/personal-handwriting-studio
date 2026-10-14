import argparse,json
from .samples import template,extract
from .fonts import build_font,variants,audit
from .render import render


def main():
    parser=argparse.ArgumentParser(description="Personal handwriting collection, learning, fonts and A4 manuscripts")
    commands=parser.add_subparsers(dest="command",required=True)
    p=commands.add_parser("template",help="Create labeled blank A4 collection sheets")
    p.add_argument("--chars",required=True);p.add_argument("--font",required=True);p.add_argument("--out",required=True)
    p=commands.add_parser("extract",help="Crop a manually aligned template scan")
    p.add_argument("--scan",required=True);p.add_argument("--grid",required=True);p.add_argument("--out",required=True)
    p=commands.add_parser("learn",help="MX-Font few-shot inference or optional decoder fine-tuning")
    p.add_argument("--manifest",required=True);p.add_argument("--checkpoint",required=True);p.add_argument("--source-font",required=True)
    p.add_argument("--chars",required=True);p.add_argument("--out",required=True);p.add_argument("--steps",type=int,default=0)
    p.add_argument("--seed",type=int,default=19);p.add_argument("--batch-size",type=int,default=4)
    p=commands.add_parser("font",help="Build TTF from bitmaps, preferring real reviewed samples")
    p.add_argument("--glyphs",required=True);p.add_argument("--chars",required=True);p.add_argument("--out",required=True)
    p.add_argument("--manifest");p.add_argument("--family",default="User Handwriting")
    p=commands.add_parser("variants",help="Create all-character gentle variants V0-V4 (not training)")
    p.add_argument("--font",required=True);p.add_argument("--out",required=True)
    p=commands.add_parser("audit",help="Fail on missing or blank requested glyphs")
    p.add_argument("--font",required=True);p.add_argument("--chars",required=True)
    p=commands.add_parser("render",help="Generate white A4 PNG pages and PDF")
    p.add_argument("--text",required=True);p.add_argument("--fonts",required=True);p.add_argument("--out",required=True)
    p.add_argument("--seed",type=int,default=20261013);p.add_argument("--dpi",type=int,default=300)
    a=parser.parse_args()
    try:
        if a.command=="template":template(a.chars,a.font,a.out)
        elif a.command=="extract":extract(a.scan,a.grid,a.out)
        elif a.command=="learn":
            from .ai import learn
            learn(a.manifest,a.checkpoint,a.source_font,a.chars,a.out,a.steps,a.seed,a.batch_size)
        elif a.command=="font":build_font(a.glyphs,a.chars,a.out,a.manifest,a.family)
        elif a.command=="variants":variants(a.font,a.out)
        elif a.command=="audit":print(json.dumps(audit(a.font,a.chars),ensure_ascii=False))
        elif a.command=="render":print(json.dumps(render(a.text,a.fonts,a.out,a.seed,a.dpi),ensure_ascii=False))
    except (ValueError,FileNotFoundError,ImportError) as error:parser.exit(2,f"Error: {error}\n")

