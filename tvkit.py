#!/usr/bin/env python3
"""Conservative Sony TV setup helpers. Every setting change has a local restore journal."""
import argparse
import datetime
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / '.local'
CONFIG = LOCAL / 'config.json'
LAUNCHER = 'com.gathin.tvhome/.MainActivity'
STOCK = {'com.google.android.apps.tv.launcherx', 'com.google.android.tvlauncher'}
TRACKING = ('tv.samba.ssm', 'tv.samba.ssm.ui', 'com.sonyericsson.idd.agent', 'com.sony.dtv.promos')
RECOVERY = 'com.google.android.tungsten.setupwraith'
MANAGED = set(TRACKING) | STOCK | {RECOVERY}
STATE_COMMAND = {0: 'default-state', 1: 'enable', 2: 'disable', 3: 'disable-user', 4: 'disable-until-used'}
KEYS = {'up': 'DPAD_UP', 'left': 'DPAD_LEFT', 'down': 'DPAD_DOWN', 'right': 'DPAD_RIGHT',
        'select': 'DPAD_CENTER', 'back': 'BACK', 'home': 'HOME', 'off': 'SLEEP',
        'louder': 'VOLUME_UP', 'quieter': 'VOLUME_DOWN', 'mute': 'VOLUME_MUTE', 'pause': 'MEDIA_PLAY_PAUSE'}


def validate_endpoint(value):
    host, sep, port = value.rpartition(':')
    if not sep or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('Use a TV IPv4 address or hostname followed by :5555.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', host):
        raise ValueError('Invalid TV host.')
    return value


def endpoint():
    value = os.environ.get('TV_ADDRESS')
    if not value and CONFIG.exists():
        value = json.loads(CONFIG.read_text()).get('address')
    if not value:
        raise RuntimeError('Run: python3 tvkit.py configure YOUR_TV_IP:5555')
    return validate_endpoint(value)


