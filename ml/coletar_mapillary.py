#!/usr/bin/env python3
"""PavimentAI - Coletor de imagens públicas de ruas via Mapillary API v4 (CC-BY-SA).

Permite expandir o dataset de treinamento e validação com fotos reais das vias do
ABC Paulista sem violar os Termos de Serviço do Google Street View.
Opcionalmente executa pré-rotulagem automática (Pseudo-Labeling / Active Learning)
com o modelo YOLO do projeto.

Exemplos:
    python coletar_mapillary.py --cidade maua --limite 100 --token MLY|...
    python coletar_mapillary.py --cidade ribeirao_pires --limite 50 --auto-rotular
"""
import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Bounding Boxes (lon_min, lat_min, lon_max, lat_max) das cidades do ABC Paulista
BBOX_CIDADES = {
    "maua": (-46.4950, -23.7150, -46.4050, -23.6350),
    "ribeirao_pires": (-46.4761, -23.7707, -46.3307, -23.6177),
    "santo_andre": (-46.5700, -23.7300, -46.4600, -23.6100),
    "sao_bernardo": (-46.6300, -23.8200, -46.5100, -23.6600),
    "sao_caetano": (-46.5850, -23.6500, -46.5400, -23.6000),
}

MAPILLARY_API_URL = "https://graph.mapillary.com/images"


def _carregar_token_env() -> str | None:
    token = os.getenv("MAPILLARY_TOKEN")
    if token:
        return token
    env_api = Path(__file__).resolve().parents[1] / "api" / ".env"
    if env_api.is_file():
        for linha in env_api.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha.startswith("MAPILLARY_TOKEN="):
                return linha.partition("=")[2].strip().strip("'\"")
    return None


def buscar_imagens_mapillary(bbox: tuple[float, float, float, float], token: str, limite: int) -> list[dict]:
    """Busca metadados e URLs de imagens não-panorâmicas (câmera frontal/celular) na área."""
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    params = urllib.parse.urlencode({
        "access_token": token,
        "fields": "id,thumb_1024_url,computed_geometry,captured_at,is_pano",
        "bbox": bbox_str,
        "is_pano": "false",  # Ignora câmeras 360º para manter perspectiva real de painel/celular
        "limit": min(limite * 2, 500),
    })
    url = f"{MAPILLARY_API_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "PavimentAI-DatasetCollector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            dados = json.load(resp)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", errors="ignore")
        sys.exit(f"Erro na API do Mapillary (HTTP {e.code}): {corpo}")
    except OSError as e:
        sys.exit(f"Falha de conexão com o Mapillary: {e}")

    itens = dados.get("data", [])
    filtrados = [
        it for it in itens
        if not it.get("is_pano") and it.get("thumb_1024_url")
    ]
    return filtrados[:limite]


