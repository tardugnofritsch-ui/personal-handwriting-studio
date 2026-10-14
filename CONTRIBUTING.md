# Contributing

Use Python 3.10+, install with `pip install -e .`, and run `python -m unittest discover -s tests -v` before opening a PR.

Keep sample scans, private fonts, trained personal checkpoints and manuscript contents outside commits. Add regression tests for coverage errors, Unicode preservation and page clipping when changing those paths. Clearly label inference, training, synthetic glyphs and real exemplars. Preserve third-party notices.

Please describe the concrete change and its validation. Do not claim a general font-quality improvement based only on a few attractive glyphs.
