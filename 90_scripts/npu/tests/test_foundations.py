import unittest,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from assembler import assemble
from memory_builder import pack8,unpack8,build
from scenario import Scenario
from model_loader import load,ROOT
from reference import generate,gemm
from assembly_generator import generate as assembly

class Foundations(unittest.TestCase):
    def test_independent_vectors(self):
        vectors={'LW x5,4(x1)':0x0040a283,'SW x2,-4(x1)':0xfe20ae23,'LOAD x1,x2,x3':0x002081ab,'STORE x1,x2,x3':0x002091ab,
                 'EXEC GEMM':0x202b,'EXEC ARGMAX,x5':0x020022ab,'TSTART':0x302b,'TSTOP':0x0200302b,'END':0x0400302b,
                 'SETI GEMM_DIM,1':0xbe20b,'AND x3,x1,x2':0x0020f1b3,'OR x3,x1,x2':0x0020e1b3,'ANDI x3,x1,-1':0xfff0f193,
                 'ORI x3,x1,1':0x0010e193,'SLLI x3,x1,4':0x00409193,'SRLI x3,x1,4':0x0040d193,
                 'LUI x1,0x12345':0x123450b7,'ADD x3,x1,x2':0x002081b3,'ADDI x1,x0,-1':0xfff00093,
                 'CSRW SRC0_BASE,x1':0x7c009073,'CSRR x2,STATUS':0x7f202173}
        for src,expected in vectors.items(): self.assertEqual(assemble(src),[expected],src)
        self.assertEqual(assemble('a: BEQ x0,x0,a\nBNE x1,x2,a\nJAL x3,a'),[0x63,0xfe209ee3,0xff9ff1ef])
    def test_pseudos(self):
        for n in (-2**31,-4097,-2049,-2048,0,2047,2048,4095,0x7fffffff,0xffffffff):
            words=assemble(f'LI x1,{n}')
            result=0
            for w in words:
                if w&127==0x37: result=w&0xfffff000
                else:
                    imm=w>>20; imm=imm-4096 if imm&2048 else imm
                    result=(result+imm)&0xffffffff
            self.assertEqual(result,n&0xffffffff)
        self.assertEqual(assemble('LI x1,2048\nl: ADDI x1,x1,-1\nBNE x1,x0,l\nEND')[3],0xfe009ee3)
    def test_pack_wrap(self):
        x=np.array([-128,-1,0,127],dtype=np.int8)
        self.assertEqual(int(pack8(x)[0]),0x7f00ff80)
        np.testing.assert_array_equal(unpack8(pack8(x)),x)
        np.testing.assert_array_equal(gemm([[127]*8],[[127]*8],[127],31,0,False),[[-128]])
    def test_model_reference_layout(self):
        s=Scenario('foundation',[0,1,7],['fc1','fc2','fc3','argmax']).validate()
        data,h=load(s); ref=generate(s,data); words,m=build(s,data); src=assembly(s,m)
        self.assertEqual(m['record_stride'],656); self.assertEqual(m['ops']['fc3']['weight_word'],29184)
        self.assertLess(len(assemble(src)),16384); self.assertEqual(src.count('LOAD x1,x2,x3'),6)
        sys.path.insert(0,str(ROOT/'03_model'))
        from generate_golden import generate_golden
        # Independent existing per-product/prefix golden, no DUT involved.
        for row,idx in enumerate(s.sample_ids):
            import uuid
            target=ROOT/'99_build'/('baseline_golden_'+uuid.uuid4().hex[:10])
            generate_golden(idx,target)
            with np.load(target/'golden.npz',allow_pickle=False) as g:
                for key in ('fc1','fc2','fc3'): np.testing.assert_array_equal(ref[key][row],g[key+'_output8'])
        print('baseline equality: IDs 0,1,7, all layers (1956 bytes), argmax',ref['argmax'].tolist())
        # Prepare capacity/loop support only; no large accuracy simulation/reference.
        large=Scenario('capacity_10000',list(range(10000)),['argmax']).validate()
        inputs=dict(data,input=np.zeros((10000,784),dtype=np.int8),labels=np.zeros(10000,dtype=np.int32))
        bulk,layout=build(large,inputs)
        self.assertLess(bulk.nbytes,16*1024**2)
        self.assertLess(len(assemble(assembly(large,layout))),128)
        self.assertEqual(layout['dump']['words'],10000)
        print('10000 capacity only:',bulk.nbytes,'bytes; no 1000/10000 inference run')

if __name__=='__main__': unittest.main()
