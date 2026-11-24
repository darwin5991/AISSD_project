"""Generation-time GEMM contract, including failures no longer checked in RTL."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gemm_config import validate_gemm_config
import assembler

class GemmConfigTests(unittest.TestCase):
    def setUp(self):
        self.cfg=[0x80000000,0x80040000,0x80020000,0x800c0000,1,10,8,0,0,0]
    def test_application_layers(self):
        for cfg in assembler.LAYERS:validate_gemm_config(cfg)
    def test_supported_short_k(self):
        for k in (8,12,16,32):
            self.cfg[6]=k;validate_gemm_config(self.cfg)
    def test_k4_rejected(self):
        self.cfg[6]=4
        with self.assertRaises(ValueError):validate_gemm_config(self.cfg)
    def test_raw_k_not_truncated(self):
        self.cfg[6]=0x80000008
        with self.assertRaises(ValueError):validate_gemm_config(self.cfg)
    def test_same_buffer_rejected(self):
        self.cfg[2]=0x80000020
        with self.assertRaises(ValueError):validate_gemm_config(self.cfg)
    def test_address_alignment_and_role(self):
        for index,value in ((0,0x80000001),(1,0x80060000),(3,0x80000000)):
            cfg=self.cfg.copy();cfg[index]=value
            with self.assertRaises(ValueError):validate_gemm_config(cfg)
    def test_physical_end_rejected(self):
        for index,value in ((0,0x8000030c),(1,0x8005c97c),(2,0x800201fc),(3,0x800c0288)):
            cfg=self.cfg.copy();cfg[index]=value
            with self.assertRaises(ValueError):validate_gemm_config(cfg)
    def test_high_output_offset_valid(self):
        self.cfg[0]=0x80020000;self.cfg[2]=0x80000304
        validate_gemm_config(self.cfg)
    def test_shift_raw_bits(self):
        for value in (-32,0xffffffe0,31):
            self.cfg[7]=value;validate_gemm_config(self.cfg)
        self.cfg[7]=0x10000001
        with self.assertRaises(ValueError):validate_gemm_config(self.cfg)
    def test_assembler_rejects_before_emit(self):
        original=assembler.LAYERS
        try:
            cfg=self.cfg.copy();cfg[6]=4;assembler.LAYERS=(tuple(cfg),)
            with self.assertRaises(ValueError):assembler.build_program(None)
        finally:assembler.LAYERS=original
if __name__=="__main__":unittest.main()
