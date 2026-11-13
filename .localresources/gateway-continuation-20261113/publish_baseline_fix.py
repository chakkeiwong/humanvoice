"""Fixed correction commit and restart of the already approved HTTPS service."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import gateway_program as program

ROOT = Path('/home/ubuntu/workspace/humanvoice')
EXPECTED = {'.localresources/gateway-continuation-20261113/gateway_program.py': '5d61efbef3ed2e808d5aa0fce057216464d4b0589c34b4882af3cb370799da0a', '.localresources/gateway-continuation-20261113/gateway_runtime.py': '8909e134476d05fe400d4b643468f7778053842d9412a53d2069811286aa5dcf', '.localresources/gateway-continuation-20261113/test_gateway.py': 'ca2665341c57238703571758c4f8dbdb31c7519297164298b46c1cbf04d85d19', '.localresources/gateway-continuation-20261113/tests-result.json': '9c54569ad16f63860bbf7d5ac5d07616664233b0b70b2271daa1dd1a7618509e', '.localresources/gateway-continuation-20261113/tests.log': '39c3b901d031c68b95daf59d55002d8a431e15230c5ccb584fcf12d6e67fc8c3', '.localresources/gateway-continuation-20261113/tests.xml': '6c99962fcea277ab2288dafd4d14cfb8a94dac112ea9f30e27ead90d1a3187a4', '.localresources/gateway-continuation-20261113/offline-result.json': '3e52aa94767f4e6f346a07216f32709cd3872a81020c802d96aae6962e55049e', '.localresources/gateway-continuation-20261113/review.json': '2f5c0d31673c3192f66ace745b425613c8c086b7c6f2e09e0155f673629d5ca6', '.localresources/gateway-continuation-20261113/REVIEW.md': '79f71062fe98c80096e02a30dddf4ffe32d224f205d651b585fa7e6ee00d1f6f', '.localresources/gateway-continuation-20261113/first-launch-failure.json': '6a599a74511e7e0aabbeb2a526873cbaa6839f5931b030b6b3a1f37d47dbf1fa', '.localresources/gateway-continuation-20261113/environment-check.json': 'cf4a26496d515c7bb029a9e825eed222ed9014cf464c1cc425920e79ad7a4a1b', '.localresources/gateway-continuation-20261113/installation.json': '2d206601de411f5b1c1fd03923a53c180da2f4f2b8c2bc35f9c1f0d7326eefce', 'docs/plans/ENSEMBLE_MASTER_PROGRAM_2026-09-30.md': '8375028cc96c286c8c455d168e2fc36dbb149b8c4bfa5a2d6fdac1edba0cc366', 'docs/plans/humanvoice_master_program_v2.md': 'ef0b13cfcac511bf4a52331296703a2478d769f287b83fec2da7f99a37cc3636', 'docs/plans/ZLB_SESSION_BINDING_REPAIR_2026-11-13.md': 'b90c30dfa533f062e58a886e097e467c45b867f06b9ad3ad20f9ab42c6e6a541'}
SELF = '.localresources/gateway-continuation-20261113/publish_baseline_fix.py'


def git(*args):
    return subprocess.run(['/usr/bin/git', *args], cwd=ROOT, check=True,
                          text=True, capture_output=True, timeout=120).stdout.strip()


def publish():
    program.current_review()
    for relative, expected in EXPECTED.items():
        path = ROOT / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Commit input changed: ' + relative)
    if git('diff', '--cached', '--name-only'):
        raise ValueError('Unrelated staged work must be preserved')
    files = sorted([*EXPECTED, SELF])
    git('add', '-f', '--', *files)
    if set(git('diff', '--cached', '--name-only').splitlines()) != set(files):
        raise ValueError('Staged paths differ from the reviewed correction')
    git('diff', '--cached', '--check')
    print(git('commit', '-m', 'Preserve nested settlement readers during HTTPS recovery'), flush=True)
    print(json.dumps({'commit': git('rev-parse', 'HEAD')}), flush=True)
    subprocess.run([program.base.PYTHON, '-B', str(program.HERE / 'gateway_program.py'),
                    'install-start'], cwd=ROOT, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('publish',))
    parser.parse_args()
    publish()
