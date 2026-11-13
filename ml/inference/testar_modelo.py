#!/usr/bin/env python3
"""PavimentAI - testa o modelo de buracos em fotos ou vídeos reais.

Exemplos:
    python testar_modelo.py rua_maua.mp4
    python testar_modelo.py fotos/            # pasta com imagens
    python testar_modelo.py rua.mp4 --conf 0.4 --salvar-frames 15

Saídas (pasta "resultados/<nome>/"):
    - video_anotado.mp4 ou imagens_anotadas/  : caixas desenhadas
    - deteccoes.csv                           : uma linha por frame/imagem
    - resumo.txt                              : números gerais do teste
    - frames_deteccao/                        : frames com detecção (opcional)
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

EXT_IMG = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
EXT_VID = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


def _descobrir_modelo_padrao() -> str:
    """Procura automaticamente o modelo nos caminhos conhecidos do repositório."""
    pasta_atual = Path(__file__).resolve().parent
    raiz_ml = pasta_atual.parent
    candidatos = [
        pasta_atual / "weights" / "best.pt",
        raiz_ml / "models" / "yolo11n" / "best.pt",
        raiz_ml / "oitavotreino - joao" / "weights" / "best.pt",
        raiz_ml / "oitavotreino - joao" / "weights" / "best.onnx",
        pasta_atual / "weights" / "best.onnx",
    ]
    for c in candidatos:
        if c.is_file():
            return str(c)
    return str(candidatos[0])


def parse_args():
    ap = argparse.ArgumentParser(description="Testa o modelo de buracos em fotos ou vídeos.")
    ap.add_argument("fonte", help="vídeo, imagem ou pasta com imagens")
    ap.add_argument(
        "--modelo",
        default=_descobrir_modelo_padrao(),
        help="caminho do modelo .pt ou .onnx (descoberto automaticamente por padrão)",
    )
    ap.add_argument("--conf", type=float, default=0.25, help="confiança mínima (padrão 0.25)")
    ap.add_argument("--imgsz", type=int, default=640, help="tamanho de entrada (padrão 640)")
    ap.add_argument("--saida", default="resultados", help="pasta de saída")
    ap.add_argument(
        "--salvar-frames",
        type=int,
        default=0,
        metavar="N",
        help="em vídeo, salva 1 a cada N frames que tiveram detecção, para revisão (0 = não salva)",
    )
    return ap.parse_args()


def resumo_texto(linhas: list[str]) -> str:
    return "\n".join(linhas) + "\n"


def processar_video(model, fonte: Path, pasta: Path, args) -> list[str]:
    import cv2

    cap = cv2.VideoCapture(str(fonte))
    if not cap.isOpened():
        sys.exit(f"Não consegui abrir o vídeo: {fonte}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    writer = cv2.VideoWriter(
        str(pasta / "video_anotado.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h)
    )
    pasta_frames = pasta / "frames_deteccao"
    if args.salvar_frames > 0:
        pasta_frames.mkdir(exist_ok=True)

    # Warm-up do modelo para não distorcer a média de ms/frame com a alocação do 1º frame
    dummy = np.zeros((args.imgsz, args.imgsz, 3), dtype=np.uint8)
    model.predict(dummy, imgsz=args.imgsz, verbose=False)

    ids_vistos = set()
    frames = frames_com_det = total_det = 0
    soma_conf = 0.0
    tempo_modelo = 0.0
    salvos = 0

    with open(pasta / "deteccoes.csv", "w", newline="", encoding="utf-8") as f:
        csv_w = csv.writer(f)
        csv_w.writerow(["frame", "tempo_s", "n_deteccoes", "conf_maxima", "ids_tracker"])
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t0 = time.perf_counter()
            r = model.track(
                frame,
                persist=True,
                conf=args.conf,
                imgsz=args.imgsz,
                tracker="bytetrack.yaml",
                verbose=False,
            )[0]
            tempo_modelo += time.perf_counter() - t0

            n = len(r.boxes)
            confs = r.boxes.conf.tolist() if n else []
            ids = r.boxes.id.int().tolist() if (n and r.boxes.id is not None) else []
            ids_vistos.update(ids)

            frames += 1
            total_det += n
            soma_conf += sum(confs)
            if n:
                frames_com_det += 1
            csv_w.writerow(
                [
                    frames - 1,
                    round((frames - 1) / fps, 2),
                    n,
                    round(max(confs), 3) if confs else "",
                    " ".join(map(str, ids)),
                ]
            )

            anotado = r.plot()
            writer.write(anotado)
            # Salva já no 1º frame com detecção e depois a cada N frames com detecção
            if args.salvar_frames > 0 and n and ((frames_com_det - 1) % args.salvar_frames == 0):
                cv2.imwrite(str(pasta_frames / f"frame_{frames - 1:06d}.jpg"), anotado)
                salvos += 1

            if frames % 50 == 0:
                msg = f"  {frames}/{total} frames" if total else f"  {frames} frames"
                print(msg, flush=True)

    cap.release()
    writer.release()

    dur = frames / fps if fps else 0
    linhas = [
        f"Vídeo: {fonte.name}",
        f"Modelo: {args.modelo} | conf={args.conf} | imgsz={args.imgsz}",
        f"Duração: {dur:.1f} s ({frames} frames a {fps:.1f} fps)",
        f"Frames com detecção: {frames_com_det} ({100 * frames_com_det / max(frames, 1):.1f}%)",
        f"Detecções somadas (todas as caixas): {total_det}",
        f"Buracos distintos segundo o tracker (aproximação): {len(ids_vistos)}",
        f"Confiança média das detecções: {soma_conf / max(total_det, 1):.2f}",
        f"Tempo médio do modelo neste computador: {1000 * tempo_modelo / max(frames, 1):.1f} ms/frame",
        "ATENÇÃO: o tracker pode contar o mesmo buraco duas vezes (perde e reencontra). "
        "Para o resultado oficial, confira o vídeo anotado e conte à mão (veja o README).",
    ]
    if args.salvar_frames > 0:
        linhas.append(f"Frames salvos para revisão: {salvos}")
    return linhas


def processar_imagens(model, fonte: Path, pasta: Path, args) -> list[str]:
    import cv2

    if fonte.is_dir():
        imagens = sorted(p for p in fonte.rglob("*") if p.suffix.lower() in EXT_IMG)
    else:
        imagens = [fonte]
    if not imagens:
        sys.exit("Nenhuma imagem encontrada.")

    pasta_img = pasta / "imagens_anotadas"
    pasta_img.mkdir(exist_ok=True)

    # Warm-up
    dummy = np.zeros((args.imgsz, args.imgsz, 3), dtype=np.uint8)
    model.predict(dummy, imgsz=args.imgsz, verbose=False)

    com_det = total_det = 0
    soma_conf = 0.0
    tempo_modelo = 0.0

    with open(pasta / "deteccoes.csv", "w", newline="", encoding="utf-8") as f:
        csv_w = csv.writer(f)
        csv_w.writerow(["imagem", "n_deteccoes", "conf_maxima"])
        for idx, p in enumerate(imagens):
            t0 = time.perf_counter()
            r = model.predict(str(p), conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
            tempo_modelo += time.perf_counter() - t0

            n = len(r.boxes)
            confs = r.boxes.conf.tolist() if n else []
            total_det += n
            soma_conf += sum(confs)
            if n:
                com_det += 1

            # Evita colisão de nomes quando há subpastas dentro de fonte
            if fonte.is_dir():
                rel = p.relative_to(fonte)
                nome_saida = "_".join(rel.parts)
            else:
                nome_saida = p.name

            csv_w.writerow([nome_saida, n, round(max(confs), 3) if confs else ""])
            cv2.imwrite(str(pasta_img / nome_saida), r.plot())

    return [
        f"Imagens: {len(imagens)} (origem: {fonte})",
        f"Modelo: {args.modelo} | conf={args.conf} | imgsz={args.imgsz}",
        f"Imagens com detecção: {com_det} ({100 * com_det / len(imagens):.1f}%)",
        f"Detecções somadas: {total_det}",
        f"Confiança média das detecções: {soma_conf / max(total_det, 1):.2f}",
        f"Tempo médio do modelo neste computador: {1000 * tempo_modelo / len(imagens):.1f} ms/imagem",
        "Confira as imagens anotadas e conte acertos e falsos alarmes à mão.",
    ]


def main():
    args = parse_args()
    fonte = Path(args.fonte)
    if not fonte.exists():
        sys.exit(f"Não encontrei: {fonte}")
    if not Path(args.modelo).exists():
        sys.exit(f"Não encontrei o modelo: {args.modelo}")

    try:
        from ultralytics import YOLO
    except ImportError:
        sys.exit("Instale as dependências primeiro: pip install -r requirements.txt")

    model = YOLO(args.modelo)
    pasta = Path(args.saida) / fonte.stem
    pasta.mkdir(parents=True, exist_ok=True)

    if fonte.is_file() and fonte.suffix.lower() in EXT_VID:
        linhas = processar_video(model, fonte, pasta, args)
    elif fonte.is_dir() or fonte.suffix.lower() in EXT_IMG:
        linhas = processar_imagens(model, fonte, pasta, args)
    else:
        sys.exit("Formato não reconhecido. Use vídeo (mp4, mov, avi, mkv), imagem ou pasta.")

    texto = resumo_texto(linhas)
    (pasta / "resumo.txt").write_text(texto, encoding="utf-8")
    print("\n" + texto)
    print(f"Resultados salvos em: {pasta.resolve()}")


if __name__ == "__main__":
    main()