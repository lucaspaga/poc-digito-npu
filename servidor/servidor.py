"""
Servidor que faz o papel do hospedeiro da placa: recebe traços do celular,
manda o dígito para a NPU e devolve o resultado.

Dois modos, com os MESMOS pesos int8:
  - emulação (padrão): a conta da NPU é feita aqui, em inteiros;
  - placa (--placa PORTA): a imagem vai pela UART para a FPGA com o firmware
    cnn_server.c, e a resposta é a da NPU de verdade.

    python servidor.py                                # emulação, porta 5000
    python servidor.py --placa /dev/ttyUSB1           # FPGA de verdade (firmware já gravado)
    python servidor.py --placa /dev/ttyUSB1 --gravar  # grava o firmware cnn_server antes
    python servidor.py --atraso 1500                  # +1,5 s em cada inferência
    python servidor.py --atraso-max 1500              # +até 1,5 s aleatório por inferência
    python servidor.py --falha 0.3                    # 30% das inferências respondem 503

O celular precisa usar o IP do computador (mostrado ao iniciar), nunca localhost.
"""

from __future__ import annotations

import argparse
import math
import random
import socket
import sys
import time

import numpy as np
from flask import Flask, jsonify, request

from npu_emulada import BAUD, CLASSES, ModeloNPU, PlacaNaoRespondeu, PlacaNPU
from preprocessamento import to_npu_input

app = Flask(__name__)
MODELO = ModeloNPU()
CONFIG = {"atraso_ms": 0, "atraso_max_ms": 0, "falha": 0.0}
PLACA: PlacaNPU | None = None          # preenchida com --placa
DIVERGENCIAS = {"total": 0, "diferentes": 0}


@app.after_request
def cors(resposta):
    # O Expo Go não precisa disso; o Expo Web (navegador) precisa.
    resposta.headers["Access-Control-Allow-Origin"] = "*"
    resposta.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resposta


# --- Rotas -----------------------------------------------------------------

def erro(mensagem: str, codigo: int):
    return jsonify(erro=mensagem), codigo


@app.get("/status")
def status():
    return jsonify(ok=True, origem="placa" if PLACA else "emulacao",
                   porta=PLACA.porta if PLACA else None,
                   atraso_ms=CONFIG["atraso_ms"], atraso_max_ms=CONFIG["atraso_max_ms"],
                   falha=CONFIG["falha"],
                   divergencias=DIVERGENCIAS if PLACA else None)


@app.post("/inferir/digito")
def inferir_digito():
    corpo = request.get_json(silent=True) or {}
    revisao = corpo.get("revisao")
    if isinstance(revisao, bool) or not isinstance(revisao, int):
        return erro("'revisao' precisa ser um inteiro", 400)
    tracos = corpo.get("tracos")
    if not isinstance(tracos, list) or not tracos:
        return erro("'tracos' precisa ser uma lista não vazia", 400)
    try:
        tracos_inteiros = []
        for traco in tracos:
            if not isinstance(traco, list) or not traco:
                return erro("cada traço precisa ser uma lista não vazia", 400)
            pontos = []
            for ponto in traco:
                if not isinstance(ponto, (list, tuple)) or len(ponto) != 2:
                    return erro("cada ponto precisa ter coordenadas x e y", 400)
                if not all(math.isfinite(float(coordenada)) for coordenada in ponto):
                    return erro("as coordenadas precisam ser números finitos", 400)
                pontos.append([int(ponto[0]), int(ponto[1])])
            tracos_inteiros.append(pontos)
    except (TypeError, ValueError, OverflowError):
        return erro("as coordenadas precisam ser números", 400)

    x_q = to_npu_input(tracos_inteiros)
    if x_q is None:
        return erro("os traços estão vazios", 400)
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
        atraso_base = CONFIG["atraso_ms"]
    else:
        r = MODELO.resultado(emulados)
        atraso_base = r.tempo_placa_ms + CONFIG["atraso_ms"]

    time.sleep((atraso_base + random.uniform(0, CONFIG["atraso_max_ms"])) / 1000)

    if random.random() < CONFIG["falha"]:
        return erro("a placa não respondeu dentro do prazo", 503)

    return jsonify(
        revisao=revisao,
        classe=r.classe,
        confianca=r.probabilidades[r.classe],
        probabilidades=r.probabilidades,
        logits=r.logits,
        ciclos=r.ciclos,
        tempo_npu_us=round(r.tempo_npu_us, 2),
        tempo_serial_ms=round(r.tempo_serial_ms, 2),
        tempo_placa_ms=round(r.tempo_placa_ms, 2),
        origem="placa" if PLACA else "emulacao",
        **extra,
    )


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
    ap.add_argument("--atraso", type=int, default=0, help="ms extras por inferência")
    ap.add_argument("--atraso-max", type=int, default=0,
                    help="ms de atraso aleatório adicional por inferência")
    ap.add_argument("--falha", type=float, default=0.0, help="probabilidade de 503 (0 a 1)")
    args = ap.parse_args()
    CONFIG.update(atraso_ms=args.atraso, atraso_max_ms=args.atraso_max, falha=args.falha)

    if args.placa:
        PLACA = PlacaNPU(args.placa, args.baud)
        print(f"  Placa em {args.placa} @ {args.baud} bps.")
        if args.gravar:
            PLACA.gravar_firmware(None if args.gravar == "padrao" else args.gravar)
        print("  Enviando os pesos da rede de dígitos...")
        PLACA.carregar_modelo(MODELO)
        print("  Pesos carregados na NPU. Os LEDs e o display mostram o dígito previsto.")
    elif args.gravar:
        sys.exit("--gravar só faz sentido com --placa")

    print(f"\n  Modo: {'PLACA (' + args.placa + ')' if PLACA else 'emulação'}")
    print(f"  No celular, use: http://{ip_da_rede()}:{args.porta}")
    print(f"  Neste computador: http://localhost:{args.porta}\n")
    app.run(host="0.0.0.0", port=args.porta, threaded=True)