def run(args, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    out = (result.stdout + result.stderr).strip()
    if result.returncode or re.search(r'(^Error:|Exception occurred|SecurityException|^Failure)', out, re.M):
        raise RuntimeError(out or 'Command failed')
    return out


def adb(*args, timeout=30):
    if not shutil.which('adb'):
        raise RuntimeError('Install Android platform-tools (adb) first.')
    return run(['adb', '-s', endpoint(), *args], timeout)


def connect():
    print(run(['adb', 'connect', endpoint()], 15))
    if adb('get-state') != 'device':
        raise RuntimeError('Authorise this computer on the TV first.')


def identity():
    return {'serial': adb('shell', 'getprop', 'ro.serialno'),
            'model': adb('shell', 'getprop', 'ro.product.model')}


def enabled_state(dump):
    match = re.search(r'User 0:.*?\benabled=(\d+)\b', dump)
    if not match or int(match[1]) not in STATE_COMMAND:
        raise RuntimeError('Cannot determine the package state for user 0.')
    return int(match[1])


def resolve_home():
    out = adb('shell', 'cmd', 'package', 'resolve-activity', '--brief', '-a',
              'android.intent.action.MAIN', '-c', 'android.intent.category.HOME')
    for line in reversed(out.splitlines()):
        if re.fullmatch(r'[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+', line.strip()):
            return line.strip()
    raise RuntimeError('Cannot determine the current Home activity.')


def write_private(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(data)
    temp.replace(path)


def save_state(path, state):
    write_private(path, json.dumps(state, indent=2) + '\n')


def backup():
    latest = LOCAL / 'latest-backup.txt'
    if latest.exists():
        prior = Path(latest.read_text().strip())
        if prior.exists() and json.loads(prior.read_text()).get('changed'):
            raise RuntimeError('Restore existing package changes before replacing the restore point.')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    folder = LOCAL / 'backups' / stamp
    folder.mkdir(mode=0o700, parents=True)
    home = resolve_home()
    packages = {}
    for pkg in sorted(MANAGED):
        dump = adb('shell', 'dumpsys', 'package', pkg)
        if re.search(r'User 0:.*?installed=true', dump):
            packages[pkg] = enabled_state(dump)
    state = {'version': 1, 'device': identity(), 'home': home, 'packages': packages, 'changed': []}
    save_state(folder / 'state.json', state)
    for name, args in [('packages.txt', ('pm', 'list', 'packages', '-f')),
                       ('disabled.txt', ('pm', 'list', 'packages', '-d'))]:
        write_private(folder / name, adb('shell', *args) + '\n')
    for table in ('system', 'secure', 'global'):
        write_private(folder / f'settings-{table}.txt', adb('shell', 'settings', 'list', table) + '\n')
    write_private(LOCAL / 'latest-backup.txt', str(folder / 'state.json'))
    return folder / 'state.json', state


def restore_journal():
    if not (LOCAL / 'latest-backup.txt').exists():
        raise RuntimeError('Run backup first.')
    path = Path((LOCAL / 'latest-backup.txt').read_text().strip())
    if not path.resolve().is_relative_to((LOCAL / 'backups').resolve()):
        raise RuntimeError('Restore journal must be inside .local/backups.')
    state = json.loads(path.read_text())
    if state.get('device') != identity():
        raise RuntimeError('This backup belongs to a different device. Nothing changed.')
    for pkg, original in state['packages'].items():
        if pkg not in MANAGED or original not in STATE_COMMAND:
            raise RuntimeError('Unexpected package or state in restore journal.')
    home = state.get('home', '')
    if not re.fullmatch(r'[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+', home):
        raise RuntimeError('Invalid home component in journal.')
    if any(pkg not in state['packages'] for pkg in state['changed']):
        raise RuntimeError('Unexpected change in journal.')
    return path, state


def change_package(path, state, pkg):
    if pkg not in state['packages']:
        return
    if pkg not in state['changed']:
        state['changed'].append(pkg)
        save_state(path, state)  # Journal before the mutation, including interrupted commands.
    print(adb('shell', 'pm', 'disable-user', '--user', '0', pkg))


def key(name):
    print(adb('shell', 'input', 'keyevent', 'KEYCODE_' + KEYS[name]))


def remote():
    bindings = {'w': 'up', 'a': 'left', 's': 'down', 'd': 'right', 'e': 'select', 'b': 'back',
                'h': 'home', '+': 'louder', '-': 'quieter', 'm': 'mute', 'p': 'pause', 'o': 'off'}
    print('w/a/s/d arrows; e select; b back; h home; +/- volume; m mute; p pause; o standby; q quit. Press Return after a key.')
    while True:
        choice = input('TV> ').strip().lower()
        if choice == 'q':
            return
        if choice in bindings:
            key(bindings[choice])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('configure').add_argument('address')
    for command in ('backup', 'activate-home', 'disable-tracking', 'restore', 'remote', 'vpn-address'):
        subs.add_parser(command)
    subs.add_parser('key').add_argument('name', choices=KEYS)
    subs.add_parser('install').add_argument('apk', type=Path)
    theme = subs.add_parser('theme'); theme.add_argument('config', type=Path); theme.add_argument('--wallpaper', type=Path)
    args = parser.parse_args()
    if args.command == 'configure':
        address = validate_endpoint(args.address)
        save_state(CONFIG, {'address': address})
        print('Saved private local configuration. No TV changes made.')
        return
    connect()
    if args.command == 'backup':
        print(backup()[0])
    elif args.command in ('activate-home', 'disable-tracking'):
        path, state = restore_journal()
        if args.command == 'disable-tracking':
            for pkg in TRACKING:
                change_package(path, state, pkg)
        else:
            stock = state['home'].split('/')[0]
            if stock not in STOCK:
                raise RuntimeError('Original Home is not a recognised Google TV launcher. No packages changed.')
            launch = adb('shell', 'am', 'start', '-W', '-n', LAUNCHER)
            if 'Status: ok' not in launch or re.search(r'^Error:', launch, re.M):
                raise RuntimeError('New launcher did not start. Stock Home left unchanged.')
            try:
                # Google TV setup recovery also claims HOME. Disable it before the stock launcher.
                change_package(path, state, RECOVERY)
                change_package(path, state, stock)
                print(adb('shell', 'cmd', 'package', 'set-home-activity', '--user', '0', LAUNCHER))
                if resolve_home() != LAUNCHER:
                    raise RuntimeError('New Home did not become default.')
            except Exception:
                restore_packages(state)
                adb('shell', 'cmd', 'package', 'set-home-activity', '--user', '0', state['home'])
                raise
            key('home')
    elif args.command == 'restore':
        path, state = restore_journal()
        restore_packages(state)
        adb('shell', 'cmd', 'package', 'set-home-activity', '--user', '0', state['home'])
        if resolve_home() != state['home']:
            raise RuntimeError('Home did not restore. Keep the backup and retry while ADB is reachable.')
        key('home')
        state['changed'] = []; save_state(path, state)
        print('Original package states and Home restored. Added apps and files remain installed.')
    elif args.command == 'install':
        if args.apk.suffix.lower() != '.apk' or not args.apk.is_file():
            raise RuntimeError('Provide an existing APK file.')
        print(adb('install', '-r', str(args.apk.resolve()), timeout=180))
    elif args.command == 'theme':
        json.loads(args.config.read_text())
        target = '/sdcard/Android/data/com.gathin.tvhome/files'
        adb('shell', 'mkdir', '-p', target)
        adb('push', str(args.config.resolve()), target + '/config.json')
        if args.wallpaper:
            adb('push', str(args.wallpaper.resolve()), target + '/wallpaper.jpg')
        adb('shell', 'am', 'force-stop', 'com.gathin.tvhome')
        print(adb('shell', 'am', 'start', '-W', '-n', LAUNCHER))
    elif args.command == 'key':
        key(args.name)
    elif args.command == 'remote':
        remote()
    elif args.command == 'vpn-address':
        addresses = re.findall(r'inet\s+(\d+\.\d+\.\d+\.\d+)/', adb('shell', 'ip', '-4', 'addr', 'show'))
        candidates = set(x for x in addresses if ipaddress.ip_address(x) in ipaddress.ip_network('100.64.0.0/10'))
        if len(candidates) != 1:
            raise RuntimeError('Connect Tailscale on the TV first; a unique VPN address was not found.')
        address = candidates.pop() + ':5555'; expected = identity()
        if run(['adb', 'connect', address], 15).startswith('failed'):
            raise RuntimeError('Cannot reach VPN endpoint. Previous configuration kept.')
        model = run(['adb', '-s', address, 'shell', 'getprop', 'ro.product.model'])
        serial = run(['adb', '-s', address, 'shell', 'getprop', 'ro.serialno'])
        if expected != {'model': model, 'serial': serial}:
            raise RuntimeError('VPN endpoint does not match this TV. Previous configuration kept.')
        save_state(CONFIG, {'address': address}); print('Private VPN address verified and saved.')


def restore_packages(state):
    for pkg in reversed(state['changed']):
        print(adb('shell', 'pm', STATE_COMMAND[state['packages'][pkg]], '--user', '0', pkg))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        sys.exit(str(error))
