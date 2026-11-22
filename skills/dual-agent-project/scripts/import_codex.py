#!/usr/bin/env python3
"""Import supported project MCP definitions from Codex without losing native settings.

Requires Python 3.11+, or tomli. Default is a read-only preview; --apply writes
after validating every output and backing up all existing files outside the repo.
"""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

MCP_TABLE = re.compile(r'^\s*\[\s*(?:mcp_servers|"mcp_servers"|\'mcp_servers\')(?:\s*\.|\s*\])')


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def without_mcp(text, native):
    """Remove MCP table sections, then prove no other parsed setting changed."""
    lines, skip = [], False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith('['):
            skip = bool(MCP_TABLE.match(line))
        if not skip:
            lines.append(line)
    result = ''.join(lines)
    if tomllib.loads(result) != {k: v for k, v in native.items() if k != 'mcp_servers'}:
        raise ValueError('Cannot safely isolate MCP tables; reconcile native TOML manually')
    return result


def convert_server(name, server):
    allowed = {'command', 'args', 'cwd', 'env', 'url', 'http_headers',
               'disabled_tools', 'tool_timeout_sec'}
    unsupported = sorted(set(server) - allowed)
    if unsupported:
        raise ValueError('%s needs an explicit adapter for: %s' % (name, ', '.join(unsupported)))
    remote = 'url' in server
    if remote and set(server) & {'command', 'args', 'cwd', 'env'}:
        raise ValueError('%s mixes HTTP and stdio settings' % name)
    if not remote and ('command' not in server or 'http_headers' in server):
        raise ValueError('%s has no supported transport' % name)
    fields = ('url',) if remote else ('command', 'args', 'cwd', 'env')
    shared = {'type': 'http' if remote else 'stdio'}
    shared.update({k: server[k] for k in fields if k in server})
    if 'http_headers' in server:
        shared['headers'] = server['http_headers']
    for key in ('env', 'headers'):
        for env_key, value in shared.get(key, {}).items():
            if value and re.search(r'(?:KEY|TOKEN|SECRET|PASSWORD|AUTHORIZATION)', env_key, re.I):
                raise ValueError('%s: externalize credential field %s before importing' % (name, env_key))
    if 'tool_timeout_sec' in server:
        seconds = server['tool_timeout_sec']
        if remote or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('%s: timeout needs an explicit adapter' % name)
        env = shared.get('env', {})
        if 'MCP_TOOL_TIMEOUT' not in env or float(env['MCP_TOOL_TIMEOUT']) != seconds * 1000:
            raise ValueError('%s: native timeout needs an explicit shared client-timeout adapter' % name)
    tools = server.get('disabled_tools', [])
    if not isinstance(tools, list) or not all(isinstance(t, str) and t for t in tools):
        raise ValueError('%s: disabled_tools must name tools' % name)
    return shared, ['mcp__%s__%s' % (name, tool) for tool in tools]


def plan(root, adapter):
    if tomllib is None:
        raise ValueError('Use Python 3.11+ (or install tomli) to read native TOML')
    native_path = root / '.codex/config.toml'
    text = native_path.read_text()
    if adapter.START in text:
        raise ValueError('MCP already managed; run scripts/sync_agent_config.py instead')
    native = tomllib.loads(text)
    servers = native.get('mcp_servers', {})
    if not isinstance(servers, dict) or not servers:
        raise ValueError('No project MCP definitions to import')
    shared_path = root / '.mcp.json'
    shared = read_json(shared_path, {'mcpServers': {}})
    settings_path = root / '.claude/settings.json'
    settings = read_json(settings_path, {'permissions': {'deny': []}})
    denies = settings.setdefault('permissions', {}).setdefault('deny', [])
    if not isinstance(denies, list) or not all(isinstance(d, str) for d in denies):
        raise ValueError('Existing permissions.deny must be a list of strings')
    for name, server in servers.items():
        converted, tool_denies = convert_server(name, server)
        current = shared['mcpServers'].get(name)
        if current is not None and current != converted:
            raise ValueError('Conflicting shared and native MCP server: ' + name)
        shared['mcpServers'][name] = converted
        denies.extend(d for d in tool_denies if d not in denies)
    remaining = without_mcp(text, native)
    # Use the same adapter validation as ongoing refreshes. A temporary project
    # avoids writing even a source file when an unsupported setting is found.
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        (stage / '.claude').mkdir()
        (stage / '.codex').mkdir()
        (stage / '.mcp.json').write_text(json.dumps(shared))
        (stage / '.claude/settings.json').write_text(json.dumps(settings))
        (stage / '.codex/config.toml').write_text(remaining)
        adapter.render(stage)
    return {
        shared_path: json.dumps(shared, indent=2) + '\n',
        settings_path: json.dumps(settings, indent=2) + '\n',
        native_path: remaining,
    }, len(servers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    import importlib.util
    template = Path(__file__).resolve().parents[1] / 'assets/sync_agent_config.py'
    spec = importlib.util.spec_from_file_location('shared_adapter', template)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    try:
        outputs, count = plan(root, adapter)
        if args.apply:
            data_home = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
            backup = data_home / 'agent-manager/backups' / ('codex-import-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            for path in outputs:
                if path.exists():
                    destination = backup / path.relative_to(root)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(path), str(destination))
            for path, content in outputs.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            print('Backup: ' + str(backup))
        print('%s %d project MCP server(s); native non-MCP settings preserved.' %
              ('Imported' if args.apply else 'Would import', count))
        print('Run the project sync adapter after importing. Native rules/hooks still need review.')
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print('Import stopped: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
