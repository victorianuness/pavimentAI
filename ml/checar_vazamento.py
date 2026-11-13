#!/usr/bin/env python3
"""PavimentAI - Audita vazamento de dados (Data Leakage) entre train, val e test.

Compara todas as imagens de validação e teste contra o conjunto de treino usando
dHash perceptual de 64 bits (incluindo versão espelhada horizontalmente),
detectando fotos duplicadas, recomprimidas, redimensionadas ou espelhadas.

Uso:
    python checar_vazamento.py caminho/para/dataset_unificado
    python checar_vazamento.py caminho/para/dataset_unificado --limiar 6
"""
import argparse
import csv
import sys
from pathlib import Path

from PIL import Image, ImageOps

EXT_IMG = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def calcular_dhash(img: Image.Image) -> int:
    """Gera assinatura visual de 64 bits comparando pixels adjacentes numa grade 9x8."""
    pequena = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS).tobytes()
    bits = 0
    for linha in range(8):
        for col in range(8):
            esq = pequena[linha * 9 + col]
            dir_ = pequena[linha * 9 + col + 1]
            bits = (bits << 1) | (1 if esq > dir_ else 0)
    return bits


def indexar_particao(pasta: Path) -> list[tuple[Path, int, int]]:
    """Retorna lista de (caminho, dhash_normal, dhash_espelhado)."""
    if not pasta.is_dir():
        return []
    arquivos = sorted(p for p in pasta.rglob("*") if p.suffix.lower() in EXT_IMG)
    indice = []
    for p in arquivos:
        try:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im)
                h_normal = calcular_dhash(im)
                h_espelhado = calcular_dhash(ImageOps.mirror(im))
                indice.append((p, h_normal, h_espelhado))
        except Exception:
            continue
    return indice


def main() -> int:
    ap = argparse.ArgumentParser(description="Verifica imagens duplicadas entre train, val e test.")
    ap.add_argument("dataset", help="Caminho para a pasta raiz do dataset (contendo train, val, test)")
    ap.add_argument(
        "--limiar",
        type=int,
        default=6,
        help="Distância de Hamming máxima em 64 bits para considerar vazamento (padrão: 6)",
    )
    ap.add_argument("--saida", default="vazamento.csv", help="Arquivo CSV de saída (padrão: vazamento.csv)")
    args = ap.parse_args()

    raiz = Path(args.dataset)
    if not raiz.is_dir():
        print(f"Pasta não encontrada: {raiz}")
        return 1

    print(f"Indexando conjunto de treino em {raiz / 'train'} ...")
    treino = indexar_particao(raiz / "train")
    if not treino:
        print("Nenhuma imagem encontrada na pasta 'train'.")
        return 1
    print(f"  -> {len(treino)} imagens de treino indexadas.")

    pares_vazados = []

    for particao in ("val", "test"):
        alvo = indexar_particao(raiz / particao)
        if not alvo:
            print(f"Partição '{particao}' vazia ou não encontrada.")
            continue

        vazadas = 0
        for p_alvo, h_alvo, _ in alvo:
            melhor_dist = 65
            melhor_treino = None
            tipo_match = "exata"

            for p_tr, h_tr, h_tr_esp in treino:
                d_norm = (h_alvo ^ h_tr).bit_count()
                d_esp = (h_alvo ^ h_tr_esp).bit_count()
                if d_norm < melhor_dist:
                    melhor_dist = d_norm
                    melhor_treino = p_tr
                    tipo_match = "normal" if d_norm > 0 else "identica"
                if d_esp < melhor_dist:
                    melhor_dist = d_esp
                    melhor_treino = p_tr
                    tipo_match = "espelhada"

                if melhor_dist == 0:
                    break

            if melhor_dist <= args.limiar and melhor_treino is not None:
                vazadas += 1
                pares_vazados.append([
                    particao,
                    p_alvo.name,
                    melhor_treino.name,
                    melhor_dist,
                    tipo_match,
                ])

        pct = 100.0 * vazadas / len(alvo)
        status = "ÓTIMO" if pct < 2.0 else ("ATENÇÃO" if pct < 8.0 else "CRÍTICO (Métricas Infladas)")
        print(f"Partição '{particao}': {vazadas}/{len(alvo)} imagens similares ao treino ({pct:.1f}%) -> {status}")

    caminho_csv = Path(args.saida)
    with open(caminho_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["particao", "imagem_avaliacao", "imagem_treino", "distancia_hamming", "tipo_similaridade"])
        w.writerows(pares_vazados)

    print(f"\nRelatório completo salvo em: {caminho_csv.resolve()} ({len(pares_vazados)} pares suspeitos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())