"""
Grava o firmware na FPGA pela UART, com o mesmo protocolo do upload.py do TCC:

  1. reset pelo debug controller: RTS em baixo, palavra mágica 0xCAFEBABE,
     boot em 0x00000000 (comando 0x09), "reset halt" (0x08), RTS de volta;
  2. espera o bootloader dizer "BOOT";
  3. 0xCAFEBABE de novo -> o bootloader responde '!';
  4. tamanho do programa (uint32, little-endian) e o programa em blocos de 64 bytes;
  5. espera o '>' de confirmação. Em seguida o firmware começa a rodar.
"""

from __future__ import annotations

import struct
import time
from pathlib import Path

MAGICA = b"\xCA\xFE\xBA\xBE"
FIRMWARE_PADRAO = Path(__file__).parent / "firmware" / "cnn_server.bin"


class FalhaNaGravacao(Exception):
    pass


def _rts(ser, valor: bool, avisar=print):
    try:
        ser.rts = valor
    except OSError:
        # Portas virtuais (como a do firmware falso) não têm RTS. Na placa real tem.
        if not getattr(ser, "_avisou_rts", False):
            avisar("  [aviso] esta porta não aceita RTS; seguindo sem o reset por hardware")
            ser._avisou_rts = True


def _esperar(ser, alvo: str, timeout_s: float, ao_ler_linha=None) -> bool:
    """Lê até aparecer `alvo` (ou estourar o tempo). Linhas inteiras que chegam
    no caminho vão para `ao_ler_linha` (mensagens do bootloader)."""
    fim = time.monotonic() + timeout_s
    buffer, linha = "", ""
    while time.monotonic() < fim:
        if ser.in_waiting:
            c = ser.read(1).decode("utf-8", errors="ignore")
            buffer = (buffer + c)[-32:]
            if alvo in buffer:
                return True
            if c in "\r\n":
                if linha.strip() and ao_ler_linha:
                    ao_ler_linha(linha.strip())
                linha = ""
            elif c != ".":
                linha += c
        else:
            time.sleep(0.002)
    return False


def resetar(ser, avisar=print):
    """Reseta o SoC pelo debug controller e o deixa pronto para o bootloader."""
    _rts(ser, False, avisar)               # arma o debugger
    time.sleep(0.05)
    ser.write(MAGICA)                      # o debugger assume o controle
    time.sleep(0.05)
    ser.write(b"\x09\x00\x00\x00\x00")     # boot em 0x00000000 (ROM, bootloader)
    time.sleep(0.01)
    ser.write(b"\x08")                     # reset halt: reseta e segura o processador
    time.sleep(0.05)
    ser.reset_input_buffer()               # limpa antes de soltar o processador
    _rts(ser, True, avisar)                # devolve a UART ao SoC e o processador roda


def gravar(ser, caminho: Path = FIRMWARE_PADRAO, log=print):
    """Grava `caminho` na placa e espera o firmware começar a rodar."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise FalhaNaGravacao(f"firmware não encontrado: {caminho}")
    programa = caminho.read_bytes()

    log(f"  Gravando {caminho.name} ({len(programa)} bytes)...")
    resetar(ser, log)
    if not _esperar(ser, "BOOT", 5.0):
        raise FalhaNaGravacao("o bootloader não respondeu 'BOOT'. A placa está ligada, "
                              "com o bitstream do SoC, e esta é a porta certa?")

    time.sleep(0.1)
    ser.reset_input_buffer()
    ser.write(MAGICA)
    ack = b""
    fim = time.monotonic() + 2.0
    while time.monotonic() < fim and not ack:
        ack = ser.read(1) if ser.in_waiting else (time.sleep(0.002) or b"")
    if ack != b"!":
        raise FalhaNaGravacao(f"o bootloader não aceitou a palavra mágica (veio {ack!r})")

    ser.write(struct.pack("<I", len(programa)))   # sem o bit 31: não grava no cartão SD
    time.sleep(0.05)
    for i in range(0, len(programa), 64):
        ser.write(programa[i:i + 64])
        ser.flush()
        time.sleep(0.002)

    if not _esperar(ser, ">", 10.0, ao_ler_linha=lambda l: log(f"  bootloader: {l}")):
        raise FalhaNaGravacao("o bootloader não confirmou a gravação ('>')")
    log("  Firmware gravado; esperando ele iniciar...")
    time.sleep(0.5)                        # o cnn_server pisca os LEDs ao iniciar
    ser.reset_input_buffer()
