"""Fixed commit and user-service installation for the reviewed HTTPS continuation."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import gateway_program as program

ROOT = Path('/home/ubuntu/workspace/humanvoice')
EXPECTED = {'.localresources/gateway-continuation-20261113/REVIEW.md': '8a6a87476fdab15e8f2a78fbe97b17bab61e0d8330cbd9dba4a437c6b4271f48', '.localresources/gateway-continuation-20261113/check_gateway.py': '51b04490917ce1251b5218b993a086c67077215210a5b7c20b5937ca5b3c9182', '.localresources/gateway-continuation-20261113/gateway_bootstrap.py': 'd717b5d7d0ad6f01653b9a1927450ba39d97f98f08222e59956fbb5bc8446eca', '.localresources/gateway-continuation-20261113/gateway_program.py': '90095cfc43f7e485b1e3c1351adf26b6bb979fccca02955d68602f9ed948be9e', '.localresources/gateway-continuation-20261113/gateway_runtime.py': 'f8129a53a9bd48f52895f5c3f5324f36d2e542b4f7bc35a07c59811893963513', '.localresources/gateway-continuation-20261113/gateway_state.py': '43c2e87dbad57a7d97381d93df8c0ef2b8c3afd20be5a15367a46ea23b89a2ff', '.localresources/gateway-continuation-20261113/humanvoice-zlb-https-20261113.service': '5d314fbfa598f6c33498a98b2d615403a438a47626ddb1f20b0d8df09adb7f9a', '.localresources/gateway-continuation-20261113/offline-result.json': '4efd4927ad4bb0665bb5a3320b7de0d6f172fc45ddc70db0592fb736b19858b3', '.localresources/gateway-continuation-20261113/review.json': '7eeddd231ac2288d765ca2bb8a517e13f26e946754d74e65b6050b77b3e1ec36', '.localresources/gateway-continuation-20261113/test_gateway.py': '9d0ab32b5ef0d004df397f406474cfa9e97d729baabe042ca7e4fdaf092f7417', '.localresources/gateway-continuation-20261113/tests-result.json': '7dd6416c4d9abc1fa8ac07a42776c527ac2278ab4a3e58162ecbed7855816478', '.localresources/gateway-continuation-20261113/tests.log': '4ed1672e120b6f47b0a3af2c8f01e3bf0a7c3104ce1172838dc54ccab89ec24a', '.localresources/gateway-continuation-20261113/tests.xml': '6c1fb7d5c773d4fb649e72b3420ef9de20198770fa70b5125d3d0861116ca9cf', '.localresources/gateway-continuation-20261113/transition.json': 'e4d42c692f1f9d62203881e018caa0314f5a797bee504390320cc90229a54ede', '.localresources/writer-session-binding-repair-20261113/REVIEW.md': '11b9e0c83fa12ff083707cc9854b7073b741518d1197f9705c2a1176531c5e2a', '.localresources/writer-session-binding-repair-20261113/actual-session-check.json': '38d32ee226052433af476c8e3b91ca029bb51fadcf901c791c66df883b84b267', '.localresources/writer-session-binding-repair-20261113/check_execution.py': 'c18248c3ba5c35279175da711bc3c26f3e441a8565b5bd92f45da1d66ed16aba', '.localresources/writer-session-binding-repair-20261113/diagnose.py': '0c66cb7aaa120c0d1977634543225c92ceec66ecb764e419c6eadeebb432d222', '.localresources/writer-session-binding-repair-20261113/execution-review.json': '81b13448ae711e97585dc34617e375c25ba5fd8082ec0403492aaad5ec9df886', '.localresources/writer-session-binding-repair-20261113/execution-tests.json': '914e5f29facc790423b768f4cd28669d5192a18e7d4759c8f7ed17205f78dfe9', '.localresources/writer-session-binding-repair-20261113/execution-tests.log': '26e5d2f95298ca0367065dec682d1b1bb8f0a395dbf4e238c313146b9c283c63', '.localresources/writer-session-binding-repair-20261113/execution-tests.xml': 'd58f188efee1ad22ee7abda7707152301331c075a7d3e448fab9a182cf01f13a', '.localresources/writer-session-binding-repair-20261113/humanvoice-zlb-session-repair-20261113.service': '6742150908ba20778e57fba83ec954d897530f1be083059b3bc475fa1efdff18', '.localresources/writer-session-binding-repair-20261113/regression-tests.log': 'd4c1d9cfe579a168b4831110a7ecb043973f05e1dccdb853cfdd941ee55976df', '.localresources/writer-session-binding-repair-20261113/regression-tests.xml': '23dabb6cc830a104dda9f5dcf3e477dce481c4bf169b20f131d93473a37f9cf6', '.localresources/writer-session-binding-repair-20261113/rehearsal.json': '89b8b63af733d18aca3a1a07f37e140a638a2fdd66e74813b488cbdd114c84d0', '.localresources/writer-session-binding-repair-20261113/renewal.json': 'f70fed164d97e9ddefb5de936d01e9afc27bce2d43cb77019e2b545f8181f641', '.localresources/writer-session-binding-repair-20261113/renewal_runtime.py': '1ba28546d31cf1a08ff80898de66a5c76a2d587a347cc7b60a9034acb0cffc3e', '.localresources/writer-session-binding-repair-20261113/run_checks.py': 'd35506d65dbff9b14921f225edec3c5b552110c149279393bcf449385e5be33a', '.localresources/writer-session-binding-repair-20261113/session_bootstrap.py': '120fcc1e52731449cb43fbfc4aff0892795532f8c621da3afa823b47523b321a', '.localresources/writer-session-binding-repair-20261113/session_endpoint.py': '03da4ce602d360e2e31076369850a5d8eb482600abd0234ee2ca5d5b893101cd', '.localresources/writer-session-binding-repair-20261113/session_program.py': '4adc62a38f8cf2109a6dc679c6356c97efb943ea63d288989f9c87ea28f03498', '.localresources/writer-session-binding-repair-20261113/test_session_program.py': '84f43adcc29ef4f563b326bdd2882e0f00eaafb3c5e3c81099c38fa8d56fd042', '.localresources/writer-session-binding-repair-20261113/tests-result.json': 'b96b211c5e3de4d5780319006755cfcf1de33e00a9a922f2ab7eba5b9acab258', 'docs/plans/ENSEMBLE_MASTER_PROGRAM_2026-09-30.md': 'cac3f42dd8aa6b31fcf773d7b854032eccb153bcbb835c9840198a0e9eabf5ac', 'docs/plans/ZLB_SESSION_BINDING_REPAIR_2026-11-13.md': '79bd96d5bbced9dc3008bcca5af9f2354c8cfaf553692a593842f3c39ac72aee', 'docs/plans/humanvoice_master_program_v2.md': '6fa20025430dccf7054ecb65330e6e96b59b9fe1508bfb3fe7028397aae119a4', 'tests/test_zlb_session_endpoint_binding.py': '428ad1568a571a1be5cd923e1b140712271e78916073daf2a8c63443bf996c44', 'tests/test_zlb_session_endpoint_integrity.py': 'cc1e5b419d4d9a946acadb3623da6382c0c8964fa12afef951fc99cfe58e4eac'}
SELF = '.localresources/gateway-continuation-20261113/publish_continuation.py'


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
        raise ValueError('Preexisting staged work must not be included')
    files = sorted([*EXPECTED, SELF])
    git('add', '-f', '--', *files)
    if set(git('diff', '--cached', '--name-only').splitlines()) != set(files):
        raise ValueError('Staged files differ from explicit repair group')
    git('diff', '--cached', '--check')
    print(git('commit', '-m', 'Repair ZLB session binding and renew HTTPS continuation'), flush=True)
    commit = git('rev-parse', 'HEAD')
    print(json.dumps({'commit': commit, 'files': len(files)}), flush=True)
    subprocess.run([program.base.PYTHON, '-B', str(program.HERE / 'gateway_program.py'),
                    'install-start'], cwd=ROOT, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('publish',))
    parser.parse_args()
    publish()
