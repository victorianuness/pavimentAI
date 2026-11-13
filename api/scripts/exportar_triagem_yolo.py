"""Exporta fotos validadas pelos gestores para um dataset YOLO de retreino (Active Learning).

Transforma o trabalho diário dos gestores municipais em dados reais de treinamento:
  - Ocorrências aprovadas na triagem / verificadas pelo gestor -> Imagens positivas com labels YOLO
  - Ocorrências recusadas na triagem / descartadas pelo gestor -> Imagens de background (label vazio)
    para reduzir falsos alarmes (bueiros, sombras, manchas, remendos).

Uso (dentro da pasta api, com a venv ativa):
    python scripts/exportar_triagem_yolo.py
    python scripts/exportar_triagem_yolo.py --saida ../ml/dataset_retreino_campo
"""
import argparse
import getpass
import os
import random
import shutil
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def _carregar_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for linha in env_path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip().strip("'\""))


def _converter_para_yolo_centro(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    """Converte (x1, y1, largura, altura) de deteccoes_ia para (x_centro, y_centro, largura, altura) entre 0 e 1."""
    xc = max(0.0, min(1.0, x + w / 2.0))
    yc = max(0.0, min(1.0, y + h / 2.0))
    wn = max(0.001, min(1.0, w))
    hn = max(0.001, min(1.0, h))
    return xc, yc, wn, hn


def main() -> int:
    ap = argparse.ArgumentParser(description="Exporta fotos validadas pelos gestores para formato YOLO.")
    ap.add_argument(
        "--saida",
        default=str(Path(__file__).resolve().parents[2] / "ml" / "dataset_retreino_campo"),
        help="Pasta de destino do dataset YOLO (padrão: ../ml/dataset_retreino_campo)",
    )
    ap.add_argument(
        "--proporcao-val",
        type=float,
        default=0.2,
        help="Fração enviada para validação (padrão: 0.2 = 80%% treino / 20%% val)",
    )
    ap.add_argument("--seed", type=int, default=42, help="Semente aleatória para o split")
    args = ap.parse_args()

    _carregar_env()
    raiz_api = Path(__file__).resolve().parents[1]
    uploads_dir = Path(os.getenv("UPLOADS_DIR", str(raiz_api / "uploads"))).resolve()

    conexao = dict(
        host=os.getenv("PGHOST") or os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("PGPORT") or os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("PGDATABASE") or os.getenv("DB_NAME", "pavimentai"),
        user=os.getenv("PGUSER") or os.getenv("DB_USER", "postgres"),
    )
    senha = (
        os.getenv("PGPASSWORD")
        or os.getenv("DB_PASSWORD")
        or getpass.getpass(f"Senha do usuário {conexao['user']}: ")
    )

    try:
        with psycopg.connect(**conexao, password=senha, row_factory=dict_row) as conn:
            midias = conn.execute(
                """
                SELECT m.id_midia, m.caminho_arquivo, o.id_ocorrencia,
                       o.status, o.situacao_ia, o.triagem_decisao, o.gravidade_verificada
                FROM midias m
                JOIN ocorrencia_midias om ON om.id_midia = m.id_midia
                JOIN ocorrencias o ON o.id_ocorrencia = om.id_ocorrencia
                WHERE o.tipo = 'buraco'
                  AND m.origem = 'foto_cidadao'
                  AND (
                      o.triagem_decisao IN ('aprovada', 'recusada')
                      OR o.gravidade_verificada IS NOT NULL
                      OR o.status IN ('resolvida', 'descartada')
                  )
                ORDER BY m.id_midia
                """
            ).fetchall()

            caixas_por_midia: dict[int, list[dict]] = {}
            if midias:
                ids_midia = [m["id_midia"] for m in midias]
                deteccoes = conn.execute(
                    """
                    SELECT id_midia, bbox_x, bbox_y, bbox_largura, bbox_altura, confianca
                    FROM deteccoes_ia
                    WHERE id_midia = ANY(%s)
                    ORDER BY id_deteccao
                    """,
                    (ids_midia,),
                ).fetchall()
                for d in deteccoes:
                    caixas_por_midia.setdefault(d["id_midia"], []).append(d)
    except psycopg.Error as erro:
        print(f"Erro ao consultar o banco: {erro}")
        return 1

    if not midias:
        print("Nenhuma foto de buraco validada por gestor foi encontrada no banco ainda.")
        return 0

    amostras = []
    ignoradas_sem_arquivo = 0
    for m in midias:
        caminho_img = (uploads_dir / m["caminho_arquivo"]).resolve()
        if not caminho_img.is_file():
            ignoradas_sem_arquivo += 1
            continue

        eh_negativa = (m["triagem_decisao"] == "recusada") or (m["status"] == "descartada")
        caixas = [] if eh_negativa else caixas_por_midia.get(m["id_midia"], [])
        if not eh_negativa and not caixas:
            # Positiva aprovada mas sem bbox salva: pula para não gerar falso negativo
            continue

        amostras.append({
            "id_midia": m["id_midia"],
            "id_ocorrencia": m["id_ocorrencia"],
            "caminho_img": caminho_img,
            "eh_negativa": eh_negativa,
            "caixas": caixas,
        })

    if not amostras:
        print("Nenhuma amostra com arquivo físico disponível em uploads/ para exportar.")
        return 0

    random.seed(args.seed)
    random.shuffle(amostras)
    n_val = max(1, int(len(amostras) * args.proporcao_val)) if len(amostras) > 4 else 0
    particoes = {"val": amostras[:n_val], "train": amostras[n_val:]}

    pasta_saida = Path(args.saida).resolve()
    for split in ("train", "val"):
        (pasta_saida / split / "images").mkdir(parents=True, exist_ok=True)
        (pasta_saida / split / "labels").mkdir(parents=True, exist_ok=True)

    positivas = negativas = 0
    for split, itens in particoes.items():
        for item in itens:
            nome_base = f"occ{item['id_ocorrencia']}_midia{item['id_midia']}"
            destino_img = pasta_saida / split / "images" / f"{nome_base}.jpg"
            destino_lbl = pasta_saida / split / "labels" / f"{nome_base}.txt"

            shutil.copy2(item["caminho_img"], destino_img)
            linhas_txt = []
            for c in item["caixas"]:
                xc, yc, wn, hn = _converter_para_yolo_centro(
                    c["bbox_x"], c["bbox_y"], c["bbox_largura"], c["bbox_altura"]
                )
                linhas_txt.append(f"0 {xc:.6f} {yc:.6f} {wn:.6f} {hn:.6f}")

            destino_lbl.write_text("\n".join(linhas_txt) + ("\n" if linhas_txt else ""), encoding="utf-8")
            if item["eh_negativa"]:
                negativas += 1
            else:
                positivas += 1

    data_yaml = (
        f"path: {pasta_saida.as_posix()}\n"
        "train: train/images\n"
        "val: val/images\n\n"
        "nc: 1\n"
        "names: ['buraco']\n"
    )
    (pasta_saida / "data.yaml").write_text(data_yaml, encoding="utf-8")

    print(f"Exportação concluída em: {pasta_saida}")
    print(f"  - Total exportado: {len(amostras)} fotos ({positivas} positivas com buraco, {negativas} backgrounds recusados)")
    print(f"  - Divisão: {len(particoes['train'])} treino / {len(particoes['val'])} validação")
    if ignoradas_sem_arquivo:
        print(f"  - Ignoradas (arquivo ausente em {uploads_dir}): {ignoradas_sem_arquivo}")
    print(f"\nPara retreinar com esses dados: yolo detect train model=best.pt data={pasta_saida / 'data.yaml'} epochs=50")
    return 0


if __name__ == "__main__":
    sys.exit(main())