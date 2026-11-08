"""
A NPU do lado do hospedeiro: a emulação em inteiros e o driver da placa real.

As duas usam os MESMOS pesos int8, no formato que o firmware cnn_server.c
espera (o mesmo esquema do cnn_client.py do TCC):

    entrada   x = pixel                            (0..127, int8)
    conv      acc = x * w_conv + b_conv  (int32)  ->  y = clip((acc + 128) >> 8, 0, 127)   (ReLU)
    densa     acc = y * w_fc  + b_fc     (int32)  ->  logit = clip((acc + 128) >> 8, -128, 127)

A emulação reproduz essa conta, incluindo o arredondamento da PPU.
"""

from __future__ import annotations

import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PASTA_MODELOS = Path(__file__).parent / "modelos"

# --- Parâmetros da plataforma (dos artigos do TCC) -------------------------
FREQ_HZ = 100_000_000          # SoC a 100 MHz
BAUD = 921_600                 # UART a 921.600 bit/s
BITS_POR_BYTE = 10             # 8N1: start + 8 dados + stop
CICLOS_CNN_MEDIDOS = 1506      # conv 3x3/2 (4 filtros) + densa 676->10, medido na placa
SOBRECARGA_USB_MS = 0.5        # trânsito USB + firmware (artigo: ~0,5 ms)
DESLOCAMENTO = 8               # a NPU divide o acumulador por 256 na saída de cada camada

CLASSES = [str(digito) for digito in range(10)]


class PlacaNaoRespondeu(Exception):
    pass


def im2col_3x3_passo2(img: np.ndarray) -> np.ndarray:
    """(N, 28, 28) -> (N, 169, 9): as janelas 3x3 com passo 2, na ordem
    linha-coluna da saída 13x13, e cada janela na ordem dy*3 + dx."""
    n = img.shape[0]
    saida = np.empty((n, 13, 13, 9), dtype=img.dtype)
    k = 0
    for dy in range(3):
        for dx in range(3):
            saida[:, :, :, k] = img[:, dy:dy + 25:2, dx:dx + 25:2]
            k += 1
    return saida.reshape(n, 169, 9)


