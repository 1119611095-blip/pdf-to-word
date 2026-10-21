"""ESR3 CE engineering prototype. All levels dBuV, all frequencies Hz."""
import bisect
import csv
import math
from dataclasses import dataclass, asdict

DETECTORS = {'PK': 'POS', 'QP': 'QPE', 'CISPR_AV': 'CAV'}

@dataclass(frozen=True)
class Settings:
    start: float = 150000
    stop: float = 30000000
    step: float = 4500
    dwell: float = 0.02
    detector: str = 'PK'
    phase: str = 'L'
    rbw: float = 9000
    def validate(self):
        if not all(math.isfinite(x) for x in (self.start,self.stop,self.step,self.dwell,self.rbw)):
            raise ValueError('参数必须是有限数值')
        if not 150000 <= self.start <= self.stop <= 30000000:
            raise ValueError('第一版范围限定为 150 kHz～30 MHz；单点测量可令起止频率相同')
        if not 1 <= self.step <= self.rbw/2:
            raise ValueError('步长必须为 1～4500 Hz（不超过带宽的一半）')
        if self.rbw != 9000 or not 0.001 <= self.dwell <= 100:
            raise ValueError('本版固定 CISPR 9 kHz；驻留时间范围 1～100000 ms')
        if self.detector not in DETECTORS or self.phase not in ('L','N'):
            raise ValueError('无效检波器或线路')
        if len(self.frequencies()) > 100000:
            raise ValueError('超过 100000 点，请增大步长或缩小频段')
    def frequencies(self):
        n = math.floor((self.stop-self.start)/self.step)
        if n > 100000: return range(100001)
        fs = [self.start+i*self.step for i in range(n+1)]
        if fs[-1] < self.stop: fs.append(self.stop)
        return fs

