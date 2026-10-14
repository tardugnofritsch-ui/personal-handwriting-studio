import json,tempfile,unittest
from pathlib import Path
from PIL import Image,ImageDraw
from fontTools.ttLib import TTFont
from handwriting_studio.fonts import build_font,variants,audit
from handwriting_studio.render import render
from handwriting_studio.samples import extract,load_manifest


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.glyphs=self.root/'glyphs';self.glyphs.mkdir()
        self.chars=self.root/'chars.txt';self.chars.write_text('你好AB12=',encoding='utf-8')
        for i,ch in enumerate('你好AB12='):
            image=Image.new('L',(128,128),255);d=ImageDraw.Draw(image)
            d.rectangle((20+i,25,40+i,100),fill=0);d.rectangle((20,30+i,100,45+i),fill=0)
            image.save(self.glyphs/f'U{ord(ch):04X}.png')
        self.font=self.root/'base.ttf';build_font(self.glyphs,self.chars,self.font)
    def tearDown(self):self.temp.cleanup()
    def test_font_variants_coverage_and_outline(self):
        bank=self.root/'bank';variants(self.font,bank)
        for v in range(5):self.assertTrue(audit(bank/f'V{v}.ttf',self.chars)['passed'])
        with TTFont(self.font) as a,TTFont(bank/'V0.ttf') as b:
            self.assertEqual(a['glyf']['uni4F60'].coordinates,b['glyf']['uni4F60'].coordinates)
        with TTFont(bank/'V1.ttf') as b:
            self.assertNotEqual(a['glyf']['uni4F60'].coordinates,b['glyf']['uni4F60'].coordinates)
    def test_render_unicode_reproducibility_and_pagination(self):
        bank=self.root/'bank';variants(self.font,bank)
        text=self.root/'text.txt';text.write_text(('你好AB12=\n'*40),encoding='utf-8')
        one=self.root/'one';two=self.root/'two';r=render(text,bank,one,dpi=72);render(text,bank,two,dpi=72)
        self.assertGreater(r['pages'],1)
        self.assertEqual((one/'page-001.png').read_bytes(),(two/'page-001.png').read_bytes())
        record=json.loads((one/'layout.json').read_text(encoding='utf-8'))
        self.assertEqual(''.join(p['char'] for p in record['placements']),text.read_text(encoding='utf-8').replace('\n',''))
        self.assertTrue((one/'manuscript.pdf').read_bytes().startswith(b'%PDF'))
    def test_missing_glyph_is_rejected(self):
        bank=self.root/'bank';variants(self.font,bank);text=self.root/'text.txt';text.write_text('缺',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Missing glyphs'):render(text,bank,self.root/'out')
    def test_explicit_crop_and_path_validation(self):
        scan=self.root/'scan.png';Image.open(self.glyphs/'U0041.png').save(scan)
        grid=self.root/'grid.json';grid.write_text(json.dumps({'size':[128,128],'cells':[{'char':'A','box':[0,0,128,128]}]}))
        out=self.root/'samples';extract(scan,grid,out);self.assertEqual(load_manifest(out/'manifest.json')[0]['char'],'A')
        (out/'manifest.json').write_text(json.dumps([{'char':'A','file':'../scan.png'}]))
        with self.assertRaisesRegex(ValueError,'within manifest'):load_manifest(out/'manifest.json')


if __name__=='__main__':unittest.main()
