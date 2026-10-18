#!/usr/bin/env python3
"""Regenerate and verify the committed Telethon layer 231 artifacts."""

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'generated-layer231-manifest.json'
RELEASE_DISTRIBUTION = 'Telethon'
RELEASE_VERSION = '1.45.0+tgsmm.layer231.3'
SOURCE_FILES = (
    'telethon_generator/data/api.tl',
    'telethon_generator/data/mtproto.tl',
    'telethon_generator/data/errors.csv',
    'telethon_generator/data/methods.csv',
    'telethon_generator/data/friendly.csv',
)
GENERATED_FILES = (
    'telethon/tl/alltlobjects.py',
    'telethon/errors/rpcerrorlist.py',
)
GENERATED_DIRS = (
    'telethon/tl/types',
    'telethon/tl/functions',
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generated_paths():
    paths = [ROOT / name for name in GENERATED_FILES]
    for name in GENERATED_DIRS:
        paths.extend(sorted((ROOT / name).rglob('*.py')))
    return sorted(paths)


def schema_counts():
    sys.path.insert(0, str(ROOT))
    from telethon_generator.parsers import (
        find_layer, parse_errors, parse_methods, parse_tl)

    tl_files = sorted((ROOT / 'telethon_generator/data').glob('*.tl'))
    layer = next(filter(None, (find_layer(path) for path in tl_files)))
    errors = list(parse_errors(ROOT / SOURCE_FILES[2]))
    methods = list(parse_methods(
        ROOT / SOURCE_FILES[3], ROOT / SOURCE_FILES[4],
        {error.str_code: error for error in errors}))
    objects = list(itertools.chain.from_iterable(
        parse_tl(path, layer, methods) for path in tl_files))
    return {
        'layer': layer,
        'tlobjects': len(objects),
        'constructors': sum(not obj.is_function for obj in objects),
        'functions': sum(obj.is_function for obj in objects),
        'rpc_errors': len(errors),
    }


def current_manifest():
    missing = [str(path.relative_to(ROOT)) for path in generated_paths()
               if not path.is_file()]
    if missing:
        raise SystemExit('missing generated files: {}'.format(', '.join(missing)))
    return {
        'format': 2,
        'generator_command': 'python3 setup.py gen tl errors',
        'release': {
            'distribution': RELEASE_DISTRIBUTION,
            'version': RELEASE_VERSION,
        },
        'schema': schema_counts(),
        'sources': {
            name: sha256(ROOT / name) for name in SOURCE_FILES
        },
        'generated': {
            str(path.relative_to(ROOT)): sha256(path)
            for path in generated_paths()
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--regenerate', action='store_true',
        help='run the canonical generator before checking')
    parser.add_argument(
        '--update', action='store_true',
        help='rewrite the manifest from the current source and output files')
    args = parser.parse_args()

    if args.regenerate:
        subprocess.run(
            [sys.executable, 'setup.py', 'gen', 'tl', 'errors'],
            cwd=ROOT, check=True)

    actual = current_manifest()
    if args.update:
        MANIFEST.write_text(
            json.dumps(actual, indent=2, sort_keys=True) + '\n',
            encoding='utf-8')
        print('updated {}'.format(MANIFEST.relative_to(ROOT)))
        return

    expected = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if actual != expected:
        expected_text = json.dumps(expected, indent=2, sort_keys=True)
        actual_text = json.dumps(actual, indent=2, sort_keys=True)
        import difflib
        print('\n'.join(difflib.unified_diff(
            expected_text.splitlines(), actual_text.splitlines(),
            fromfile='committed manifest', tofile='current tree')))
        raise SystemExit(
            'generated layer 231 artifacts differ; regenerate and review')

    print(
        'verified layer {layer}: {constructors} constructors, '
        '{functions} functions, {rpc_errors} RPC errors, '
        '{files} generated files'.format(
            files=len(actual['generated']), **actual['schema']))


if __name__ == '__main__':
    main()
