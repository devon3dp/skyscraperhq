#!/usr/bin/env python3
"""QSB GPU thermal guardian — FULL PERFORMANCE + aggressive proactive fans.
The GPU is a brand-new RTX 5070 Ti and should run at FULL clocks. So we do NOT
throttle clocks under normal load — instead we ramp the FANS hard and early
(proactively, on utilisation) to keep it cool AT full performance. Clocks are
only capped in a genuine thermal emergency as a last-resort safety net."""
import subprocess, time, os
LOG="/vaults/nvme0/qsb_tower_v1/data/logs/gpu_fan.log"; PW="ross"; FD=":1"
def sudo(a):
    try: return subprocess.run(["sudo","-S"]+a,input=PW+"\n",capture_output=True,text=True,timeout=8).stdout
    except Exception: return ""
def nvset(attr):
    try: subprocess.run(["sudo","-S","env","DISPLAY="+FD,"nvidia-settings","-c",FD,"-a",attr],
                        input=PW+"\n",capture_output=True,text=True,timeout=8)
    except Exception: pass
def smi(q):
    try: return subprocess.run(["nvidia-smi",f"--query-gpu={q}","--format=csv,noheader,nounits"],
                              capture_output=True,text=True,timeout=5).stdout.strip().splitlines()[0]
    except Exception: return None
# AGGRESSIVE proactive fan % keyed on load(util/power) — cool at FULL clocks.
def target_fan(util, temp, load):
    if temp>=80: return 100
    if temp>=72: return 95
    if temp>=64: return 88
    if load>=60: return 90      # heavy load -> fans hard so clocks stay full
    if load>=35: return 78
    if load>=15: return 65      # load arriving -> ramp early (proactive)
    if load>=3:  return 50
    if temp>=50: return 42
    return 32                    # idle floor
# clocks: FULL performance — only emergency-cap if it ever runs away hot
def emergency_clock(temp):
    if temp>=86: return 2200    # last-resort safety only
    return 0                     # 0 = full/unlocked
def log(m):
    l=time.strftime("%H:%M:%S ")+m
    try: open(LOG,"a").write(l+"\n")
    except Exception: pass
    print(l,flush=True)
def ensure_x():
    import subprocess
    try:
        if subprocess.run(["pgrep","-f","Xorg :1"],capture_output=True).returncode!=0:
            subprocess.run(["sudo","-S","bash","-c",
                "setsid Xorg :1 -config /etc/X11/xorg.nvidia-fan.conf -novtswitch -sharevts -noreset >/tmp/xorg_nvfan.log 2>&1 </dev/null & disown"],
                input="ross\n",text=True,timeout=10)
            time.sleep(6)
    except Exception: pass
def main():
    ensure_x()
    sudo(["nvidia-smi","-pm","1"]); sudo(["nvidia-smi","-pl","330"])  # full power headroom
    sudo(["nvidia-smi","-rgc"])                                        # ensure clocks UNLOCKED
    nvset("[gpu:0]/GPUFanControlState=1")
    log("guardian: FULL-PERFORMANCE mode — full clocks, aggressive proactive fans")
    lf=lc=None
    while True:
        v=smi("utilization.gpu,temperature.gpu,power.draw,power.limit,fan.speed")
        if v:
            try: u,t,p,pl,f=[float(x.strip()) for x in v.split(",")]
            except Exception: time.sleep(1.5); continue
            load=max(u,100.0*p/pl if pl else 0)
            wf=target_fan(u,t,load); wc=emergency_clock(t)
            if lf is None or abs(wf-lf)>=6:
                nvset(f"[fan:0]/GPUTargetFanSpeed={int(wf)}"); nvset(f"[fan:1]/GPUTargetFanSpeed={int(wf)}")
                log(f"util={u:.0f}% temp={t:.0f}C load={load:.0f}% pow={p:.0f}W clk-full -> FAN {int(wf)}%")
                lf=wf
            if wc!=lc:
                sudo(["nvidia-smi","-rgc"] if wc==0 else ["nvidia-smi","-lgc",f"0,{wc}"])
                if wc: log(f"EMERGENCY temp={t:.0f}C -> clock cap {wc}MHz")
                lc=wc
        time.sleep(1.5)
if __name__=="__main__": main()
