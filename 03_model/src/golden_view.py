"""Small, read-only views of saved RTL golden data for the inspection notebook."""
from pathlib import Path
import hashlib
import json

import numpy as np


def _word(values):
    return sum((int(value) & 0xFF) << (8 * lane) for lane, value in enumerate(values))


def _hex(value, bits=32):
    return f"{int(value) & ((1 << bits) - 1):0{bits // 4}X}"


def _values(values):
    return "[" + ", ".join(str(int(value)) for value in values) + "]"


def _window(start, count, size):
    if not isinstance(start, int) or not isinstance(count, int):
        raise ValueError("start와 count는 정수로 지정하세요.")
    if not 1 <= count <= 8 or not 0 <= start < start + count <= size:
        raise ValueError(f"count는 1..8, start는 0..{size - count} 범위로 지정하세요.")
    return range(start, start + count)


class GoldenRun:
    """Read an explicitly selected run; never generate data or execute RTL."""

    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        path = self.directory / "golden.npz"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != self.manifest["files_sha256"]["golden.npz"]:
            raise ValueError("golden.npz의 SHA-256이 manifest와 다릅니다.")
        with np.load(path, allow_pickle=False) as saved:
            self.data = {key: saved[key].copy() for key in saved.files}
        self.layers = {layer["layer"]: layer for layer in self.manifest["layers"]}
        self._hex_cache = {}

    def hex_words(self, relative):
        if relative not in self._hex_cache:
            path = self.directory / relative
            expected = self.manifest["files_sha256"][relative]
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"{relative}의 SHA-256이 manifest와 다릅니다.")
            self._hex_cache[relative] = np.array(
                [int(line, 16) for line in path.read_text(encoding="ascii").splitlines()],
                dtype=np.uint32,
            )
        return self._hex_cache[relative]

    def check_hex(self, relative, address, expected):
        actual = int(self.hex_words(relative)[address])
        if actual != (int(expected) & 0xFFFFFFFF):
            raise AssertionError(f"{relative}[{address}]: HEX와 NPZ/계산값이 다릅니다.")
        return _hex(actual)

    def summary(self):
        m = self.manifest
        print(f"run = {self.directory.name}")
        print(f"sample={m['sample_id']} | label={m['label']} | FP32={m['fp32_prediction']} | INT8={m['prediction']}")
        print("golden.npz SHA-256: PASS | 표시하는 HEX 파일도 처음 읽을 때 해시 확인")

    def pixels(self, row=7, col=0, count=8):
        if not isinstance(row, int) or not 0 <= row < 28:
            raise ValueError("row는 0..27 범위로 지정하세요.")
        columns = list(_window(col, count, 28))
        indices = row * 28 + np.array(columns)
        print(f"pixel[{row}, {col}:{col + count}] = {_values(self.data['pixels_uint8'][row, columns])}")
        print(f"normalized = {np.array2string(self.data['input_fp32'][indices], precision=5, max_line_width=160)}")
        print(f"input8 (F{self.layers['fc1']['input_frac']}) = {_values(self.data['input8'][indices])}")

    def select(self, layer="fc1", neuron=29, word_start=50, word_count=2):
        return GoldenSelection(self, layer, neuron, word_start, word_count)

    def argmax(self):
        logits = self.data["fc3_output8"]
        prediction = int(np.argmax(logits[:10]))
        if prediction != self.manifest["prediction"]:
            raise AssertionError("signed ARGMAX와 manifest prediction이 다릅니다.")
        if np.any(logits[10:] != 0):
            raise AssertionError("FC3 dummy 출력이 0이 아닙니다.")
        self.check_hex("expected/prediction.hex", 0, prediction)
        print(f"class 0..9 signed code = {_values(logits[:10])}")
        print(f"dummy 10..11 = {_values(logits[10:])} (비교 제외)")
        print(f"ARGMAX = {prediction} | label = {self.manifest['label']} | 동률은 가장 작은 index")

    def memory(self, name="buffer_a", start=0, count=2, final=False):
        valid = self.manifest["memory"]
        if name not in valid or (final and name not in ("buffer_a", "buffer_b")):
            raise ValueError("name은 buffer_a/b, weight_bank0..3, bias; final은 buffer에만 사용하세요.")
        relative = f"expected/{name}_final.hex" if final else valid[name]["file"]
        words = self.hex_words(relative)
        indices = _window(start, count, len(words))
        base = int(valid[name]["tb_base_byte"], 16)
        print(f"{relative} | {'FC3 종료 후' if final else 'TB 초기화 데이터'}")
        for index in indices:
            word = int(words[index])
            lanes = [(word >> (8 * lane)) & 0xFF for lane in range(4)]
            lanes = [value if value < 128 else value - 256 for value in lanes]
            print(f"word[{index}] | TB byte=0x{base + 4 * index:05X} | HEX={_hex(word)} | signed lanes={_values(lanes)}")


