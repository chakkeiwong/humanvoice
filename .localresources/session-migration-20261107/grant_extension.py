"""An explicit additive call limit without rewriting historical grant bytes.

The native status reader retains all baseline, stage, settlement and identity
checks. Its four uses of the spending ceiling select an independently approved
extension. Historical grant identity and durable stage rows remain unchanged.
No extension is active merely because this module is imported.
"""

import ast
import inspect
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import CodeType, FunctionType

from humanvoice.artifacts import digest, read_json
from tools import automatic_call_grant as grants
from tools.delayed_network_runtime import replaced_aliases
from tools.inventory_recovery_v3 import retired_grants

VERSION = 'humanvoice-additive-call-authorization-v1'
NATIVE = grants.status


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(record, grant, grant_path):
    require(record.get('version') == VERSION
        and record.get('identity') == digest({key: value for key, value in record.items() if key != 'identity'})
        and record.get('status') == 'USER_AUTHORIZED'
        and record.get('authorized_by') == 'user'
        and isinstance(record.get('authorization'), str) and bool(record['authorization'].strip())
        and record.get('grant') == str(Path(grant_path).absolute())
        and record.get('grant_identity') == grant.get('identity')
        and type(record.get('original_maximum')) is int
        and record.get('original_maximum') == grant.get('maximum_new_calls')
        and type(record.get('additional_calls')) is int and record['additional_calls'] > 0
        and type(record.get('total_maximum')) is int
        and record['total_maximum'] == grant['maximum_new_calls'] + record['additional_calls']
        and record.get('no_replenishment_on_reload') is True,
        'Call extension lacks exact additive user authorization')
    return record['total_maximum']


def reader(record, *, authorization_check):
    """Derive the native reader with only its four capacity expressions changed."""
    frozen = deepcopy(record)
    syntax = ast.parse(inspect.getsource(NATIVE))

    class Capacity(ast.NodeTransformer):
        def __init__(self):
            self.count = 0
            self.original_validation = 0

        def visit_Compare(self, node):
            # The native grant's positive original limit remains part of its
            # identity validation; only later spending expressions change.
            if (isinstance(node.left, ast.Subscript)
                    and isinstance(node.left.value, ast.Name) and node.left.value.id == 'grant'
                    and isinstance(node.left.slice, ast.Constant)
                    and node.left.slice.value == 'maximum_new_calls'
                    and len(node.ops) == 1 and isinstance(node.ops[0], ast.LtE)
                    and len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)
                    and node.comparators[0].value == 0):
                self.original_validation += 1
                return node
            return self.generic_visit(node)

        def visit_Subscript(self, node):
            if (isinstance(node.value, ast.Name) and node.value.id == 'grant'
                    and isinstance(node.slice, ast.Constant) and node.slice.value == 'maximum_new_calls'):
                self.count += 1
                return ast.copy_location(ast.Call(func=ast.Name(id='approved_maximum', ctx=ast.Load()),
                    args=[ast.Name(id='grant', ctx=ast.Load()), ast.Name(id='path', ctx=ast.Load())], keywords=[]), node)
            return self.generic_visit(node)

    replacement = Capacity()
    syntax = ast.fix_missing_locations(replacement.visit(syntax))
    require(replacement.count == 4 and replacement.original_validation == 1 and len(syntax.body) == 1
        and isinstance(syntax.body[0], ast.FunctionDef) and syntax.body[0].name == 'status',
        'Native grant reader changed; its capacity extension requires review')

    def maximum(grant, path):
        require(record == frozen and authorization_check() is True,
            'Call extension authority changed during native verification')
        return validate(frozen, grant, path)

    namespace = {**NATIVE.__globals__, '__name__': __name__, 'approved_maximum': maximum}
    compiled = compile(syntax, '<humanvoice-approved-call-extension>', 'exec')
    functions = [code for code in compiled.co_consts if isinstance(code, CodeType)]
    require(len(functions) == 1 and functions[0].co_name == 'status',
        'Call extension compiled unexpected executable membership')
    return FunctionType(functions[0], namespace, NATIVE.__name__, NATIVE.__defaults__)


@contextmanager
def scope(authorization_path, *, expected_sha256):
    path = Path(authorization_path)

    def stable():
        require(not path.is_symlink() and digest(path.read_bytes()) == expected_sha256,
            'Call extension differs from its approved immutable bytes')
        return True

    stable()
    record = read_json(path)
    expanded = reader(record, authorization_check=stable)
    # Includes retained_grants.NATIVE and native stage()'s dynamic status lookup.
    # Retirement proof and settlement readers remain the original implementations.
    with replaced_aliases(NATIVE, expanded):
        require(grants.status is expanded and retired_grants.NATIVE is expanded,
            'Call extension did not bind the native grant readers')
        try:
            yield
        finally:
            stable()
