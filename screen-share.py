#!/usr/bin/env python3
"""Mac viewer with a persistent TV-side sharing badge and local stop control."""
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent
from tvkit import endpoint
TV = None
ADB = shutil.which('adb')
SCRCPY = shutil.which('scrcpy')
SERVICE = 'lab.tv.share/.ShareService'
FILES = '/sdcard/Android/data/lab.tv.share/files'
TOKEN = uuid.uuid4().hex
LOCAL = BASE / '.local'
LOCAL.mkdir(mode=0o700, exist_ok=True)
LOCK = LOCAL / 'screen-share.lock'
viewer = None
started = False
locked = False


def adb(*args, timeout=8, check=True):
    result = subprocess.run([ADB, '-s', TV, *args], text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout)
    if check and (result.returncode or 'Exception' in result.stdout or 'Error:' in result.stdout):
        raise RuntimeError(result.stdout.strip())
    return result.stdout.strip()


def status():
    # Marker plus a live service record: a stale file alone never authorises viewing.
    state = adb('shell', f'if [ -f {FILES}/stop ]; then echo STOP; '
                f'elif [ -f {FILES}/active ]; then cat {FILES}/active; else echo OFF; fi')
    services = adb('shell', 'dumpsys', 'activity', 'services', 'lab.tv.share')
    live = re.search(r'ServiceRecord\{[^\n]*lab\.tv\.share/\.ShareService', services) is not None
    return state if live else 'OFF'


def close_viewer():
    if viewer is not None and viewer.poll() is None:
        viewer.terminate()
        try:
            viewer.wait(timeout=5)
        except subprocess.TimeoutExpired:
            viewer.kill()
            viewer.wait(timeout=3)


def quit_signal(signum, frame):
    raise KeyboardInterrupt


try:
    TV = endpoint()
    if not ADB or not SCRCPY:
        raise RuntimeError('ADB and scrcpy must be installed and on PATH.')
    try:
        LOCK.mkdir()
        locked = True
        (LOCK / 'pid').write_text(str(os.getpid()))
    except FileExistsError:
        raise RuntimeError('A sharing session may already be running. Close its window first. '
                           'If a previous Mac crash left a lock, remove .local/screen-share.lock in the project folder.')
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, quit_signal)
    subprocess.run([ADB, 'connect', TV], check=True, timeout=10)
    if adb('get-state') != 'device':
        raise RuntimeError('TV unavailable; check power, Wi-Fi and debugging authorisation.')
    # This app is only a visible indicator. No recording or permission-prompt bypass is used.
    started = True
    adb('shell', 'am', 'start-foreground-service', '-n', SERVICE, '--es', 'session', TOKEN)
    ready = False
    for _ in range(10):
        if status() == TOKEN:
            ready = True
            break
        time.sleep(0.3)
    if not ready:
        raise RuntimeError('The TV sharing indicator did not start; mirroring has not been opened.')
    print('TV sharing is active with a visible badge on the TV.', flush=True)
    print('Close the viewer to stop. TV viewers can use All apps → Screen Sharing → Stop sharing.', flush=True)
    print('Use arrow keys and Return to navigate; Cmd+H = Home, Cmd+B = Back.', flush=True)
    print('Use TV Off.command to put the TV in standby.', flush=True)
    with (LOCAL / 'screen-share.log').open('w') as log:
        viewer = subprocess.Popen([SCRCPY, '--serial', TV, '--no-audio', '--no-power-on',
            '--max-size=1280', '--max-fps=20', '--video-bit-rate=4M', '--window-width=1100',
            '--window-title=TV — Screen sharing active', '--shortcut-mod=lsuper,rsuper'],
            stdout=log, stderr=subprocess.STDOUT)
        while viewer.poll() is None:
            time.sleep(1)
            if viewer.poll() is not None:
                break
            if status() != TOKEN:
                print('Sharing stopped by the TV, or the sharing indicator is unavailable.', flush=True)
                break
        code = viewer.poll()
        if code is not None and code != 0:
            raise RuntimeError('Viewer exited with an error. See screen-share.log in the setup folder.')
except KeyboardInterrupt:
    print('Closing sharing.', flush=True)
except (OSError, RuntimeError, subprocess.SubprocessError) as error:
    print(f'Screen sharing: {error}', file=sys.stderr, flush=True)
    sys.exitcode = 1
finally:
    close_viewer()  # Stop the stream before removing its visible TV badge.
    if started:
        try:
            adb('shell', 'am', 'startservice', '-n', SERVICE, '-a', 'END', check=False)
        except (OSError, subprocess.SubprocessError):
            print('TV unreachable. Its sharing badge may remain; reopen Screen Sharing on the TV.', flush=True)
    if locked:
        (LOCK / 'pid').unlink(missing_ok=True)
        LOCK.rmdir()
sys.exit(getattr(sys, 'exitcode', 0))
