#!/usr/bin/python3
# -*- coding: utf-8 -*-

from typing import Union
from scp import SCPClient
from socket import socket
from os.path import dirname
from pydantic import FilePath
from os import chmod, PathLike
from typing_extensions import Self
from typing import Any, Optional, Union
from paramiko import ssh_exception, SSHClient, AutoAddPolicy, Channel

_CMD_ALLOW_TCP_FORWARD = 'sed -i.bak "s,AllowTcpForwarding no,AllowTcpForwarding yes,g" %s'
_CMD_RESTART_SSHD = '/etc/init.d/ssh restart'

class SSHConnect:
    """通过 ``SSH`` 协议访问远程机台执行相关操作
    (使用上下文特性结束后自动关闭 ``SSH`` 连线会话)

    Attributes
    ----------
    - host    : (str)        : 访问 `IP` 地址
    - username: (str)        : 用户名，默认: `root`
    - password: (str)        : 密码，默认: `111111`
    - port    : (int)        : 连线端口号，默认: `22`
    - timeout : (float)      : 连线超时时长，默认: `10.0 秒`
    - sock    : (socket|None): 与目标已创建连接的通道 (:class:`~Channel`)

    Methods
    -------
    create()
        创建 `SSH` 连线，返回已连接对象 `SSHClient` 实例

    is_alive()
        检查会话是否存在，返回布林值

    proxy(dest_addr, sshd_cfg='/etc/ssh/sshd_config')
        创建嵌套跳板连线的来源通道，提供 `Socket:返回通道对象给远程目标`

    run(command='ls')
        远程执行指定命令，返回元组 (`tuple[命令标准输出/错误, 命令返回值]`)

    pscp(src='', dst='', perm=0, pull=False, recursive=False)
        遠程傳送/拉取文件，功能類似 `Linux` 命令的 ``scp``

    Examples
    -------
    远程连线到对端执行 `whoami` 命令
    ```
    with SSHConnect('172.17.11.121', username='sysadmin') as ssh:
        ssh.run('whoami')
    ```
    >>> ('sysadmin\\n', 0)

    嵌套连线以 `172.17.11.121` 为来源机台，连线到目标机台 `192.168.111.11` 执行命令 (跳板操作)
    ```
    with SSHConnect('172.17.11.121', username='sysadmin') as ssh:
        src_channel = ssh.proxy(( '192.168.111.11', 22 ), '/conf/ssh_server_config')
        with SSHConnect('192.168.111.11', 'sysadmin', sock=src_channel) as dst:
            print(dst.run('ifconfig -a eth0'))
    ```
    >>> 'eth0      Link encap:Ethernet  HWaddr 38:68:DD:39:BC:07 ...'

    傳送文件至遠程機台 (`vim74.tar.gz` = 文件, `vim74` = 目錄)
    ```
    with SSHConnect('172.17.11.121', username='sysadmin') as ssh:
        ssh.pscp('./vim74.tar.gz', '/tmp')
        ssh.pscp('./vim74', '/tmp', recursive=True)
    ```

    拉取文件來自遠程機台 (`autoLogoutPIDEntryTable` = 文件, `/tmp/audit` = 目錄)
    ```
    with SSHConnect('172.17.11.121', username='sysadmin') as ssh:
        ssh.pscp('/tmp/audit/autoLogoutPIDEntryTable', '/usr/src/tools', pull=True)
        ssh.pscp('/tmp/audit', '/usr/src/tools', pull=True, recursive=True)
    ```
    """
    def __init__(self,
        host: str = '', username: str = 'root', password: str = '111111',
        port: int = 22, timeout: Union[float, int] = 10.0,
        sock: Optional[socket] = None
    ) -> None:
        assert host, 'invalid host'
        self.host,self.port = host, port
        self.username, self.password = username, password
        self.timeout, self.sock = timeout, sock

    def __repr__(self) -> str:
        return str(self.client.get_transport()) if self.__dict__.get('client') else 'no session'

    def __call__(self) -> None:
        print('connect succeeded' if self.is_alive() else 'connect failured')

    def __enter__(self) -> Self:
        self.create()
        return self

    def __exit__(self, type: Any, value: Any, traceback: Any) -> None:
        if self.is_alive() is True:
            self.client.close()
        if any(( type, value, traceback )):
            assert False, value

    def create(self) -> Union[SSHClient, None]:
        if not self.is_alive():
            self.client = SSHClient()
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(AutoAddPolicy())
            self.client.connect(self.host,
                                username=self.username,
                                password=self.password,
                                port=self.port,
                                timeout=self.timeout,
                                sock=self.sock)
            transport = self.client.get_transport()
            transport.set_keepalive(int(self.timeout))
            return self.client

    def is_alive(self) -> bool:
        if not self.__dict__.get('client'):
            return False
        if self.client.get_transport() is not None:
            return self.client.get_transport().is_active()
        return False

    def proxy(self, dest_addr: tuple[str, int],
                    sshd_cfg: FilePath = '/etc/ssh/sshd_config') -> Channel:
        cmd = f'{_CMD_ALLOW_TCP_FORWARD % sshd_cfg}; {_CMD_RESTART_SSHD}'
        args = ( 'direct-tcpip', dest_addr, ( self.host, self.port ) )
        try:
            return self.client.get_transport().open_channel(*args, timeout=self.timeout)
        except ssh_exception.ChannelException:
            assert self.run(cmd)[1] == 0, 'SSH service encountered error'
            self.client.close()
            self.create()
        return self.client.get_transport().open_channel(*args, timeout=self.timeout)

    def run(self, command: str = 'ls') -> tuple[str, int]:
        _, stdout, stderr = self.client.exec_command(command)
        output = ''.join(stderr.readlines() + stdout.readlines())
        status_code = stdout.channel.recv_exit_status()
        return ( output, status_code )

    def pscp(self, src: Union[str, PathLike] = '', dst: Union[str, PathLike] = '',
        perm: int = 0, pull: bool = False, recursive: bool = False) -> None:
        with SCPClient(self.client.get_transport()) as scp:
            if pull:
                scp.get(src, dst, recursive=recursive)
                chmod(dst, 0o755)
            else:
                self.run(f'mkdir -p {dirname(dst)}')
                scp.put(src, dst, recursive=recursive)
                if perm > 0: self.run(f'chmod {perm} {dst}')

if __name__ == '__main__':
    with SSHConnect('172.17.11.121', username='sysadmin') as ssh:
        src_channel = ssh.proxy(( '192.168.111.11', 22 ), '/conf/ssh_server_config')
        with SSHConnect('192.168.111.11', 'sysadmin', sock=src_channel) as dst:
            print(dst.run('ifconfig -a eth0'))
        ssh.pscp('/tmp/audit', '/tmp', pull=True, recursive=True)
