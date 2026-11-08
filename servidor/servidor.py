"""
Servidor que faz o papel do hospedeiro da placa: entrega peças do conjunto de
teste do Fashion-MNIST, recebe a imagem do celular, manda para a NPU e devolve
o resultado.

Dois modos, com os MESMOS pesos int8:
  - emulação (padrão): a conta da NPU é feita aqui, em inteiros;
  - placa (--placa PORTA): a imagem vai pela UART para a FPGA com o firmware
    cnn_server.c, e a resposta é a da NPU de verdade.

    python servidor.py                                # emulação, porta 5000
    python servidor.py --placa /dev/ttyUSB1           # FPGA de verdade (firmware já gravado)
    python servidor.py --placa /dev/ttyUSB1 --gravar  # grava o firmware cnn_server antes
    python servidor.py --placa /dev/ttyUSB1 --verificar 200
                                                      # antes de servir, compara placa e
                                                      # emulação em 200 imagens de teste
    python servidor.py --atraso 1500                  # +1,5 s em cada inferência
    python servidor.py --falha 0.3                    # 30% das inferências respondem 503

O celular precisa usar o IP do computador (mostrado ao iniciar), nunca localhost.
"""

from __future__ import annotations

import argparse
import base64
import random
import socket
import struct
import sys
import time
import zlib

import numpy as np
from flask import Flask, jsonify, request

from npu_emulada import (BAUD, CLASSES, PASTA_MODELOS, ModeloNPU, PlacaNaoRespondeu,
                         PlacaNPU, preparar_entrada)

app = Flask(__name__)
MODELO = ModeloNPU()
AMOSTRAS = np.load(PASTA_MODELOS / "fashion_amostras.npz")
CONFIG = {"atraso_ms": 0, "falha": 0.0}
PLACA: PlacaNPU | None = None          # preenchida com --placa
DIVERGENCIAS = {"total": 0, "diferentes": 0}


@app.after_request
def cors(resposta):
    # O Expo Go não precisa disso; o Expo Web (navegador) precisa.
    resposta.headers["Access-Control-Allow-Origin"] = "*"
    resposta.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resposta


# --- Imagens em PNG, sem bibliotecas externas ------------------------------

def _png(img: np.ndarray, tipo_cor: int) -> bytes:
    """Monta um PNG a partir de uma matriz (altura, largura) em tons de cinza
    (tipo_cor 0) ou (altura, largura, 3) em RGB (tipo_cor 2)."""
    altura, largura = img.shape[:2]
    bruto = b"".join(b"\x00" + linha.tobytes() for linha in img)

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return (struct.pack(">I", len(dados)) + tipo + dados
                + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + bloco(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, tipo_cor, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(bruto, 9))
            + bloco(b"IEND", b""))


def _data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def png_data_uri(pixels: np.ndarray, ampliacao: int = 4) -> str:
    """Imagem 28x28 em tons de cinza -> PNG 112x112, ampliada pixel a pixel."""
    img = np.kron(pixels.reshape(28, 28).astype(np.uint8),
                  np.ones((ampliacao, ampliacao), np.uint8))
    return _data_uri(_png(img, tipo_cor=0))


FUNDO_GRADE = np.array([0x0B, 0x12, 0x20], np.float64)   # #0B1220, entre os quadradinhos
PIXEL_APAGADO = np.array([0x1A, 0x26, 0x40], np.float64)  # #1A2640
PIXEL_ACESO = np.array([0x7D, 0xD3, 0xFC], np.float64)    # #7DD3FC


def png_estilizado(pixels: np.ndarray, celula: int = 8, vao: int = 1) -> str:
    """Mesma imagem no estilo da apresentação: cada pixel vira um quadradinho
    azul (mais claro = mais intenso) sobre uma grade escura. 224x224 px."""
    v = pixels.reshape(28, 28).astype(np.float64)[..., None] / 255
    cores = PIXEL_APAGADO + (PIXEL_ACESO - PIXEL_APAGADO) * v
    lado = 28 * celula
    img = np.empty((lado, lado, 3), np.float64)
    img[:] = FUNDO_GRADE
    for y in range(28):
        for x in range(28):
            y0, x0 = y * celula + vao, x * celula + vao
            img[y0:y0 + celula - vao, x0:x0 + celula - vao] = cores[y, x]
    return _data_uri(_png(np.round(img).astype(np.uint8), tipo_cor=2))


# --- Rotas -----------------------------------------------------------------

def erro(mensagem: str, codigo: int):
    return jsonify(erro=mensagem), codigo


@app.get("/status")
def status():
    return jsonify(ok=True, origem="placa" if PLACA else "emulacao",
                   porta=PLACA.porta if PLACA else None,
                   atraso_ms=CONFIG["atraso_ms"], falha=CONFIG["falha"],
                   divergencias=DIVERGENCIAS if PLACA else None)


@app.get("/amostra/fashion")
def amostra():
    i = random.randrange(len(AMOSTRAS["rotulos"]))
    classe = int(AMOSTRAS["rotulos"][i])
    img = AMOSTRAS["imagens"][i]
    return jsonify(id=i, pixels=img.reshape(-1).tolist(), imagem_png=png_data_uri(img),
                   imagem_estilo=png_estilizado(img),
                   classe_real=classe, rotulo_real=CLASSES[classe])