def baixar_arquivo(url: str, destino: Path) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "PavimentAI-DatasetCollector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            destino.write_bytes(resp.read())
        return True
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Baixa imagens públicas de ruas (CC-BY-SA) do Mapillary para treino/teste."
    )
    ap.add_argument(
        "--cidade",
        choices=sorted(BBOX_CIDADES.keys()),
        default="maua",
        help="Município predefinido para coleta (padrão: maua)",
    )
    ap.add_argument(
        "--bbox",
        help="Bounding box customizado 'lon_min,lat_min,lon_max,lat_max' (sobrescreve --cidade)",
    )
    ap.add_argument("--limite", type=int, default=50, help="Quantidade máxima de fotos (padrão: 50)")
    ap.add_argument("--token", default=_carregar_token_env(), help="Client Token da API v4 do Mapillary")
    ap.add_argument(
        "--saida",
        default="dataset_mapillary",
        help="Pasta onde as fotos e anotações serão salvas (padrão: dataset_mapillary)",
    )
    ap.add_argument(
        "--auto-rotular",
        action="store_true",
        help="Executa o modelo YOLO do projeto sobre as fotos baixadas gerando pseudo-labels YOLO",
    )
    ap.add_argument("--conf", type=float, default=0.35, help="Confiança mínima na auto-rotulagem (padrão: 0.35)")
    args = ap.parse_args()

    if not args.token:
        print(
            "ERRO: Informe um token gratuito da API v4 do Mapillary via --token MLY|... "
            "ou defina MAPILLARY_TOKEN no arquivo api/.env.\n"
            "Obtenha gratuitamente em: https://www.mapillary.com/dashboard/developers"
        )
        return 1

    if args.bbox:
        try:
            partes = [float(x.strip()) for x in args.bbox.split(",")]
            if len(partes) != 4:
                raise ValueError
            bbox = (partes[0], partes[1], partes[2], partes[3])
            nome_area = "custom"
        except ValueError:
            print("Formato inválido para --bbox. Use: lon_min,lat_min,lon_max,lat_max")
            return 1
    else:
        bbox = BBOX_CIDADES[args.cidade]
        nome_area = args.cidade

    pasta_base = Path(args.saida) / nome_area
    pasta_img = pasta_base / "images"
    pasta_lbl = pasta_base / "labels"
    pasta_img.mkdir(parents=True, exist_ok=True)
    if args.auto_rotular:
        pasta_lbl.mkdir(parents=True, exist_ok=True)

    print(f"Buscando até {args.limite} imagens públicas (CC-BY-SA) em '{nome_area}' {bbox} ...")
    imagens = buscar_imagens_mapillary(bbox, args.token, args.limite)
    if not imagens:
        print("Nenhuma imagem encontrada para este recorte geográfico.")
        return 0

    modelo = None
    if args.auto_rotular:
        from inference.testar_modelo import _descobrir_modelo_padrao
        from ultralytics import YOLO

        caminho_mod = _descobrir_modelo_padrao()
        print(f"Carregando modelo YOLO ({caminho_mod}) para pré-rotulagem automática...")
        modelo = YOLO(caminho_mod)

    baixadas = com_buraco = 0
    metadados_csv = pasta_base / "metadados_mapillary.csv"

    with open(metadados_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id_mapillary", "arquivo", "longitude", "latitude", "capturada_em", "n_buracos_pseudo"])

        for item in imagens:
            img_id = str(item["id"])
            url = item["thumb_1024_url"]
            coords = (item.get("computed_geometry") or {}).get("coordinates") or [None, None]
            arq_img = pasta_img / f"mly_{img_id}.jpg"

            if not arq_img.is_file():
                if not baixar_arquivo(url, arq_img):
                    continue
            baixadas += 1

            n_det = 0
            if modelo is not None:
                r = modelo.predict(str(arq_img), conf=args.conf, imgsz=640, verbose=False)[0]
                n_det = len(r.boxes)
                linhas_yolo = []
                for b in r.boxes:
                    xc, yc, bw, bh = b.xywhn[0].tolist()
                    linhas_yolo.append(f"0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
                (pasta_lbl / f"mly_{img_id}.txt").write_text(
                    "\n".join(linhas_yolo) + ("\n" if linhas_yolo else ""),
                    encoding="utf-8",
                )
                if n_det > 0:
                    com_buraco += 1

            w.writerow([img_id, arq_img.name, coords[0], coords[1], item.get("captured_at"), n_det])

    print(f"\nColeta concluída! {baixadas} imagens públicas salvas em: {pasta_base.resolve()}")
    if args.auto_rotular:
        print(
            f"  - Pré-rotulagem YOLO: {com_buraco} imagens com possível buraco detectado "
            f"e {baixadas - com_buraco} backgrounds limpos."
        )
    print("Licença dos dados: Mapillary CC-BY-SA 4.0 (atribuição registrada em metadados_mapillary.csv).")
    return 0


if __name__ == "__main__":
    sys.exit(main())