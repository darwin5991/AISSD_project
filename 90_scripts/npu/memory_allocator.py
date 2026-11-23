"""Application-only byte-address allocator; no NPU address-map changes."""
from dataclasses import asdict, dataclass

BASE = 0x10000000
DMEM_BYTES = 16 * 1024 * 1024

@dataclass(frozen=True)
class Region:
    name: str
    start: int
    size: int

    @property
    def end(self):
        return self.start + self.size

    def manifest(self):
        return dict(asdict(self), end=self.end, words=self.size // 4,
                    start_hex=f"0x{self.start:08X}", end_exclusive_hex=f"0x{self.end:08X}")

class Allocator:
    def __init__(self, base=BASE, capacity=DMEM_BYTES):
        if base % 4 or capacity <= 0 or capacity % 4 or base + capacity > 0x100000000:
            raise ValueError("invalid aligned memory capacity")
        self.base, self.capacity = base, capacity
        self.cursor = base
        self.regions = {}

    def allocate(self, name, size):
        if name in self.regions or size <= 0 or size % 4:
            raise ValueError("duplicate region or invalid aligned size")
        start = (self.cursor + 3) & ~3
        region = Region(name, start, size)
        if region.end > self.base + self.capacity:
            raise ValueError("DMEM bounds exceeded")
        self.regions[name] = region
        self.cursor = region.end
        self.validate()
        return region

    def validate(self):
        end = self.base
        for r in sorted(self.regions.values(), key=lambda r: r.start):
            if r.start % 4 or r.size % 4 or r.start < end or r.end > self.base + self.capacity:
                raise ValueError("unaligned, overlapping or out-of-bounds allocation")
            end = r.end

    def manifest(self):
        self.validate()
        return dict(base=self.base, capacity=self.capacity, used_bytes=self.cursor-self.base,
                    regions=[r.manifest() for r in self.regions.values()])

def application_layout(count, debug_layers=False):
    if not 1 <= count <= 200 or (debug_layers and count != 1):
        raise ValueError("Phase 7 supports first 1..200 images; layer STORE only for one image")
    a = Allocator()
    for bank in range(4):
        a.allocate(f"weight{bank}", 29280 * 4)
    a.allocate("bias", 163 * 4)
    a.allocate("input", count * 784)
    a.allocate("prediction", count * 4)
    if debug_layers:
        a.allocate("layers", (128 + 32 + 3) * 4)
    return a
