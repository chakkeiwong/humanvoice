"""Explicit transport succession: immutable old profile, truthful new receipts."""
from copy import deepcopy
from pathlib import Path

import gateway_bootstrap as bootstrap

from humanvoice.artifacts import digest, read_json
from tools import active_session_settings as settings
from tools import active_session_stream_recovery as stream
from tools import model_routing_policy as routing
from tools.ensemble_closure_contract import save

HERE = bootstrap.HERE
previous = bootstrap.previous
live, context = previous.live, previous.context
PATH = HERE / 'transition.json'
OLD_URL = 'http://144.34.149.141:8080/v1'
NEW_URL = 'https://cn.origincoder.com/v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def changes(old, new, prefix=''):
    if isinstance(old, dict) and isinstance(new, dict):
        return sorted(p for key in old.keys() | new.keys()
                      for p in changes(old.get(key), new.get(key), prefix + '/' + key))
    return [] if old == new else [prefix]


def successor(profile, binding):
    original = routing.binding_for(profile)
    require(changes(original, binding) == ['/settings/layers', '/settings/provider/base_url']
            and original['settings']['provider']['base_url'] == OLD_URL
            and binding['settings']['provider']['base_url'] == NEW_URL,
            'Transport succession changes more than the observed gateway/configuration layer')
    base = profile[routing.FIELD]['base_profile']
    selected = settings.candidate_profile(base, binding)
    selected = stream.candidate_profile(selected)
    result = routing.candidate_profile(selected, profile[routing.FIELD]['index'])
    for field in ('model', 'sampling', 'budget', 'prompt_templates'):
        require(result[field] == profile[field], 'Gateway migration changed ' + field)
    require(result['runtime']['codex'] == profile['runtime']['codex'], 'Gateway migration changed client')
    return result


def prepare():
    previous.current_review()
    admission = read_json(live.STATE / 'admission.json')
    profile = admission['binding']['profile']
    binding = settings.capture(routing.binding_for(profile))
    new_profile = successor(profile, binding)
    attempts = read_json(live.OUTPUT / 'native-attempts.json')
    require(len(attempts['attempts']) == 135 and all(r['done'] for r in attempts['attempts']),
            'Migration requires the drained retained 135-attempt prefix')
    require(read_json(live.STATE / 'coordinator.json')['pending'] is None,
            'Migration cannot replace a pending batch')
    value = {'version': 'zlb-gateway-succession-v1', 'stage': str(live.OUTPUT),
             'source_hash': admission['binding']['source_hash'],
             'admission_sha256': digest((live.STATE / 'admission.json').read_bytes()),
             'authorization': 'repair the program to always use the same setting as the ative session.  Always double check before launching.  continue the execution.',
             'continuation_authorization': previous.renewal.RECORD['authorization'],
             'user_gateway_question': 'is the current one https://cn.origincoder.com/v1',
             'deadline': previous.renewal.RECORD['deadline'], 'first_new_slot': 135,
             'maximum_slots': 177, 'old_profile': profile, 'profile': new_profile,
             'original_attempts': attempts['attempts'],
             'original_bank': read_json(previous.HERE / 'rehearsal.json')['bank']}
    if PATH.exists():
        require(read_json(PATH) == value, 'Existing migration differs; preserve its evidence')
    else:
        save(PATH, value)
    return value


def load():
    value = read_json(PATH)
    admission = read_json(live.STATE / 'admission.json')
    require(value['version'] == 'zlb-gateway-succession-v1'
            and value['stage'] == str(live.OUTPUT) and value['maximum_slots'] == 177
            and value['first_new_slot'] == 135
            and value['deadline'] == previous.renewal.RECORD['deadline']
            and value['admission_sha256'] == digest((live.STATE / 'admission.json').read_bytes())
            and value['source_hash'] == admission['binding']['source_hash']
            and value['old_profile'] == admission['binding']['profile']
            and value['profile'] == successor(value['old_profile'], routing.binding_for(value['profile'])),
            'Gateway transition differs from its fixed stage/profile/renewal')
    current = read_json(live.OUTPUT / 'native-attempts.json')['attempts']
    require(current[:135] == value['original_attempts'], 'Migration changed an existing paid attempt')
    return value


def marker(value, row, directory):
    require(value['first_new_slot'] <= row['slot'] < value['maximum_slots'],
            'New transport cannot replace an old or foreign slot')
    return {'version': value['version'], 'transition': str(PATH), 'transition_sha256': digest(PATH.read_bytes()),
            'stage': value['stage'], 'slot': row['slot'], 'attempt': row['id'],
            'task': row['task'], 'runtime_id': Path(directory).name,
            'semantic_profile_hash': digest(value['old_profile']),
            'transmitted_profile_hash': digest(value['profile']),
            'endpoint': value['profile']['runtime']['endpoint']}


def recorded_profile(snapshot, reference, expected):
    """Select the actually recorded profile; never rewrite request/receipt bytes."""
    value = load()
    if expected not in (value['old_profile'], value['profile']):
        return expected
    from humanvoice.artifacts import confined_path
    directory = confined_path(Path(snapshot), reference['path']).parent
    request = read_json(directory / 'inputs/api-request.json')
    actual = request['profile']
    if actual == value['old_profile']:
        require(not (directory / 'gateway-transition.json').exists(), 'Old receipt gained a transport successor')
        return actual
    require(actual == value['profile'] and request['source_hash'] == value['source_hash'],
            'Receipt uses an unadmitted gateway/profile/source')
    evidence = read_json(directory / 'gateway-transition.json')
    rows = read_json(live.OUTPUT / 'native-attempts.json')['attempts']
    slot = evidence.get('slot')
    require(type(slot) is int and value['first_new_slot'] <= slot < len(rows),
            'Gateway receipt lacks its charged successor slot')
    row = rows[slot]
    require(evidence == marker(value, row, directory)
            and row.get('runtime_directory') == str(live.TRANSMISSION / '.humanvoice/runtime' / directory.name)
            and row['started'], 'Gateway receipt lost exact native attempt ownership')
    return deepcopy(actual)