def preparar_entrada(pixels_u8: np.ndarray) -> np.ndarray:
    """0..255 -> 0..127, como a GUI do TCC faz antes de mandar à placa."""
    return (pixels_u8.reshape(-1, 784).astype(np.int64) // 2).clip(0, 127).astype(np.int8)


def empacotar_pesos_dma(w_int8: np.ndarray) -> np.ndarray:
    """Mesmo empacotamento do cnn_client.py: blocos de 4 neurônios; para cada
    entrada k, uma palavra com w[4j+0..3, k] nos bytes 0..3 (byte 0 = menos
    significativo). Linhas que faltam no último bloco ficam zeradas."""
    saidas, entradas = w_int8.shape
    blocos = -(-saidas // 4)
    w = np.zeros((blocos * 4, entradas), np.int64)
    w[:saidas] = w_int8.astype(np.int64) & 0xFF
    w = w.reshape(blocos, 4, entradas)
    palavras = w[:, 0] | (w[:, 1] << 8) | (w[:, 2] << 16) | (w[:, 3] << 24)   # (blocos, entradas)
    return palavras.reshape(-1).astype(np.uint32)


@dataclass
class ResultadoNPU:
    classe: int
    logits: list[int]
    probabilidades: list[float]
    ciclos: int = CICLOS_CNN_MEDIDOS
    bytes_enviados: int = 785      # comando 0xFF + 784 pixels
    bytes_recebidos: int = 10
    tempo_medido_ms: float | None = None   # só quando veio da placa

    @property
    def tempo_npu_us(self) -> float:
        return self.ciclos / FREQ_HZ * 1e6

    @property
    def tempo_serial_ms(self) -> float:
        return (self.bytes_enviados + self.bytes_recebidos) * BITS_POR_BYTE / BAUD * 1000

    @property
    def tempo_placa_ms(self) -> float:
        if self.tempo_medido_ms is not None:
            return self.tempo_medido_ms
        return self.tempo_serial_ms + SOBRECARGA_USB_MS + self.tempo_npu_us / 1000


class ModeloNPU:
    """Os pesos int8 no formato da placa e a emulação da conta da NPU."""

    def __init__(self, caminho: Path = PASTA_MODELOS / "digitos_int8.npz"):
        d = np.load(caminho)
        self.w_conv = d["w_conv"].astype(np.int8)     # (4, 9)    filtro x (dy*3+dx)
        self.b_conv = d["b_conv"].astype(np.int32)    # (4,)
        self.w_fc = d["w_fc"].astype(np.int8)         # (10, 676) entrada em channels-last
        self.b_fc = d["b_fc"].astype(np.int32)        # (10,)

    def logits_emulados(self, x_q: np.ndarray) -> np.ndarray:
        """x_q: (N, 784) int8 -> (N, 10) logits int8, com a conta da NPU."""
        x = x_q.reshape(-1, 28, 28).astype(np.int64)
        acc1 = im2col_3x3_passo2(x) @ self.w_conv.astype(np.int64).T + self.b_conv   # (N, 169, 4)
        y1 = np.clip((acc1 + (1 << (DESLOCAMENTO - 1))) >> DESLOCAMENTO, 0, 127)
        acc2 = y1.reshape(len(x), -1) @ self.w_fc.astype(np.int64).T + self.b_fc     # (N, 10)
        return np.clip((acc2 + (1 << (DESLOCAMENTO - 1))) >> DESLOCAMENTO, -128, 127).astype(np.int8)

    def resultado(self, logits: np.ndarray, tempo_medido_ms: float | None = None) -> ResultadoNPU:
        # O softmax não roda na NPU: o hospedeiro calcula só para mostrar a confiança.
        z = logits.astype(np.float64) / 15
        e = np.exp(z - z.max())
        probs = e / e.sum()
        return ResultadoNPU(classe=int(np.argmax(logits)), logits=[int(v) for v in logits],
                            probabilidades=[round(float(p), 4) for p in probs],
                            tempo_medido_ms=tempo_medido_ms)

    def inferir(self, pixels_u8: np.ndarray) -> ResultadoNPU:
        return self.resultado(self.logits_emulados(preparar_entrada(pixels_u8))[0])


class PlacaNPU:
    """Driver da FPGA com o firmware cnn_server.c, pela UART.

    Protocolo (do firmware): 0xAA + 9 palavras (pesos da conv) -> 'A';
    0xBB + 4 int32 (bias da conv) -> 'B'; 0xCC + 2028 palavras (pesos da densa)
    -> 'C'; 0xDD + 12 int32 (bias da densa) -> 'D'; 0xFF + 784 bytes (imagem)
    -> 10 bytes (logits int8). Tudo em big-endian."""

    def __init__(self, porta: str, baud: int = BAUD, timeout_s: float = 2.0):
        try:
            import serial  # pyserial: só é necessário no modo --placa
        except ImportError as e:
            raise SystemExit("O modo --placa precisa do pyserial: pip install pyserial") from e
        try:
            # mesmas opções do upload.py: sem controle de fluxo, RTS em alto
            # (com RTS em baixo, a UART vai para o debug controller, não para o SoC)
            self.ser = serial.Serial(porta, baud, rtscts=False, dsrdtr=False, timeout=timeout_s)
        except Exception as e:
            raise SystemExit(f"Não consegui abrir a porta {porta}: {e}") from e
        try:
            self.ser.rts = True
        except OSError:
            pass   # porta virtual (firmware falso) não tem RTS
        self.ser.reset_input_buffer()
        self.trava = threading.Lock()   # uma conversa com a placa por vez
        self.porta = porta

    def _comando(self, cmd: int, palavras: np.ndarray, formato: str, ack: bytes):
        self.ser.write(bytes([cmd]) + struct.pack(f">{len(palavras)}{formato}",
                                                  *[int(v) for v in palavras]))
        resposta = self.ser.read(1)
        if resposta != ack:
            raise SystemExit(f"A placa não confirmou o comando 0x{cmd:02X} "
                             f"(esperava {ack!r}, veio {resposta!r}). O bitstream com o "
                             f"firmware cnn_server está carregado na FPGA?")

    def gravar_firmware(self, caminho=None, log=print):
        """Grava o firmware cnn_server na FPGA (mesmo protocolo do upload.py)."""
        from gravador import FIRMWARE_PADRAO, FalhaNaGravacao, gravar
        with self.trava:
            try:
                gravar(self.ser, caminho or FIRMWARE_PADRAO, log)
            except FalhaNaGravacao as e:
                raise SystemExit(f"Falha ao gravar a placa: {e}") from e

    def carregar_modelo(self, m: ModeloNPU):
        with self.trava:
            self.ser.reset_input_buffer()
            self._comando(0xAA, empacotar_pesos_dma(m.w_conv), "I", b"A")
            self._comando(0xBB, m.b_conv, "i", b"B")
            self._comando(0xCC, empacotar_pesos_dma(m.w_fc), "I", b"C")
            self._comando(0xDD, np.pad(m.b_fc, (0, 12 - len(m.b_fc))), "i", b"D")

    def logits(self, x_q: np.ndarray) -> tuple[np.ndarray, float]:
        """Uma imagem (784 int8) -> (10 logits int8, tempo de ida e volta em ms)."""
        with self.trava:
            inicio = time.perf_counter()
            self.ser.write(b"\xFF" + x_q.astype(np.int8).tobytes())
            resposta = self.ser.read(10)
            ms = (time.perf_counter() - inicio) * 1000
        if len(resposta) != 10:
            self.ser.reset_input_buffer()
            raise PlacaNaoRespondeu("a placa não respondeu dentro do prazo")
        return np.frombuffer(resposta, dtype=np.int8).copy(), ms

    def fechar(self):
        self.ser.close()
