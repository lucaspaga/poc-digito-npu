"""Pré-processamento dos traços desenhados para a entrada 28x28 da NPU."""

import cv2
import numpy as np

STROKE_RATIO = 0.12  # espessura do traço relativa ao tamanho do dígito


def to_npu_input(strokes):
    """Converte traços em um vetor int8 de 784 posições, com valores 0..127."""
    points = [p for stroke in strokes for p in stroke]
    if not points:
        return None
    pts = np.array(points)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    size = max(x1 - x0, y1 - y0, 1)
    thick = max(2, int(round(STROKE_RATIO * size)))

    canvas = np.zeros((y1 - y0 + 1 + 2 * thick, x1 - x0 + 1 + 2 * thick), np.uint8)
    for stroke in strokes:
        shifted = np.array([(x - x0 + thick, y - y0 + thick) for x, y in stroke], np.int32)
        if len(shifted) == 1:
            cv2.circle(canvas, tuple(int(v) for v in shifted[0]), thick // 2, 255, -1, cv2.LINE_AA)
        else:
            cv2.polylines(canvas, [shifted], False, 255, thick, cv2.LINE_AA)

    ys, xs = np.nonzero(canvas)
    crop = canvas[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    ratio = 20.0 / max(h, w)
    nw, nh = max(1, int(w * ratio)), max(1, int(h * ratio))
    small = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA)

    img28 = np.zeros((28, 28), np.uint8)
    oy, ox = (28 - nh) // 2, (28 - nw) // 2
    img28[oy:oy + nh, ox:ox + nw] = small
    return np.clip(img28 // 2, 0, 127).astype(np.int8).reshape(-1)