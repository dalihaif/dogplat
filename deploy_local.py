# -*- coding: utf-8 -*-
"""在本机以独立后台进程启动狗狗管理平台（不依赖任何父进程/终端）

用法：
    python deploy_local.py          启动（已在跑就跳过）
    python deploy_local.py stop     停止
    python deploy_local.py status   查看状态
    python deploy_local.py restart  重启
"""
import os
import socket
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VENV = r'C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts'


def _resolve_venv():
    """优先读 py_path.txt（安装时写入），否则用默认路径。"""
    cfg = os.path.join(BASE, 'py_path.txt')
    if os.path.exists(cfg):
        with open(cfg, encoding='utf-8', errors='ignore') as f:
            p = f.read().strip().strip('"')
        if p and os.path.exists(os.path.join(p, 'python.exe')):
            return p
    return DEFAULT_VENV


VENV = _resolve_venv()
PYW = os.path.join(VENV, 'pythonw.exe')
PY = os.path.join(VENV, 'python.exe')
APP = os.path.join(BASE, 'app.py')
PORT = int(os.environ.get('DOGPLAT_PORT', 5800))

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def port_open(port=PORT):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


def pids_on_port(port=PORT):
    out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                         encoding='gbk', errors='replace').stdout
    pids = set()
    for line in out.splitlines():
        if f':{port}' in line and 'LISTENING' in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(int(parts[-1]))
    return pids


def start(wait=True):
    if port_open():
        print(f'服务已在运行：http://127.0.0.1:{PORT}')
        return 0

    exe = PYW if os.path.exists(PYW) else PY
    log = open(os.path.join(BASE, 'data', 'server.out'), 'a', encoding='utf-8')
    p = subprocess.Popen(
        [exe, APP],
        cwd=BASE,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        close_fds=True,
    )
    print(f'已启动独立后台进程 PID={p.pid}（{os.path.basename(exe)}）')

    if not wait:
        return 0
    for i in range(30):
        time.sleep(1)
        if port_open():
            print(f'[√] 服务就绪：http://127.0.0.1:{PORT}')
            addr = os.path.join(BASE, 'data', '访问地址.txt')
            if os.path.exists(addr):
                print('-' * 58)
                with open(addr, encoding='utf-8') as f:
                    print(f.read().strip())
                print('-' * 58)
            return 0
        print(f'    等待启动… {i + 1}s')
    print('[×] 30 秒内未就绪，检查 data\\server.log')
    return 1


def stop():
    pids = pids_on_port()
    if not pids:
        print(f'端口 {PORT} 上没有运行中的服务')
        return 0
    for pid in pids:
        r = subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                           capture_output=True, text=True, encoding='gbk',
                           errors='replace')
        print(f'  结束 PID {pid}｜{"成功" if r.returncode == 0 else "失败"}')
    time.sleep(1)
    print('已停止' if not port_open() else '仍在监听，请用管理员权限重试')
    return 0


def status():
    if port_open():
        print(f'● 运行中  http://127.0.0.1:{PORT}   PID={sorted(pids_on_port())}')
        addr = os.path.join(BASE, 'data', '访问地址.txt')
        if os.path.exists(addr):
            with open(addr, encoding='utf-8') as f:
                for line in f:
                    if '局域网' in line:
                        print('  ' + line.strip())
        return 0
    print('○ 未运行')
    return 1


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'start'
    if cmd == 'start':
        sys.exit(start())
    if cmd == 'stop':
        sys.exit(stop())
    if cmd == 'restart':
        stop()
        time.sleep(1)
        sys.exit(start())
    if cmd == 'status':
        sys.exit(status())
    print(__doc__)
    sys.exit(2)
