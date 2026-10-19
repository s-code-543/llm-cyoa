"""Restricted data-transformation Python worker. No imports or arbitrary attributes in scripts.

This is a deliberately small Python subset for administrator-authored scripts,
not a general-purpose sandbox for hostile third-party code.
"""
import ast
import json
import random
import resource
import sys

ALLOWED = {
    'Module', 'Expr', 'Assign', 'AugAssign', 'If', 'For', 'While', 'Break', 'Continue',
    'Pass', 'Name', 'Load', 'Store', 'Constant', 'Dict', 'List', 'Tuple', 'Set',
    'Subscript', 'Slice', 'BinOp', 'UnaryOp', 'BoolOp', 'Compare', 'IfExp',
    'Call', 'keyword', 'Attribute', 'ListComp', 'DictComp', 'SetComp', 'comprehension',
    'Add', 'Sub', 'Mult', 'Div', 'FloorDiv', 'Mod', 'Pow', 'USub', 'UAdd', 'Not',
    'And', 'Or', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE', 'In', 'NotIn', 'Is', 'IsNot',
}
METHODS = {'get', 'items', 'keys', 'values', 'append', 'extend', 'pop', 'update',
           'setdefault', 'remove', 'sort', 'reverse', 'count', 'index', 'copy'}
BUILTINS = {name: value for name, value in {
    'len': len, 'range': range, 'enumerate': enumerate, 'zip': zip,
    'min': min, 'max': max, 'sum': sum, 'sorted': sorted, 'abs': abs,
    'round': round, 'int': int, 'float': float, 'str': str, 'bool': bool,
    'dict': dict, 'list': list, 'set': set, 'tuple': tuple, 'any': any, 'all': all,
}.items()}


def validate_script(source):
    if not isinstance(source, str) or len(source) > 20000:
        raise ValueError('Python script must be text of at most 20,000 characters')
    try:
        tree = ast.parse(source)
    except (SyntaxError, RecursionError) as exc:
        raise ValueError('Invalid Python script syntax') from exc
    for node in ast.walk(tree):
        if type(node).__name__ not in ALLOWED:
            raise ValueError(f'Unsupported Python syntax: {type(node).__name__}')
        if isinstance(node, ast.Name) and node.id.startswith('_'):
            raise ValueError('Private names are unavailable')
        if isinstance(node, ast.Attribute) and node.attr not in METHODS:
            raise ValueError(f'Unavailable method: {node.attr}')
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in BUILTINS and node.func.id not in {'random', 'randint', 'choice'}:
                    raise ValueError(f'Unavailable function: {node.func.id}')
            elif not isinstance(node.func, ast.Attribute):
                raise ValueError('Indirect calls are unavailable')
    return tree


def set_limit(kind, maximum):
    """Lower limits without trying to raise an inherited hard limit."""
    _, hard = resource.getrlimit(kind)
    limit = maximum if hard == resource.RLIM_INFINITY else min(maximum, hard)
    resource.setrlimit(kind, (limit, limit))


def apply_resource_limits():
    set_limit(resource.RLIMIT_CPU, 2)
    # Darwin exposes RLIMIT_AS but rejects this limit. Linux deployment keeps
    # the memory bound; macOS retains CPU, wall-time, file and payload bounds.
    if sys.platform != 'darwin':
        set_limit(resource.RLIMIT_AS, 128 * 1024 * 1024)
    set_limit(resource.RLIMIT_NOFILE, 16)


def main():
    apply_resource_limits()
    payload = json.loads(sys.stdin.read(1024 * 1024 + 1))
    tree = validate_script(payload['code'])
    rng = random.Random(payload['seed'])
    scope = {'state': payload['state'], 'input': payload['input'],
             'random': rng.random, 'randint': rng.randint, 'choice': rng.choice}
    scope['__builtins__'] = BUILTINS
    exec(compile(tree, '<adventure-step>', 'exec'), scope, scope)
    output = json.dumps(scope['state'], allow_nan=False)
    if not isinstance(scope['state'], dict) or len(output) > 1024 * 1024:
        raise ValueError('State must be a JSON object no larger than 1 MB')
    sys.stdout.write(output)


if __name__ == '__main__':
    main()