class Curve:
    def __init__(self, points, name=''):
        self.points = list(points); self.name = name
        if len(self.points)<2: raise ValueError('曲线至少需要两行数据')
        self.x = [p[0] for p in self.points]
        if any(not math.isfinite(x) or x<=0 for x in self.x): raise ValueError('频率无效')
        if any(not math.isfinite(y) for _,y in self.points): raise ValueError('数值无效')
        if any(a>=b for a,b in zip(self.x,self.x[1:])): raise ValueError('频率必须严格递增且不能重复')
    @classmethod
    def read(cls, path, column):
        with open(path,encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            if not {'frequency_hz',column}.issubset(reader.fieldnames or []):
                raise ValueError('CSV 表头必须包含 frequency_hz,'+column)
            return cls([(float(r['frequency_hz']),float(r[column])) for r in reader],str(path))
    def at(self,f):
        if not self.x[0]<=f<=self.x[-1]: raise ValueError('曲线不覆盖测试频率，禁止外推')
        j=bisect.bisect_left(self.x,f)
        if j==0:return self.points[0][1]
        a,ya=self.points[j-1]; b,yb=self.points[j]
        t=math.log(f/a)/math.log(b/a)
        return ya+t*(yb-ya)
    def covers(self,s):
        self.at(s.start); self.at(s.stop)

class Demo:
    idn='SIMULATION — 虚拟数据，不是实测'
    def __init__(self,*args): pass
    def configure(self,s): self.s=s; return {'mode':'SIMULATION'}
    def measure(self,f):
        z=math.log10(f/150000)
        value=28+5*math.sin(z*14)+30*math.exp(-((z-.52)/.027)**2)+21*math.exp(-((z-1.45)/.04)**2)
        return value-{'PK':0,'QP':4,'CISPR_AV':9}[self.s.detector]
    def close(self):pass

class ESR:
    def __init__(self,resource,log=lambda msg:None,backend='R&S VISA / VXI-11'):
        from RsInstrument import RsInstrument
        from connection import connection_plan
        self.log=log
        normalized,options=connection_plan(resource,backend)
        self.log('通信后端：'+backend+'；地址：'+normalized+'；超时 10 s')
        try:
            self.io=RsInstrument(normalized,id_query=True,reset=False,options=options)
        except Exception as exc:
            hint=('本版为 64 位程序。请核查 R&S VISA 的 64 位组件；也可选择“系统默认 VISA / VXI-11”。'
                  if backend=='R&S VISA / VXI-11' else '请核查所选后端、仪器地址和网络连接。')
            raise RuntimeError('连接失败：'+backend+'\n'+normalized+'\n'+hint+
                '\n请停止其他软件对接收机的测量/控制后重试。\n详细错误：'+str(exc)) from exc
        try:
            self.io.visa_timeout=10000
            self.io.opc_timeout=120000
            self.io.instrument_status_checking=True
            self.idn=self.query('*IDN?')
            import re
            parts=self.idn.split(',')
            if len(parts)<2 or not re.fullmatch(r'ESR[- ]?3',parts[1].strip(),re.I):
                raise RuntimeError('设备不是 ESR3：'+self.idn)
        except Exception:
            self.io.close(); raise
    def query(self,c):
        v=self.io.query_str(c); self.log(c+' → '+v); return v
    def write(self,c):
        self.log(c); self.io.write_str(c)
    def configure(self,s):
        self.s=s
        # A deliberate preset is disclosed in the GUI before starting real acquisition.
        self.log('*RST (preset)')
        self.io.write_str_with_opc('*RST')
        for c in ('INST:SEL REC','ABOR','INIT1:CONT OFF','FREQ:MODE CW',
                  'FORM ASC','CALC:UNIT:POW DBUV','INP:TYPE INPUT1','INP:COUP AC',
                  'INP:IMP 50','INP:ATT:PROT ON','INP:ATT:AUTO ON',
                  'INP:GAIN:AUTO OFF','INP:GAIN:STAT OFF','DISP:BARG:TCO OFF',
                  'BAND:TYPE CISPR','BAND:AUTO OFF','BAND 9000',
                  'DET:REC '+DETECTORS[s.detector],f'SWE:TIME {s.dwell}'):
            self.write(c)
        readings={c:self.query(c) for c in ('INST:SEL?','BAND?','BAND:TYPE?',
                    'CALC:UNIT:POW?','DET:REC?','SWE:TIME?','INP:ATT:AUTO?','INP:GAIN:STAT?',
                    'CORR:TRAN:ACT?')}
        if readings['CORR:TRAN:ACT?'].strip().strip("\"'"):
            raise RuntimeError('仪器仍存在活动修正系数，停止以防重复修正')
        if abs(float(readings['BAND?'])-9000)>1 or readings['BAND:TYPE?'].strip().upper() not in ('PULS','PULSE','CISP','CISPR'):
            raise RuntimeError('实机带宽回读不匹配，停止采集')
        if readings['CALC:UNIT:POW?'].strip().upper()!='DBUV': raise RuntimeError('实机单位不是 dBuV')
        det=readings['DET:REC?'].strip().upper()
        if ',' in det or not det.startswith(DETECTORS[s.detector]): raise RuntimeError('实机检波器回读不匹配')
        if not math.isclose(float(readings['SWE:TIME?']),s.dwell,rel_tol=.01,abs_tol=1e-6): raise RuntimeError('驻留时间回读不匹配')
        return readings
    def measure(self,f):
        self.write(f'FREQ:CENT {f:.12g}')
        actual=float(self.query('FREQ:CENT?'))
        if abs(actual-f)>1: raise RuntimeError('实际频率与目标不一致')
        self.log('INIT1:IMM; *OPC?')
        self.io.write_str_with_opc('INIT1:IMM',max(10000,int(self.s.dwell*1000+10000)))
        values=[float(v) for v in self.query('TRAC? SINGLE').strip().split(',')]
        if len(values)!=1 or not math.isfinite(values[0]) or abs(values[0])>1000:
            raise RuntimeError('无效 SINGLE 结果，停止以避免错误数据')
        return values[0]
    def close(self):
        try:self.write('ABOR')
        finally:self.io.close()
