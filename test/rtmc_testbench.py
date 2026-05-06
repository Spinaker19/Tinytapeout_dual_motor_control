import cocotb
import ctypes
import logging

from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer, RisingEdge, FallingEdge
from cocotbext.spi import SpiMaster, SpiConfig
from cocotb_bus.bus import Bus 

import rtmc_common as rtmc_com

class ErrorHandler(logging.NullHandler):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.errors = 0
        
    def handle(self, record: logging.LogRecord):
        self.errors += int(record.levelno >= logging.ERROR)

class Testbench:
    def __init__(self, dut, name="tb", spi_mult=4, spi_frame_spacing=None):
        self.dut = dut
        self.pos_edge = RisingEdge(dut.clk)
        self.neg_edge = FallingEdge(dut.clk)
        
        self.log = logging.getLogger(f"cocotb.{name}")
        self.errorHandler = ErrorHandler()
        self.log.addHandler(self.errorHandler)

        spi_clk_period_ns = rtmc_com.SYS_CLK_PERIOD_NS * spi_mult
        spi_clk_freq_hz = 1e9 / spi_clk_period_ns

        # SPI config 0.5.0
        self.spi_config = SpiConfig(
            word_width = 8,
            sclk_freq = spi_clk_freq_hz,
            cpol = False,
            cpha = False,
            msb_first = True
        )

        # Identification de l'entité SPI
        if hasattr(self.dut, "spi"):
            spi_entity = self.dut.spi
        elif hasattr(self.dut, "dut") and hasattr(self.dut.dut, "spi"):
            spi_entity = self.dut.dut.spi
        else:
            spi_entity = self.dut

        # Mapping Bus pour version 0.5.0
        signals = {
            "sclk": "sclk",
            "mosi": "mosi",
            "miso": "miso",
            "cs":   "cs"
        }
        self.spi_bus = Bus(spi_entity, None, signals)
        self.spi = SpiMaster(self.spi_bus, self.spi_config)

        # Clock setup
        clock = Clock(dut.clk, rtmc_com.SYS_CLK_PERIOD_NS, units="ns")
        cocotb.start_soon(clock.start())

        self.regfile = {}

    async def reset(self):
        # Initialisation sécurisée des signaux
        try:
            self.dut.gpio.gpi.value = 0
            self.dut.motor.mc.value = 0
            self.dut.motor.mc_oe.value = 0
        except AttributeError:
            pass

        await Timer(rtmc_com.SYS_CLK_PERIOD_NS // 2, "ns")
        self.dut.ena.value = 1
        self.dut.rst_n.value = 0
        await ClockCycles(self.dut.clk, 10)
        self.dut.rst_n.value = 1
        await ClockCycles(self.dut.clk, 10)

    # --- Accès SPI de base ---

    async def write(self, addr, val: int, timeout=64) -> None:
        if isinstance(addr, str):
            addr = rtmc_com.REG_MAP[addr]

        txDat = int(rtmc_com.Op.WR).to_bytes(1, byteorder="big")
        txDat += (addr & rtmc_com.ADDR_MASK).to_bytes(rtmc_com.ADDR_W // 8, byteorder="big")
        txDat += (val & rtmc_com.DATA_MASK).to_bytes(rtmc_com.DATA_W // 8, byteorder="big")
        txDat += int(rtmc_com.Op.NOP).to_bytes(1, byteorder="big")
        
        await self.spi.write(txDat)
        rxDat = await self.spi.read(len(txDat))

        result = rtmc_com.Result(rxDat[-1])
        while result == rtmc_com.Result.BUSY and timeout:
            await self.spi.write(int(rtmc_com.Op.NOP).to_bytes(1, byteorder="big"))
            rxDat = await self.spi.read(1)
            result = rtmc_com.Result(int.from_bytes(rxDat, byteorder="big"))
            timeout -= 1

        if not timeout and result == rtmc_com.Result.BUSY:
            raise RuntimeError("SPI write timeout!")
        if result != rtmc_com.Result.ACK:
            raise RuntimeError(f"SPI write bad result: {result}!")
        
        self.regfile[addr] = val

    async def read(self, addr, timeout=64) -> int:
        if isinstance(addr, str):
            addr = rtmc_com.REG_MAP[addr]

        txDat = int(rtmc_com.Op.RD).to_bytes(1, byteorder="big")
        txDat += (addr & rtmc_com.ADDR_MASK).to_bytes(rtmc_com.ADDR_W // 8, byteorder="big")
        await self.spi.write(txDat)
        rxDat = await self.spi.read(len(txDat))

        result = rtmc_com.Result(rxDat[-1])
        while result == rtmc_com.Result.BUSY and timeout:
            await self.spi.write(int(rtmc_com.Op.NOP).to_bytes(1, byteorder="big"))
            rxDat = await self.spi.read(1)
            result = rtmc_com.Result(int.from_bytes(rxDat, byteorder="big"))
            timeout -= 1

        if result != rtmc_com.Result.ACK_DATA:
            raise RuntimeError(f"SPI read bad result: {result}!")

        txDat = bytes([int(rtmc_com.Op.NOP)] * (rtmc_com.DATA_W // 8))
        await self.spi.write(txDat)
        rxDat = await self.spi.read(len(txDat))
        return int.from_bytes(rxDat, byteorder="big")

    # --- Manipulation des registres et champs ---

    async def write_reg(self, name: str, field: str | None, val: int) -> None:
        bit_offset, _, bit_mask = rtmc_com.get_field_info(name, field)
        reg_val = await self.read(name)
        reg_val &= rtmc_com.DATA_MASK ^ (bit_mask << bit_offset)
        reg_val |= (val & bit_mask) << bit_offset

        addr = rtmc_com.REG_MAP[name]
        await self.write(addr, reg_val)
        if addr < 0x20:
            await self.write(addr | 0x20, reg_val)
        self.regfile[addr] = reg_val

    async def read_reg(self, name: str, field: str | None) -> int:
        bit_offset, _, bit_mask = rtmc_com.get_field_info(name, field)
        val = await self.read(name)
        return (val >> bit_offset) & bit_mask

    # --- Gestion des compteurs 32 bits ---

    async def write_counter(self, name: str, val: int) -> None:
        cnt0 = val >> rtmc_com.DATA_W
        cnt1 = val & rtmc_com.DATA_MASK
        addr0 = rtmc_com.REG_MAP[name + "0"]
        addr1 = rtmc_com.REG_MAP[name + "1"]
        await self.write(addr0, cnt0)
        await self.write(addr1, cnt1)
        if addr0 < 0x20:
            await self.write(addr0 | 0x20, cnt0)
            await self.write(addr1 | 0x20, cnt1)

    async def read_counter(self, name: str, signed=False) -> int:
        counter = await self.read(name + "0")
        counter <<= rtmc_com.DATA_W
        counter += await self.read(name + "1")
        if signed:
            return ctypes.c_int32(counter).value
        return counter

    # --- Step Table ---

    async def write_step_table(self, step_table: list[int]) -> None:
        if len(step_table) > rtmc_com.TABLE_DEPTH:
            raise RuntimeError("Step table depth exceeded.")
        low_addr = rtmc_com.STEP_TABLE_OFFSET
        high_addr = rtmc_com.STEP_TABLE_OFFSET | 0x20
        for i, val in enumerate(step_table):
            low_val = val & ((1 << rtmc_com.MC_OUT_WIDTH) - 1)
            high_val = val >> rtmc_com.MC_OUT_WIDTH
            await self.write(low_addr + i, low_val)
            await self.write(high_addr + i, high_val)

    # --- Utilitaires de simulation ---

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(value)
        except ValueError:
            text = str(value).replace("x", "0").replace("X", "0").replace("z", "0").replace("Z", "0")
            return int(text, 2)

    def get_mc_out(self) -> int:
        mc_oe = self._safe_int(self.dut.motor.mc_oe.value)
        mc = self._safe_int(self.dut.motor.mc.value)
        return mc & mc_oe

    async def step(self, n=1, pos_edge=True) -> None:
        edge = self.pos_edge if pos_edge else self.neg_edge
        for _ in range(n):
            await edge

    def set_gpi(self, val: int) -> None:
        """Définit la valeur de l'entrée GPI."""
        self.dut.gpio.gpi.value = val

    def get_gpo(self) -> int:
        """Lit la valeur de la sortie GPO."""
        return int(self.dut.gpio.gpo.value)
    
    @staticmethod
    def set_packed_bit(signal, bit_idx: int, bit_val: int) -> None:
        val = int(signal.value)
        val |= (bit_val & 0x1) << bit_idx
        signal.value = val

    @staticmethod
    def get_packed_bit(signal, idx: int) -> int:
        return (int(signal.value) >> idx) & 0x1

    async def finish(self):
        await self.step(100)
        if self.errorHandler.errors:
            raise RuntimeError(f"Test failed, error count = {self.errorHandler.errors}.")

async def make_tb(dut, **kwargs):
    tb = Testbench(dut, **kwargs)
    await tb.reset()
    return tb