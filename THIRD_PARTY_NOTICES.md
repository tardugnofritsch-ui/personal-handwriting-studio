# Third-party notices

`src/handwriting_studio/_mxfont/models/` is derived from NAVER's MX-Font:

- Source: https://github.com/clovaai/mxfont
- Copied revision: `93f3c88517f7c904f16da6333adb2588dcdf3cce`
- Copyright (c) 2021-present NAVER Corp.
- License: MIT. Full license and subcomponent notices are preserved at `_mxfont/LICENSE` and `_mxfont/NOTICE`.
- Local modifications: generator imports the packaged relative helper module instead of a top-level `utils`; `helpers.py` is copied from upstream `utils/utils.py`. No pretrained weights are distributed.

The training wrapper, font builder and gentle variants are adapted from the user's original personal project scripts and reorganized for public reuse. Original handwriting scans, personal checkpoints, private fonts, assignment text and reference-font binaries are excluded.

The original project also used text2handwriting by rockbenben, and third-party fonts including Ma Shan Zheng, YShi Written and JasonHandwriting. Their app and font binaries are not redistributed in this repository. Users supply their own authorized input fonts and checkpoints; retain applicable licenses when sharing derived artifacts.
