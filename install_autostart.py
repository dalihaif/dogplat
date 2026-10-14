# -*- coding: utf-8 -*-
"""开机自启管理（不依赖 schtasks / 不需要管理员权限）

做法：往 Windows「启动」文件夹放一个 vbs，登录后由系统自动执行。
用法：
    python install_autostart.py on     开启
    python install_autostart.py off    关闭
    python install_autostart.py status 查看
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PYW = (r'C:\Users\Administrator\.workbuddy\binaries'
               r'\python\envs\default\Scripts\pythonw.exe')


def _resolve_pyw():
    """优先读 py_path.txt（安装时写入），否则用默认路径。"""
    cfg = os.path.join(BASE, 'py_path.txt')
    if os.path.exists(cfg):
        with open(cfg, encoding='utf-8', errors='ignore') as f:
            d = f.read().strip().strip('"')
        if d:
            p = os.path.join(d, 'pythonw.exe')
            if os.path.exists(p):
                return p
    return DEFAULT_PYW


PYW = _resolve_pyw()
APP = os.path.join(BASE, 'app.py')

STARTUP_DIR = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~\\AppData\\Roaming')),
    'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
AUTOSTART = os.path.join(STARTUP_DIR, '狗狗管理平台自启.vbs')
# 改名前留下的旧启动项，开/关时一并清掉，免得改名后有两个自启在跑
LEGACY = [os.path.join(STARTUP_DIR, '训犬工作平台自启.vbs')]


def _purge_legacy():
    for p in LEGACY:
        try:
            if os.path.exists(p):
                os.remove(p)
                print(f'[i] 已清理改名前的旧启动项：{os.path.basename(p)}')
        except OSError:
            pass

# 逐行拼装，避免 Python 字符串引号转义出错
VBS_LINES = [
    "' 狗狗管理平台 · 开机自启（由 install_autostart.py 自动生成）",
    "' 关闭方法：双击 dogplat 里的「开机自启-关闭.bat」，或直接删掉本文件",
    'Option Explicit',
    'Dim ws, fso',
    'Set ws  = CreateObject("WScript.Shell")',
    'Set fso = CreateObject("Scripting.FileSystemObject")',
    '',
    'If Not fso.FileExists("{app}") Then WScript.Quit 0',
    '',
    'WScript.Sleep 15000',
    'ws.CurrentDirectory = "{base}"',
    'ws.Run """{pyw}"" ""{app}""", 0, False',
]
VBS = '\r\n'.join(VBS_LINES) + '\r\n'


def script_text():
    return VBS.format(pyw=PYW, app=APP, base=BASE)


def on():
    _purge_legacy()
    os.makedirs(STARTUP_DIR, exist_ok=True)
    with open(AUTOSTART, 'w', encoding='utf-16') as f:
        f.write(script_text())
    ok = os.path.exists(AUTOSTART)
    print('[√] 开机自启已开启' if ok else '[×] 写入失败，检查启动文件夹权限')
    print(f'    启动项：{AUTOSTART}')
    print('    行为：登录 Windows 后 15 秒，自动在后台启动服务')
    return 0 if ok else 1


def off():
    _purge_legacy()
    if os.path.exists(AUTOSTART):
        os.remove(AUTOSTART)
        print('[√] 开机自启已关闭（当前运行的服务不受影响）')
    else:
        print('[i] 开机自启本来就是关着的')
    return 0


def status():
    if os.path.exists(AUTOSTART):
        print('[√] 开机自启：已开启')
        print(f'    {AUTOSTART}')
        return 0
    for p in LEGACY:
        if os.path.exists(p):
            print('[!] 检测到改名前的旧启动项（会指向旧名字，建议重新点一次「开机自启-开启.bat」）')
            print(f'    {p}')
            return 1
    print('[ ] 开机自启：未开启')
    return 1


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'on':
        sys.exit(on())
    if cmd == 'off':
        sys.exit(off())
    sys.exit(status())
