"""LAN resource normalization and read-only SCPI connection diagnostics."""
import re
import socket

def address(resource):
    value=resource.strip()
    if re.fullmatch(r'[A-Za-z0-9_.-]+',value):
        host,port=value,5025
    else:
        m=re.fullmatch(r'TCPIP\d*::([^:]+)(?:::(?:(\d+)::SOCKET|(?:inst0::)?INSTR))?',value,re.I)
        if not m:raise ValueError('请输入仪器 IP，或 TCPIP::IP::5025::SOCKET；本版 LAN 直连不接受 HiSLIP/GPIB 地址。')
        host,port=m[1],int(m[2] or 5025)
    if not 1<=port<=65535:raise ValueError('TCP 端口必须为 1～65535')
    return host,port

BACKENDS = ('R&S VISA / VXI-11', '系统默认 VISA / VXI-11', 'PyVISA / VXI-11', '直接 Socket')

def connection_plan(value, backend):
    host,port=address(value)
    if backend not in BACKENDS:raise ValueError('未知通信后端')
    if backend=='直接 Socket':
        return f'TCPIP::{host}::{port}::SOCKET', 'SelectVisa=SocketIo, OpenTimeout=10000, VisaTimeout=10000'
    if value.strip().upper().endswith('::SOCKET'):
        raise ValueError('当前选择 VXI-11，请输入 IP 或 ::inst0::INSTR 地址；Socket 地址请配合“直接 Socket”选项')
    resource=value.strip() if '::' in value else f'TCPIP0::{host}::inst0::INSTR'
    if '::' in resource and not resource.upper().endswith('::INSTR'):
        resource=f'TCPIP0::{host}::inst0::INSTR'
    options='OpenTimeout=10000, VisaTimeout=10000'
    if backend==BACKENDS[0]:options='SelectVisa=rs, '+options
    if backend==BACKENDS[2]:options='SelectVisa=py, '+options
    return resource, options

def resource_name(value):
    return connection_plan(value, BACKENDS[0])[0]

def diagnose(value):
    host,port=address(value)
    try:
        with socket.create_connection((host,port),timeout=4) as s:
            s.settimeout(4);s.sendall(b'*IDN?\n');data=bytearray()
            while b'\n' not in data:
                part=s.recv(1024)
                if not part:raise RuntimeError('连接已建立，但仪器未返回完整标识就关闭连接')
                data.extend(part)
                if len(data)>8192:raise RuntimeError('返回内容过长，不像 SCPI 标识')
            ident=data.decode('ascii',errors='replace').strip()
            return f'TCP {host}:{port} 可达\n*IDN? 返回：{ident}'
    except ConnectionRefusedError as e:
        raise RuntimeError(f'{host}:{port} 拒绝连接。请核对仪器 IP、Socket 远控服务及防火墙端口设置。') from e
    except (socket.timeout,TimeoutError) as e:
        raise RuntimeError(f'{host}:{port} 连接或标识查询超时。请核对电脑与仪器的 IP/子网及网络路径；超时不能单独证明缺少驱动。') from e
    except OSError as e:
        raise RuntimeError(f'{host}:{port} 网络连接失败：{e}') from e
