"""Application contracts: checked allocation/encoding, loop liveness and numeric rules."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import assembler as a
import memory_allocator as m
import golden_compare as g
from weight_packer import pack8

def signed(v,bits):
    return (v & ((1<<bits)-1))-(1<<bits) if v & (1<<(bits-1)) else v & ((1<<bits)-1)

def execute_program(count,debug=False):
    """Independent decode/control reference; EXEC results stubbed, no RTL timing model."""
    layout=m.application_layout(count,debug)
    asm,descriptors=a.build_program(layout,debug)
    regs=[0]*8;csr={};pc=0;loads=[];stores=[];pred=[];gemms=0;args=0;steps=0
    while steps<20000:
        w=asm.words[pc//4];op=w&127;rd=(w>>7)&31;rs1=(w>>15)&31;rs2=(w>>20)&31
        nxt=pc+4;steps+=1
        if op==0x37:regs[rd]=w&0xfffff000
        elif op==0x13:regs[rd]=(regs[rs1]+signed(w>>20,12))&0xffffffff
        elif op==0x0b:csr[(w>>7)&4095]=signed(w>>19,13)&0xffffffff
        elif op==0x73:csr[w>>20]=regs[rs1]
        elif op==0x63:
            off=((w>>31)<<12)|(((w>>7)&1)<<11)|(((w>>25)&63)<<5)|(((w>>8)&15)<<1)
            if regs[rs1]!=regs[rs2]:nxt=pc+signed(off,13)
        elif op==0x23:
            imm=signed(((w>>25)<<5)|((w>>7)&31),12)
            pred.append(((regs[rs1]+imm)&0xffffffff,regs[rs2]))
        elif w==0x0400302b:break
        elif w==0x0000202b:
            cfg=tuple(signed(csr[0x7c0+i],32) if i==7 else csr[0x7c0+i] for i in range(10))
            if cfg!=a.LAYERS[gemms%3]:raise AssertionError("CSR configuration")
            gemms+=1
        elif w==0x020022ab:
            if csr[0x7e0]!=0x80020000 or csr[0x7e1]!=10:raise AssertionError("ARG config")
            regs[5]=args%10;args+=1
        elif op==0x2b and ((w>>12)&7) in (0,1):
            item=(regs[rs1],regs[rs2],regs[rd])
            (stores if ((w>>12)&7)==1 else loads).append(item)
        else:raise AssertionError(f"unsupported generated word {w:08x}")
        regs[0]=0;pc=nxt
    else:raise AssertionError("loop did not terminate")
    r=layout.regions
    expected=[(d["src"],d["dst"],d["length"]) for d in descriptors]
    expected += [(r["input"].start+784*i,0x80000000,784) for i in range(count)]
    if loads!=expected:raise AssertionError("LOAD operands/liveness")
    if pred!=[(r["prediction"].start+4*i,i%10) for i in range(count)]:raise AssertionError("SW/ARG result")
    if regs[1]!=r["input"].end or regs[6]!=r["prediction"].end:raise AssertionError("end pointers")
    if gemms!=3*count or args!=count:raise AssertionError("engine counts")
    if len(stores)!=(3 if debug else 0):raise AssertionError("debug STORE count")
    if debug:
        for cfg,store,size in zip(a.LAYERS,stores,(512,128,12)):
            if store[0]!=cfg[2] or store[2]!=size:raise AssertionError("debug STORE operands")
    return asm,steps

class AllocationTests(unittest.TestCase):
    def test_first_100_and_200(self):
        self.assertEqual(m.application_layout(100).cursor-m.BASE,547932)
        self.assertEqual(m.application_layout(200).cursor-m.BASE,626732)
        for count in (1,5,100,200):
            x=m.application_layout(count);x.validate()
            self.assertTrue(all(r.start%4==0 and r.size%4==0 for r in x.regions.values()))

    def test_reject_invalid_allocations(self):
        x=m.Allocator(capacity=8);x.allocate("a",4)
        for name,size in (("a",4),("b",0),("b",3),("b",8)):
            with self.subTest(name=name,size=size),self.assertRaises(ValueError):x.allocate(name,size)
        with self.assertRaises(ValueError):m.application_layout(201)
        with self.assertRaises(ValueError):m.application_layout(5,True)

class ProgramTests(unittest.TestCase):
    def test_loop_all_gates_and_gpr_liveness(self):
        for count in (1,5,100,200):
            with self.subTest(count=count):
                asm,steps=execute_program(count)
                self.assertEqual(len(asm.words),111)
                self.assertEqual(steps,49+62*count)
                self.assertEqual(asm.labels["LOOP"],0xc0)

    def test_debug_store_preserves_loop_registers(self):
        asm,steps=execute_program(1,True)
        self.assertEqual(len(asm.words),132)
        self.assertEqual(steps,132)

    def test_checked_immediates_registers_and_labels(self):
        for f,args in ((a.Assembler().li,(8,0)),(a.Assembler().li,(1,1<<32)),
                       (a.Assembler().seti,(0x7c4,4096)),(a.Assembler().seti,(0x123,1)),
                       (a.Assembler().addi,(1,1,2048)),(a.Assembler().sw,(8,1,0))):
            with self.subTest(args=args),self.assertRaises(ValueError):f(*args)
        asm=a.Assembler();asm.bne(1,2,"absent")
        with self.assertRaises(ValueError):asm.finish()
        asm=a.Assembler();asm.label("far")
        for _ in range(1100):asm.addi(0,0,0)
        asm.bne(1,2,"far")
        with self.assertRaises(ValueError):asm.finish()
        asm=a.Assembler(imem_bytes=4);asm.addi(0,0,0)
        with self.assertRaises(ValueError):asm.addi(0,0,0)

    def test_known_encodings_and_li_carry(self):
        self.assertEqual(a.p3.transfer(1,2,3),0x002081ab)
        self.assertEqual(a.p6.argmax(5),0x020022ab)
        self.assertEqual(a.p4.sw(2,1,-4),0xfe20ae23)
        for value in (0x7ff,0x800,0x1001c980,0x80000000,0xffffffff):
            asm=a.Assembler();asm.li(4,value)
            result=((asm.words[0]&0xfffff000)+signed(asm.words[1]>>20,12))&0xffffffff
            self.assertEqual(result,value)

class NumericTests(unittest.TestCase):
    def test_wrap_and_signed_packing(self):
        self.assertEqual(g.wrap32([0x7fffffff+1,-0x80000000-1,0xffffffff]).tolist(),
                         [-0x80000000,0x7fffffff,-1])
        self.assertEqual(pack8([-128,-1,0,127]).tolist(),[0x7f00ff80])

    def test_arithmetic_shift_and_lowest_index(self):
        # First two layers produce 1; FC3 codes [-1,-1,0,...], so first maximum is class 2.
        w=[np.array([[0]],dtype=np.int8),np.array([[0]],dtype=np.int8),np.zeros((10,1),dtype=np.int8)]
        b=[np.array([127],dtype=np.int8),np.array([127],dtype=np.int8),np.array([-1,-1]+[0]*8,dtype=np.int8)]
        pred,layers=g.infer(np.array([[0]],dtype=np.int8),w,b)
        self.assertEqual(layers[2][0,:3].tolist(),[-1,-1,0])
        self.assertEqual(pred.tolist(),[2])
        b[-1][:]=0
        self.assertEqual(g.infer(np.array([[0]],dtype=np.int8),w,b)[0].tolist(),[0])

    def test_golden_match_separate_from_accuracy(self):
        r=g.compare([1,2],[1,3],[1,2])
        self.assertEqual(r["golden_mismatches"],1)
        self.assertEqual(r["correct"],2)
        self.assertEqual(r["accuracy_percent"],100.0)
        self.assertEqual(r["mismatch_indices"],[1])
        for pred,golden,labels in (([0xffffffff],[0],[0]),([0],[0,1],[0])):
            with self.assertRaises(ValueError):g.compare(pred,golden,labels)

if __name__=="__main__":
    unittest.main()
