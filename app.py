import csv,json,math,queue,threading,time,traceback
from datetime import datetime,timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from dataclasses import asdict
from core import Settings,Curve,Demo,ESR

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('ESR3 · CE 传导发射工作台 | v0.2 连接修复版'); self.geometry('1160x790'); self.minsize(960,680)
        self.configure(bg='#edf2f7'); self.q=queue.Queue(); self.stop=threading.Event(); self.busy=False
        self.rows=[]; self.correction=None; self.limit=None; self.meta={}; self.logs=[]
        style=ttk.Style(self); style.theme_use('clam'); style.configure('TButton',padding=7); style.configure('TLabel',font=('Microsoft YaHei UI',10))
        head=tk.Frame(self,bg='#102b46',padx=22,pady=15); head.pack(fill='x')
        tk.Label(head,text='CE / 传导发射',bg='#102b46',fg='white',font=('Microsoft YaHei UI',22,'bold')).pack(side='left')
        tk.Label(head,text='ESR3   ·   150 kHz—30 MHz   ·   工程联调版',bg='#102b46',fg='#94c9e8',font=('Microsoft YaHei UI',11)).pack(side='right')
        pane=ttk.Frame(self,padding=12);pane.pack(fill='x'); self.v={}
        fields=[('mode','模式','模拟演示',['模拟演示','ESR3 实机']),('resource','仪器 IP / 地址','192.168.1.100',None),('phase','线路','L',['L','N']),('detector','检波器','PK',['PK','QP','CISPR_AV'])]
        for i,(key,label,value,opts) in enumerate(fields):
            ttk.Label(pane,text=label).grid(row=0,column=i*2,padx=5)
            v=self.v[key]=tk.StringVar(value=value)
            w=ttk.Combobox(pane,textvariable=v,values=opts,state='readonly',width=13) if opts else ttk.Entry(pane,textvariable=v,width=38)
            w.grid(row=0,column=i*2+1,padx=5)
        grid=ttk.Frame(self,padding=(16,2));grid.pack(fill='x')
        for i,(key,label,value) in enumerate([('start','起始 MHz','0.15'),('end','终止 MHz','30'),('step','步长 kHz','4.5'),('dwell','驻留 ms','20')]):
            ttk.Label(grid,text=label).grid(row=0,column=i*2,padx=5)
            self.v[key]=tk.StringVar(value=value);ttk.Entry(grid,textvariable=self.v[key],width=12).grid(row=0,column=i*2+1,padx=5)
        ttk.Label(grid,text='固定：CISPR 6 dB / 9 kHz').grid(row=0,column=8,padx=14)
        actions=ttk.Frame(self,padding=(16,10));actions.pack(fill='x')
        for text,cmd in [('检测连接',self.connect),('网络诊断',self.diagnose),('保存日志',self.save_log),('加载修正 CSV',self.load_correction),('加载限值 CSV',self.load_limit),('清除曲线文件',self.clear_curves),('开始测量',self.start),('停止',self.cancel),('导出 CSV+记录',self.export)]:
            ttk.Button(actions,text=text,command=cmd).pack(side='left',padx=3)
        self.note=tk.StringVar(value='LAN 使用直接 TCP 5025，无需 VISA 驱动；L/N 请手动切换 LISN。')
        ttk.Label(self,textvariable=self.note,wraplength=1120,padding=(20,4)).pack(fill='x')
        self.canvas=tk.Canvas(self,bg='#fff',highlightthickness=0,height=340);self.canvas.pack(fill='both',expand=True,padx=20,pady=8);self.canvas.bind('<Configure>',lambda e:self.draw())
        self.progress=ttk.Progressbar(self,maximum=100);self.progress.pack(fill='x',padx=20)
        self.status=tk.StringVar(value='就绪：先用模拟演示检查操作；实机版本尚未经 ESR3 联调。')
        ttk.Label(self,textvariable=self.status,padding=(20,7)).pack(fill='x')
        self.table=ttk.Treeview(self,columns=('f','raw','corr','level','limit','margin'),show='headings',height=5)
        for key,title in [('f','频率 MHz'),('raw','接收机 dBµV'),('corr','外部修正 dB'),('level','修正后 dBµV'),('limit','限值 dBµV'),('margin','裕量 dB')]:self.table.heading(key,text=title);self.table.column(key,width=150,anchor='center')
        self.table.pack(fill='x',padx=20,pady=(0,12))
        self.protocol('WM_DELETE_WINDOW',self.shutdown);self.after(80,self.pump)
    def settings(self):
        s=Settings(start=float(self.v['start'].get())*1e6,stop=float(self.v['end'].get())*1e6,step=float(self.v['step'].get())*1e3,dwell=float(self.v['dwell'].get())/1000,detector=self.v['detector'].get(),phase=self.v['phase'].get())
        s.validate();return s
    def idle(self):
        if self.busy:messagebox.showinfo('正在运行','请先停止并等待当前任务结束');return False
        return True
    def connect(self):
        if not self.idle():return
        demo=self.v['mode'].get()=='模拟演示';resource=self.v['resource'].get().strip();self.busy=True
        self.status.set('正在检测连接…')
        def work():
            dev=None
            try:
                dev=Demo() if demo else ESR(resource,lambda m:self.q.put(('log',m)))
                self.q.put(('message',dev.idn))
            except Exception as e:self.q.put(('error',str(e)))
            finally:
                if dev:
                    # Connection test must not change/abort an existing measurement.
                    if not demo:dev.io.close()
                self.q.put(('idle',None))
        threading.Thread(target=work,daemon=True).start()
    def diagnose(self):
        if not self.idle():return
        resource=self.v['resource'].get().strip();self.busy=True
        self.status.set('正在诊断 TCP 端口与 *IDN? 响应…')
        def work():
            from connection import diagnose
            try:self.q.put(('message',diagnose(resource)))
            except Exception as e:self.q.put(('error',str(e)))
            finally:self.q.put(('idle',None))
        threading.Thread(target=work,daemon=True).start()
    def save_log(self):
        p=filedialog.asksaveasfilename(defaultextension='.txt',initialfile='ESR3_connection_log.txt')
        if p:
            try:Path(p).write_text('\n'.join(self.logs),encoding='utf-8')
            except Exception as e:messagebox.showerror('保存失败',str(e))
    def load_correction(self):self.load('correction','correction_db')
    def load_limit(self):self.load('limit','limit_dbuv')
    def load(self,kind,col):
        if not self.idle():return
        p=filedialog.askopenfilename(filetypes=[('CSV','*.csv')])
        if not p:return
        try:
            c=Curve.read(p,col);setattr(self,kind,c);self.refresh_note()
        except Exception as e:messagebox.showerror('加载失败',str(e))
    def clear_curves(self):
        if self.idle():self.correction=None;self.limit=None;self.refresh_note()
    def refresh_note(self):
        self.note.set('下次测量配置：修正='+ (Path(self.correction.name).name if self.correction else '无')+'；限值='+(Path(self.limit.name).name if self.limit else '无')+'。曲线按 log(f) 插值；L/N 请手动切换。')
    def start(self):
        if not self.idle():return
        try:
            s=self.settings()
            for c in (self.correction,self.limit):
                if c:c.covers(s)
        except Exception as e:messagebox.showerror('参数错误',str(e));return
        demo=self.v['mode'].get()=='模拟演示'
        if not demo and not messagebox.askokcancel('开始 ESR3 实测', '将预置 ESR3 当前设置（*RST），使用 RF INPUT1、AC 耦合、50Ω、自动衰减、前放关闭。\n仪器现有设置需先自行保存；本程序不自动恢复。\n确认 LISN 已手动切换到 '+s.phase+'，并核对连接和外部修正文件。\n本版未实现自动过载判定，结果仅供工程联调。继续？'):return
        self.rows=[];self.logs=[];self.stop.clear();self.busy=True;self.progress['value']=0
        self.meta={'version':'0.2','simulation':demo,'settings':asdict(s),'started_utc':datetime.now(timezone.utc).isoformat(),'status':'running','correction':None if not self.correction else {'name':self.correction.name,'points':self.correction.points},'limit':None if not self.limit else {'name':self.limit.name,'points':self.limit.points},'overload_assessment':'NOT_IMPLEMENTED','compliance_verdict':'NOT_ASSESSED'}
        correction,limit=self.correction,self.limit;resource=self.v['resource'].get().strip()
        self.meta['resource']='SIMULATION' if demo else resource
        self.status.set('初始化测量…');self.draw()
        def work():
            dev=None;outcome='failed'
            try:
                dev=Demo() if demo else ESR(resource,lambda m:self.q.put(('log',m)))
                self.q.put(('metadata',{'idn':dev.idn,'readback':dev.configure(s)}))
                fs=s.frequencies()
                for i,f in enumerate(fs):
                    if self.stop.is_set():outcome='stopped';break
                    raw=dev.measure(f);corr=correction.at(f) if correction else 0;level=raw+corr;lim=limit.at(f) if limit else None
                    self.q.put(('point',{'frequency_hz':f,'receiver_dbuv':raw,'correction_db':corr,'level_dbuv':level,'limit_dbuv':lim,'margin_db':None if lim is None else lim-level}))
                    if demo and i%30==0:time.sleep(.005)
                else:outcome='complete'
            except Exception as e:self.q.put(('error',str(e)));self.q.put(('log',traceback.format_exc()))
            finally:
                if dev:
                    try:dev.close()
                    except Exception as e:outcome='failed';self.q.put(('error','关闭连接失败：'+str(e)))
                self.q.put(('finished',outcome))
        threading.Thread(target=work,daemon=True).start()
    def cancel(self):
        if self.busy:self.stop.set();self.status.set('等待当前点测量/通信结束后停止；最长取决于驻留及超时。')
    def pump(self):
        dirty=False
        for _ in range(1000):
            try:kind,data=self.q.get_nowait()
            except queue.Empty:break
            if kind=='point':self.rows.append(data);dirty=True
            elif kind=='log':self.logs.append(data)
            elif kind=='metadata':self.meta.update(data)
            elif kind=='message':self.logs.append(data);self.status.set(data);messagebox.showinfo('连接结果',data)
            elif kind=='idle':self.busy=False
            elif kind=='error':self.logs.append(data);self.status.set('错误：'+data);messagebox.showerror('任务错误',data)
            elif kind=='finished':
                self.busy=False;self.meta['status']=data;self.meta['ended_utc']=datetime.now(timezone.utc).isoformat()
                self.status.set({'complete':'测量完成','failed':'任务失败，已保留部分数据','stopped':'已停止，已保留部分数据'}[data]+' · '+str(len(self.rows))+' 点；未做符合性结论');dirty=True
        if dirty:
            self.draw();self.update_table()
            total=len(Settings(**self.meta['settings']).frequencies());self.progress['value']=100*len(self.rows)/total
            if self.busy:self.status.set(f'已采集 {len(self.rows)} / {total} 点'+(' · 模拟数据' if self.meta['simulation'] else ' · 实机数据（过载需人工核查）'))
        self.after(80,self.pump)
    def update_table(self):
        for item in self.table.get_children():self.table.delete(item)
        # Show largest corrected values, not an automatic final-measurement peak list.
        for r in sorted(self.rows,key=lambda r:r['level_dbuv'],reverse=True)[:5]:
            vals=[f"{r['frequency_hz']/1e6:.6f}"]+[('—' if r[k] is None else f'{r[k]:.2f}') for k in ('receiver_dbuv','correction_db','level_dbuv','limit_dbuv','margin_db')]
            self.table.insert('',tk.END,values=vals)
    def draw(self):
        c=self.canvas;c.delete('all');w=max(c.winfo_width(),300);h=max(c.winfo_height(),180);left,right,top,bottom=65,w-25,40,h-45
        s=self.meta.get('settings',{'start':150000,'stop':30000000})
        lo,hi=s['start'],s['stop']
        if lo==hi:lo/=1.05;hi*=1.05
        ys=[r['level_dbuv'] for r in self.rows]+[r['limit_dbuv'] for r in self.rows if r['limit_dbuv'] is not None]
        ymin=math.floor(min([0]+ys)/10)*10;ymax=max(100,math.ceil(max([100]+ys)/10)*10)
        def xy(f,v):return left+math.log(f/lo)/math.log(hi/lo)*(right-left),bottom-(v-ymin)/(ymax-ymin)*(bottom-top)
        for j in range(6):
            v=ymin+j*(ymax-ymin)/5;y=xy(lo,v)[1];c.create_line(left,y,right,y,fill='#e3eaf0');c.create_text(left-8,y,text=f'{v:g}',anchor='e',fill='#52677b')
        for f in [150000,300000,500000,1000000,3000000,5000000,10000000,30000000]:
            if lo<=f<=hi:
                x=xy(f,0)[0];c.create_line(x,top,x,bottom,fill='#e3eaf0');c.create_text(x,bottom+18,text=f'{f/1e6:g}',fill='#52677b')
        c.create_text(left,18,text='dBµV',anchor='w',fill='#52677b');c.create_text(right,bottom+32,text='MHz',anchor='e',fill='#52677b')
        for key,color in [('level_dbuv','#007ea8'),('limit_dbuv','#c36825')]:
            coords=[]
            # Preserve all samples; Tk canvas handles this bounded engineering dataset.
            for r in self.rows:
                if r[key] is not None:coords.extend(xy(r['frequency_hz'],r[key]))
            if len(coords)>=4:c.create_line(*coords,fill=color,width=2)
            elif len(coords)==2:c.create_oval(coords[0]-3,coords[1]-3,coords[0]+3,coords[1]+3,fill=color)
        label='蓝：修正后读数   橙：用户限值'
        if self.meta.get('simulation',True):label+='   |   SIMULATION / 模拟数据'
        c.create_text(right,18,text=label,anchor='e',fill='#52677b')
    def export(self):
        if not self.idle():return
        if not self.rows:messagebox.showinfo('没有数据','请先测量');return
        name=('SIM_' if self.meta.get('simulation') else 'CE_')+self.meta['settings']['phase']+'_'+self.meta['settings']['detector']+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.csv'
        p=filedialog.asksaveasfilename(defaultextension='.csv',initialfile=name,filetypes=[('CSV','*.csv')])
        if not p:return
        base=Path(p);side=base.with_suffix('.json');log=base.with_suffix('.log')
        if any(f.exists() for f in (side,log)) and not messagebox.askyesno('覆盖记录','同名 JSON 或日志已存在，是否覆盖？'):return
        try:
            fields=list(self.rows[0])+['simulation','phase','detector','run_status','overload_assessment']
            with base.open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
                for r in self.rows:writer.writerow(dict(r,simulation=self.meta['simulation'],phase=self.meta['settings']['phase'],detector=self.meta['settings']['detector'],run_status=self.meta['status'],overload_assessment='NOT_IMPLEMENTED'))
            side.write_text(json.dumps(self.meta,ensure_ascii=False,indent=2),encoding='utf-8');log.write_text('\n'.join(self.logs),encoding='utf-8')
            self.status.set('已导出 CSV、JSON 测量记录和 SCPI 日志：'+str(base))
        except Exception as e:messagebox.showerror('保存失败',str(e))
    def shutdown(self):
        if self.busy:
            self.cancel();messagebox.showinfo('等待停止','请等待当前点结束后再关闭，以便释放仪器连接。');return
        self.destroy()

if __name__=='__main__':
    import sys
    ui=App()
    if len(sys.argv)==3 and sys.argv[1]=='--smoke-test':
        target=Path(sys.argv[2]); started=time.monotonic()
        ui.v['end'].set('0.2')
        ui.after(100,ui.start)
        def check():
            if time.monotonic()-started>30:
                target.write_text('TIMEOUT',encoding='utf-8');ui.destroy();return
            if ui.meta.get('status')=='complete' and not ui.busy:
                ok=len(ui.rows)==13 and len(ui.table.get_children())==5
                target.write_text('PASS' if ok else 'FAIL',encoding='utf-8');ui.destroy();return
            ui.after(100,check)
        ui.after(300,check)
    ui.mainloop()
