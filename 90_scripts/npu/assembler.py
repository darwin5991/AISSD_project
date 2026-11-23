"""Small checked application assembler using the verified Phase 1..6 encoders."""
import run_phase1 as p1
import phase2_vectors as p2
import phase3_vectors as p3
import phase4_vectors as p4
import phase5_vectors as p5
import phase6_vectors as p6

CSR = p2.RW
LAYERS = (
    (0x80000000,0x80040000,0x80020000,0x800C0000,1,512,784,3,10,1),
    (0x80020000,0x80058800,0x80000000,0x800C0200,1,128,512,1,7,1),
    (0x80000000,0x8005C800,0x80020000,0x800C0280,1,10,128,2,7,0),
)

def gpr(*registers):
    if any(type(r) is not int or not 0 <= r <= 7 for r in registers):
        raise ValueError("application uses r0..r7 only")

class Assembler:
    def __init__(self, imem_bytes=65536):
        if imem_bytes <= 0 or imem_bytes % 4:
            raise ValueError("invalid IMEM capacity")
        self.imem_bytes = imem_bytes
        self.words, self.listing, self.labels, self.fixups = [], [], {}, []

    @property
    def pc(self):
        return 4 * len(self.words)

    def emit(self, word, text):
        if self.pc + 4 > self.imem_bytes or not 0 <= word <= 0xffffffff:
            raise ValueError("instruction/IMEM bounds")
        self.listing.append(f"{self.pc:08x}: {word:08x}  {text}")
        self.words.append(word)

    def li(self, rd, value):
        gpr(rd)
        if not -(1 << 31) <= value <= 0xffffffff:
            raise ValueError("LI requires a 32-bit value")
        upper, lower = p2.li(rd, value)
        self.emit(upper, f"LUI r{rd},0x{upper >> 12:05x} ; LI 0x{value & p1.MASK:08x}")
        low = p1.signed(value & 4095, 12)
        self.emit(lower, f"ADDI r{rd},r{rd},{low}")

    def seti(self, address, value):
        if address not in CSR.values() or not -4096 <= value <= 4095:
            raise ValueError("invalid CSR/SETI immediate")
        self.emit(p2.seti(address,value), f"SETI 0x{address:03x},{value}")

    def setaddr(self, address, value):
        if address not in CSR.values():
            raise ValueError("invalid writable CSR")
        self.li(4,value)
        self.emit(p2.csrw(address,4), f"CSRW 0x{address:03x},r4 ; SETADDR clobbers r4")

    def addi(self, rd, rs, value):
        gpr(rd,rs)
        if not -2048 <= value <= 2047:
            raise ValueError("ADDI immediate")
        self.emit(p1.addi(rd,rs,value), f"ADDI r{rd},r{rs},{value}")

    def transfer(self, src, dst, length, store=False):
        gpr(src,dst,length)
        self.emit(p3.transfer(src,dst,length,store),
                  f"{'STORE' if store else 'LOAD'} r{src},r{dst},r{length}")

    def sw(self, value, base, immediate=0):
        gpr(value,base)
        if not -2048 <= immediate <= 2047:
            raise ValueError("SW immediate")
        self.emit(p4.sw(value,base,immediate),f"SW r{value},{immediate}(r{base})")

    def label(self, name):
        if name in self.labels:
            raise ValueError("duplicate label")
        self.labels[name] = self.pc

    def bne(self, a, b, label):
        gpr(a,b)
        self.fixups.append((len(self.words),a,b,label))
        self.emit(0,f"BNE r{a},r{b},{label}")

    def finish(self):
        for index,a,b,name in self.fixups:
            if name not in self.labels:
                raise ValueError("undefined branch label")
            offset = self.labels[name] - index * 4
            if offset % 4 or not -4096 <= offset <= 4094:
                raise ValueError("branch target/alignment/range")
            self.words[index] = p1.branch(a,b,offset,ne=True)
            self.listing[index] = f"{index*4:08x}: {self.words[index]:08x}  BNE r{a},r{b},{name} ; {offset}"
        return self.words

def build_program(layout, debug_layers=False):
    r = layout.regions
    a = Assembler()
    loads = []
    for name,dst in [(f"weight{i}",0x80040000+i*0x20000) for i in range(4)]+[("bias",0x800C0000)]:
        src, size = r[name].start, r[name].size
        loads.append(dict(src=src,dst=dst,length=size))
        a.li(1,src); a.li(2,dst); a.li(3,size); a.transfer(1,2,3)
    # r1/r3/r6/r7 are live throughout LOOP. r4 alone is SETADDR scratch.
    for reg,value in [(1,r["input"].start),(3,784),(6,r["prediction"].start),(7,r["input"].end)]:
        a.li(reg,value)
    a.seti(CSR["M"],1)
    a.setaddr(CSR["ARG_SRC"],0x80020000)
    a.seti(CSR["ARG_LEN"],10)
    a.label("LOOP")
    a.li(2,0x80000000)
    a.transfer(1,2,3)
    layer_cursor = r["layers"].start if debug_layers else 0
    for cfg in LAYERS:
        for i,value in enumerate(cfg):
            if i == 4:
                continue
            if i < 4:
                a.setaddr(0x7c0+i,value)
            else:
                a.seti(0x7c0+i,value)
        a.emit(p5.GEMM,"EXEC GEMM")
        if debug_layers:
            # Only dead scratch r2/r4/r5; preserve all four loop-live registers.
            words = (cfg[5]+3)//4
            a.li(2,cfg[2]); a.li(4,layer_cursor); a.li(5,words*4)
            a.transfer(2,4,5,store=True)
            layer_cursor += words*4
    a.emit(p6.argmax(5),"EXEC ARGMAX,r5")
    a.sw(5,6)
    a.addi(1,1,784); a.addi(6,6,4)
    a.bne(1,7,"LOOP")
    a.emit(p1.END,"END")
    a.finish()
    return a, loads
