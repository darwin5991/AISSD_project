"""Strict v2 assembler. # and // comments; integer .equ, labels, LI, SETADDR."""
import re
from pathlib import Path

CSRS = dict(zip(('SRC0_BASE','SRC1_BASE','DST_BASE','BIAS_BASE','GEMM_DIM','GEMM_CFG','ARG_SRC','ARG_LEN','PERF_COUNT','STATUS'),
                (0x7c0,0x7c1,0x7c2,0x7c3,0x7c4,0x7c7,0x7e0,0x7e1,0x7f0,0x7f2)))
RW = set(CSRS.values()) - {0x7f0,0x7f2}

def reg(s):
    if not re.fullmatch('[xr][0-7]',s.lower()): raise ValueError('register '+s)
    return int(s[1:])

def bounded(n, lo, hi):
    if not lo <= n <= hi: raise ValueError(f'{n} outside [{lo},{hi}]')
    return n

def assemble(source):
    symbols = dict(CSRS)
    def val(s):
        return symbols[s.upper()] if s.upper() in symbols else int(s,0)
    ops=[]
    for line in source.splitlines():
        line=re.split(r'#|//',line)[0].strip()
        if not line: continue
        if ':' in line:
            label,line=line.split(':',1)
            key=label.strip().upper()
            if key in symbols: raise ValueError('duplicate '+key)
            symbols[key]=4*len(ops)
            line=line.strip()
            if not line: continue
        t=[x for x in re.split(r'[\s,()]+',line) if x]
        m=t[0].upper(); a=t[1:]
        if m=='.EQU':
            if a[0].upper() in symbols: raise ValueError('duplicate symbol')
            symbols[a[0].upper()]=val(a[1]); continue
        if m=='SETADDR':
            dest=a[0]; t=['LI','x4',a[1]]; m='LI'; a=t[1:]
        else: dest=None
        if m=='LI':
            n=val(a[1]); bounded(n,-2**31,2**32-1)
            n=((n+2**31)%2**32)-2**31
            low=((n+2048)&4095)-2048
            if n==low: ops.append(('ADDI',[a[0],'x0',str(low)]))
            else:
                ops.append(('LUI',[a[0],str(((n-low)>>12)&0xfffff)]))
                if low: ops.append(('ADDI',[a[0],a[0],str(low)]))
            if dest: ops.append(('CSRW',[dest,'x4']))
        else: ops.append((m,a))
    words=[]
    for pc,(m,a) in enumerate(ops):
        pc*=4
        if m=='LUI': w=(bounded(val(a[1]),0,0xfffff)<<12)|(reg(a[0])<<7)|0x37
        elif m in ('ADD','AND','OR'):
            w=reg(a[2])<<20|reg(a[1])<<15|{'ADD':0,'AND':7,'OR':6}[m]<<12|reg(a[0])<<7|0x33
        elif m in ('ADDI','ANDI','ORI','SLLI','SRLI'):
            n=bounded(val(a[2]),0,31) if m in ('SLLI','SRLI') else bounded(val(a[2]),-2048,2047)
            w=(n&4095)<<20|reg(a[1])<<15|{'ADDI':0,'ANDI':7,'ORI':6,'SLLI':1,'SRLI':5}[m]<<12|reg(a[0])<<7|0x13
        elif m in ('LW','SW'):
            n=bounded(val(a[1]),-2048,2047)&4095; r=reg(a[0]); base=reg(a[2])
            w=(n<<20|base<<15|2<<12|r<<7|3) if m=='LW' else ((n>>5)<<25|r<<20|base<<15|2<<12|(n&31)<<7|0x23)
        elif m in ('BEQ','BNE','JAL'):
            off=val(a[-1])-pc
            if off%4 or not 0 <= val(a[-1]) < len(ops)*4: raise ValueError('branch target')
            if m=='JAL':
                n=bounded(off,-2**20,2**20-1)&0x1fffff
                w=(n>>20)<<31|((n>>1)&1023)<<21|((n>>11)&1)<<20|((n>>12)&255)<<12|reg(a[0])<<7|0x6f
            else:
                n=bounded(off,-4096,4095)&8191
                w=(n>>12)<<31|((n>>5)&63)<<25|reg(a[1])<<20|reg(a[0])<<15|(m=='BNE')<<12|((n>>1)&15)<<8|((n>>11)&1)<<7|0x63
        elif m in ('CSRW','CSRR','SETI'):
            c=val(a[1] if m=='CSRR' else a[0])
            if c not in CSRS.values() or (m!='CSRR' and c not in RW): raise ValueError('CSR access')
            if m=='SETI': w=(bounded(val(a[1]),-4096,4095)&8191)<<19|c<<7|0xb
            elif m=='CSRW': w=c<<20|reg(a[1])<<15|1<<12|0x73
            else: w=c<<20|2<<12|reg(a[0])<<7|0x73
        elif m in ('LOAD','STORE'): w=reg(a[1])<<20|reg(a[0])<<15|(m=='STORE')<<12|reg(a[2])<<7|0x2b
        elif m=='EXEC':
            if a[0].upper()=='GEMM' and len(a)==1: w=0x202b
            elif a[0].upper()=='ARGMAX' and len(a)==2: w=0x0200202b|reg(a[1])<<7
            else: raise ValueError('EXEC operands')
        elif m in ('TSTART','TSTOP','END'): w={'TSTART':0x302b,'TSTOP':0x0200302b,'END':0x0400302b}[m]
        else: raise ValueError('unsupported '+m)
        words.append(w)
    if len(words)>16384: raise ValueError('IMEM capacity')
    return words

def write_hex(path,words):
    Path(path).write_text(''.join(f'{int(w)&0xffffffff:08x}\n' for w in words),encoding='ascii')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('source'); p.add_argument('output'); a=p.parse_args()
    write_hex(a.output,assemble(Path(a.source).read_text()))
