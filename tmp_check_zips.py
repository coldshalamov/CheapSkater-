import argparse
import yaml
from pathlib import Path
from app.main import _resolve_zips, _load_zip_resume, _infer_state_from_zip
from app.monitoring import ZipProgressTracker

with open('app/config.yml', 'r', encoding='utf-8') as handle:
    config = yaml.safe_load(handle)
args = argparse.Namespace(zips=[], concurrency=None, probe=False, validate=False, ignore_quarantine=False)
zips = _resolve_zips(args, config)
tracker = ZipProgressTracker(Path('logs/zip_cursor.json'), Path('logs/zip_history.json'), 90.0)
zips = tracker.interleave(zips, _infer_state_from_zip)
zips2, resume_marker = _load_zip_resume(zips)
print('resume_marker', resume_marker)
print('first 10', zips2[:10])
print('len', len(zips2))