@app.post("/inferir/fashion")
def inferir():
    corpo = request.get_json(silent=True) or {}
    pixels = corpo.get("pixels")
    if not isinstance(pixels, list) or len(pixels) != 784:
        return erro("envie 'pixels' com exatamente 784 inteiros de 0 a 255", 400)
    try:
        arr = np.asarray(pixels, dtype=np.int64)
    except (TypeError, ValueError):
        return erro("os pixels precisam ser números inteiros", 400)
    if arr.min() < 0 or arr.max() > 255:
        return erro("os pixels precisam estar entre 0 e 255", 400)
    if arr.max() == 0:
        return erro("a imagem está vazia", 400)

    x_q = preparar_entrada(arr.astype(np.uint8))[0]
    emulados = MODELO.logits_emulados(x_q[None])[0]
    extra = {}

    if PLACA:
        try:
            logits, ms = PLACA.logits(x_q)
        except PlacaNaoRespondeu as e:
            return erro(str(e), 503)
        r = MODELO.resultado(logits, tempo_medido_ms=ms)
        classe_emulada = int(np.argmax(emulados))
        DIVERGENCIAS["total"] += 1
        DIVERGENCIAS["diferentes"] += int(classe_emulada != r.classe)
        extra = {"classe_emulacao": classe_emulada,
                 "logits_emulacao": [int(v) for v in emulados]}
        time.sleep(CONFIG["atraso_ms"] / 1000)
    else:
        r = MODELO.resultado(emulados)
        # espera o tempo que a placa levaria (UART + NPU)
        time.sleep((r.tempo_placa_ms + CONFIG["atraso_ms"]) / 1000)

    if random.random() < CONFIG["falha"]:
        return erro("a placa não respondeu dentro do prazo", 503)

    return jsonify(
        classe=r.classe,
        rotulo=CLASSES[r.classe],
        confianca=r.probabilidades[r.classe],
        probabilidades=r.probabilidades,
        rotulos=CLASSES,
        logits=r.logits,
        ciclos=r.ciclos,
        tempo_npu_us=round(r.tempo_npu_us, 2),
        tempo_serial_ms=round(r.tempo_serial_ms, 2),
        tempo_placa_ms=round(r.tempo_placa_ms, 2),
        origem="placa" if PLACA else "emulacao",
        **extra,
    )


# --- Verificação placa x emulação ------------------------------------------

def verificar(n: int):
    """Manda n imagens de teste à placa e compara com a emulação e com o rótulo."""
    imagens, rotulos = AMOSTRAS["imagens"][:n], AMOSTRAS["rotulos"][:n]
    x_q = preparar_entrada(imagens)
    emulados = MODELO.logits_emulados(x_q)
    acertos_placa = acertos_emul = iguais_classe = iguais_logits = 0
    tempos = []
    for i in range(len(x_q)):
        logits, ms = PLACA.logits(x_q[i])
        tempos.append(ms)
        acertos_placa += int(np.argmax(logits) == rotulos[i])
        acertos_emul += int(np.argmax(emulados[i]) == rotulos[i])
        iguais_classe += int(np.argmax(logits) == np.argmax(emulados[i]))
        iguais_logits += int(np.array_equal(logits, emulados[i]))
        if i < 3:
            print(f"    imagem {i}: placa {logits.tolist()}  emulação {emulados[i].tolist()}")
    n = len(x_q)
    print(f"\n  Verificação em {n} imagens de teste do Fashion-MNIST:")
    print(f"    acurácia na placa      : {acertos_placa / n:.1%}")
    print(f"    acurácia na emulação   : {acertos_emul / n:.1%}")
    print(f"    mesma classe           : {iguais_classe}/{n}")
    print(f"    logits idênticos       : {iguais_logits}/{n}")
    print(f"    tempo médio por imagem : {np.mean(tempos):.2f} ms (ida e volta pela UART)\n")


def ip_da_rede() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=5000, help="porta HTTP do servidor")
    ap.add_argument("--placa", metavar="SERIAL", help="usa a FPGA nesta porta serial, "
                                                      "por exemplo /dev/ttyUSB1 ou COM4")
    ap.add_argument("--baud", type=int, default=BAUD)
    ap.add_argument("--gravar", nargs="?", const="padrao", metavar="ARQUIVO.bin",
                    help="com --placa: grava o firmware na FPGA antes de tudo "
                         "(padrão: firmware/cnn_server.bin)")
    ap.add_argument("--verificar", type=int, metavar="N", default=0,
                    help="com --placa: compara placa e emulação em N imagens antes de servir")
    ap.add_argument("--atraso", type=int, default=0, help="ms extras por inferência")
    ap.add_argument("--falha", type=float, default=0.0, help="probabilidade de 503 (0 a 1)")
    args = ap.parse_args()
    CONFIG.update(atraso_ms=args.atraso, falha=args.falha)

    if args.placa:
        PLACA = PlacaNPU(args.placa, args.baud)
        print(f"  Placa em {args.placa} @ {args.baud} bps.")
        if args.gravar:
            PLACA.gravar_firmware(None if args.gravar == "padrao" else args.gravar)
        print("  Enviando os pesos do Fashion-MNIST...")
        PLACA.carregar_modelo(MODELO)
        print("  Pesos carregados na NPU. Os LEDs e o display mostram o número da classe "
              "prevista (0 = Camiseta ... 9 = Bota).")
        if args.verificar:
            verificar(args.verificar)
    elif args.verificar or args.gravar:
        sys.exit("--verificar e --gravar só fazem sentido com --placa")

    print(f"\n  Modo: {'PLACA (' + args.placa + ')' if PLACA else 'emulação'}")
    print(f"  No celular, use: http://{ip_da_rede()}:{args.porta}")
    print(f"  Neste computador: http://localhost:{args.porta}\n")
    app.run(host="0.0.0.0", port=args.porta, threaded=True)
