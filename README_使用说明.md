# ESR3 CE v0.3

本版本修正 v0.2 强制把所有 LAN 地址转成 Socket 的行为。
默认后端为 R&S VISA / VXI-11；可选系统默认 VISA、PyVISA VXI-11、直接 Socket。
VXI-11 完整地址示例 TCPIP0::192.168.1.100::inst0::INSTR。裸 IP 自动补全。
VXI-11 连接不会自动转为 Socket；只有显式选择直接 Socket 才使用 TCP 5025。
超时 10 秒。R&S VISA 模式需要本机可用的 64 位 R&S VISA；EXE 自带 Python，不能代替厂商驱动。
使用官方软件时能访问不保证其 VISA 组件的位数与本程序相同。未安装 R&S VISA 时可试系统默认或 PyVISA 后端。

先停止其他软件对接收机的控制，然后在本软件检测连接。
网络诊断使用所选协议，只读取标识，不执行 *RST 或 INIT 测量。
实测前会提示执行 *RST，原配置需要自行保存。
150 kHz～30 MHz，固定 9 kHz CISPR 带宽，PK/QP/CISPR Average，每次一个检波器。
L/N 手动切换。默认 20 ms 为 PK 联调参数，最终测量时间按测试方法设置。
本程序不判断过载、不提供正式合规结论；需 ESR3 实机联调。
修正 CSV：frequency_hz,correction_db；限值 CSV：frequency_hz,limit_dbuv。
两类 CSV 均须频率严格递增、覆盖测试频段；按 log(f) 插值。
导出 CSV、JSON、SCPI 日志。模拟数据不是实测。