class GoldenSelection:
    def __init__(self, run, layer, neuron, word_start, word_count):
        if layer not in run.layers:
            raise ValueError("layer는 fc1, fc2, fc3 중 하나로 지정하세요.")
        self.run, self.name, self.info = run, layer, run.layers[layer]
        if not isinstance(neuron, int) or not 0 <= neuron < self.info["padded_outputs"]:
            raise ValueError(f"neuron은 0..{self.info['padded_outputs'] - 1} 범위로 지정하세요.")
        self.words = list(_window(word_start, word_count, self.info["input_words"]))
        self.neuron, self.tile, self.lane = neuron, neuron // 4, neuron % 4
        self.x = run.data[f"{layer}_input8"].astype(np.int64)
        self.w = run.data[f"{layer}_weight8"][neuron].astype(np.int64)
        self.bias8 = int(run.data[f"{layer}_bias8"][neuron])
        self.bias32 = int(run.data[f"{layer}_bias32"][neuron])
        self.psum = run.data[f"{layer}_psum32"][self.tile, :, self.lane]
        self.acc = run.data[f"{layer}_acc32"][self.tile, :, self.lane]
        self.output = int(run.data[f"{layer}_output8"][neuron])

    def summary(self):
        m = self.info
        dummy = " (dummy: ARGMAX에서 제외)" if self.neuron >= m["outputs"] else ""
        print(f"{self.name} neuron={self.neuron} → tile={self.tile}, output lane/bank={self.lane}{dummy}")
        print(f"input word={self.words[0]}..{self.words[-1]} | input index={4 * self.words[0]}..{4 * self.words[-1] + 3}")
        print(f"F: input={m['input_frac']}, weight={m['weight_frac']}, bias={m['bias_frac']}, acc={m['acc_frac']}, output={m['output_frac']}")
        print(f"bias_shift={m['bias_shift']} | output_shift={m['output_shift']} | ReLU={m['relu']}")

    def inputs(self):
        for k in self.words:
            x = self.x[4 * k:4 * k + 4]
            print(f"word[{k}] input[{4*k}:{4*k+4}] = {_values(x)} | packed HEX={_hex(_word(x))}")

    def weights(self):
        for k in self.words:
            w = self.w[4 * k:4 * k + 4]
            address = self.info["weight_base_word"] + self.tile * self.info["input_words"] + k
            word = self.run.check_hex(f"memory/weight_bank{self.lane}.hex", address, _word(w))
            print(f"bank{self.lane}[{address}] weight[{self.neuron},{4*k}:{4*k+4}] = {_values(w)} | HEX={word}")

    def products(self):
        for k in self.words:
            products = self.x[4*k:4*k+4] * self.w[4*k:4*k+4]
            print(f"word[{k}] input × weight = {_values(products)}")

    def adder_tree(self):
        for k in self.words:
            products = self.x[4*k:4*k+4] * self.w[4*k:4*k+4]
            a, b = int(products[0] + products[1]), int(products[2] + products[3])
            if a + b != int(self.psum[k]):
                raise AssertionError("4개 곱의 합과 저장된 psum이 다릅니다.")
            print(f"word[{k}] pair01={a}, pair23={b} → psum={a+b} | HEX={_hex(a+b)} | NPZ 일치")

    def bias(self):
        shift = self.info["bias_shift"]
        aligned = self.bias8 << shift if shift >= 0 else self.bias8 >> -shift
        if aligned != self.bias32 or self.bias32 != int(self.acc[0]):
            raise AssertionError("bias 정렬 또는 누산기 초기값이 다릅니다.")
        address = self.info["bias_base_word"] + self.tile
        values = self.run.data[f"{self.name}_bias8"][4*self.tile:4*self.tile+4]
        packed = self.run.check_hex("memory/bias.hex", address, _word(values))
        print(f"bias word[{address}] HEX={packed} | 선택 lane={self.lane}")
        print(f"bias8={self.bias8} (HEX={_hex(self.bias8, 8)}) → 부호 확장 후 shift {shift} → bias32={self.bias32} (HEX={_hex(self.bias32)})")
        print(f"acc[prefix=0]={int(self.acc[0])} | NPZ 일치")

    def accumulation(self):
        for k in self.words:
            before, partial, after = int(self.acc[k]), int(self.psum[k]), int(self.acc[k+1])
            if before + partial != after:
                raise AssertionError("누산 결과와 저장된 acc32가 다릅니다.")
            print(f"word[{k}] acc[{k}] {before} + psum {partial} = acc[{k+1}] {after} | HEX={_hex(after)} | NPZ 일치")

    def final_sum(self):
        calculated = self.bias32 + int(np.dot(self.x, self.w))
        if calculated != int(self.acc[-1]):
            raise AssertionError("전체 입력을 누산한 값이 저장된 최종 acc와 다릅니다.")
        print(f"전체 {self.info['inputs']}개 입력: bias32 + Σ(input × weight) = {calculated}")
        print(f"acc[prefix={self.info['input_words']}]={int(self.acc[-1])} | HEX={_hex(calculated)} | NPZ 일치")

    def postprocess(self):
        value = int(self.acc[-1])
        activated = max(value, 0) if self.info["relu"] else value
        shifted = activated >> self.info["output_shift"]
        clipped = min(127, max(-128, shifted))
        if clipped != self.output:
            raise AssertionError("후처리 계산과 저장된 output8이 다릅니다.")
        print(f"acc32={value} → ReLU({self.info['relu']})={activated} → >>{self.info['output_shift']}={shifted}")
        print(f"signed int8 포화={clipped} | HEX={_hex(clipped, 8)} | NPZ output8={self.output} 일치")
        print(f"복원한 값 = {clipped} / 2^{self.info['output_frac']} = {clipped / 2**self.info['output_frac']:g}")

    def store(self):
        values = self.run.data[f"{self.name}_output8"][4*self.tile:4*self.tile+4]
        packed = self.run.check_hex(f"expected/{self.name}_output.hex", self.tile, _word(values))
        print(f"output neurons[{4*self.tile}:{4*self.tile+4}] = {_values(values)}")
        print(f"buffer {self.info['output_buffer']} word[{self.tile}] ← HEX={packed} | lane0=[7:0], lane3=[31:24]")
        print(f"expected/{self.name}_output.hex: line index={self.tile} (편집기 줄 번호={self.tile+1})")

    def addresses(self):
        m = self.info
        print("모듈 word address (TB 초기화용 byte address와 구분):")
        for k in self.words:
            address = m['weight_base_word'] + self.tile * m['input_words'] + k
            print(f"input {m['input_buffer']}[{k}] | weight bank{self.lane}[{address}]")
        print(f"bias[{m['bias_base_word'] + self.tile}] | output {m['output_buffer']}[{self.tile}]")

    def expected_hex(self):
        n = self.info["input_words"]
        for k in self.words:
            psum_index = (self.tile * n + k) * 4 + self.lane
            acc_index = (self.tile * (n + 1) + k + 1) * 4 + self.lane
            p = self.run.check_hex(f"expected/{self.name}_psum32.hex", psum_index, self.psum[k])
            a = self.run.check_hex(f"expected/{self.name}_acc32.hex", acc_index, self.acc[k+1])
            print(f"word[{k}] {self.name}_psum32.hex[{psum_index}]={p} | {self.name}_acc32.hex[{acc_index}]={a}")
