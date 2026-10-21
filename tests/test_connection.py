import socketserver,threading,unittest
from connection import address,resource_name,diagnose
class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.server.commands.append(self.rfile.readline().strip())
        self.wfile.write(b'Rohde&Schwarz,ESR3,TEST,3.66\n')
class ConnectionTest(unittest.TestCase):
    def test_normalization(self):
        for s in ('192.168.1.23','TCPIP::192.168.1.23::INSTR','TCPIP0::192.168.1.23::inst0::INSTR','TCPIP::192.168.1.23::5025::SOCKET'):
            self.assertEqual(resource_name(s),'TCPIP::192.168.1.23::5025::SOCKET')
    def test_reject_bad_resource(self):
        for s in ('','TCPIP::host::hislip0::INSTR','abc\n*RST','TCPIP::host::99999::SOCKET'):
            with self.assertRaises(ValueError):address(s)
    def test_readonly_network_diagnostic(self):
        with socketserver.TCPServer(('127.0.0.1',0),Handler) as server:
            server.commands=[]
            worker=threading.Thread(target=server.handle_request);worker.start()
            result=diagnose(f'TCPIP::127.0.0.1::{server.server_address[1]}::SOCKET')
            worker.join(5)
            self.assertIn('ESR3',result);self.assertEqual(server.commands,[b'*IDN?'])

class SCPIHandler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            line=self.rfile.readline()
            if not line:return
            cmd=line.decode().strip().upper();self.server.commands.append(cmd)
            if '?' in cmd:
                if '*IDN?' in cmd:answer='Rohde&Schwarz,ESR3,TEST,3.66'
                elif '*OPT?' in cmd:answer='0'
                elif 'SYST:ERR?' in cmd or 'SYSTEM:ERROR?' in cmd:answer='0,"No error"'
                elif '*OPC?' in cmd:answer='1'
                else:answer='0'
                self.wfile.write((answer+'\n').encode());self.wfile.flush()

class SocketBackendTest(unittest.TestCase):
    def test_official_backend_without_visa(self):
        from core import ESR
        with socketserver.TCPServer(('127.0.0.1',0),SCPIHandler) as server:
            server.commands=[]
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            dev=None
            try:
                dev=ESR(f'TCPIP::127.0.0.1::{server.server_address[1]}::SOCKET')
                self.assertIn('ESR3',dev.idn)
                self.assertFalse(any('*RST' in c or 'INIT' in c for c in server.commands))
            finally:
                if dev:dev.io.close()
                server.shutdown();worker.join(5)
