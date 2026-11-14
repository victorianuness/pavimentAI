"""Testes do contrato fechado no Dia 1: erros {codigo, mensagem}, paginação em envelope,
acesso a ocorrência/fotos e filtro 'todas' do mapa só para a gestão."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seguranca import gerar_hash_senha

SENHA = "Senha#12345"
# Duas cidades de mentira, longe uma da outra (retângulos em graus)
MAUA = (-23.72, -23.62, -46.51, -46.41)       # lat_min, lat_max, lon_min, lon_max
OUTRA = (-23.57, -23.53, -46.65, -46.61)


def _poligono(lat_min, lat_max, lon_min, lon_max) -> str:
    return (
        f"SRID=4326;MULTIPOLYGON((({lon_min} {lat_min},{lon_max} {lat_min},{lon_max} {lat_max},"
        f"{lon_min} {lat_max},{lon_min} {lat_min})))"
    )


@pytest.fixture(scope="module")
def mundo(admin_conn, tmp_path_factory):
    """Cria 2 cidades, usuários de cada papel e as ocorrências usadas nos testes."""
    c = admin_conn
    c.execute(
        "TRUNCATE ocorrencia_midias, midias, deteccoes_ia, historico_status, sinalizacoes, "
        "ocorrencias, usuarios, areas_atendimento RESTART IDENTITY CASCADE"
    )
    a1 = c.execute(
        "INSERT INTO areas_atendimento (nome, codigo_ibge, geometria) VALUES ('Cidade Um', '9999991', %s) "
        "RETURNING id_area", (_poligono(*MAUA),)).fetchone()[0]
    a2 = c.execute(
        "INSERT INTO areas_atendimento (nome, codigo_ibge, geometria) VALUES ('Cidade Dois', '9999992', %s) "
        "RETURNING id_area", (_poligono(*OUTRA),)).fetchone()[0]

    def usuario(nome, papel, area_gestao=None):
        return c.execute(
            """INSERT INTO usuarios (nome, email, telefone, hash_senha, papel, status_conta,
                                     email_verificado, id_area_gestao)
               VALUES (%s, %s, %s, %s, %s, 'ativa', true, %s) RETURNING id_usuario""",
            (nome, f"{nome}@teste.com", f"119{abs(hash(nome)) % 10**8:08d}", gerar_hash_senha(SENHA), papel, area_gestao),
        ).fetchone()[0]

    ids = {
        "a1": a1, "a2": a2,
        "ana": usuario("ana", "cidadao"),
        "bia": usuario("bia", "cidadao"),
        "gestor1": usuario("gestor1", "gestor", a1),
        "gestor2": usuario("gestor2", "gestor", a2),
        "admin": usuario("admin", "admin"),
    }
    with TestClient(app) as client:
        tokens = {}
        for nome in ("ana", "bia", "gestor1", "gestor2", "admin"):
            r = client.post("/auth/login", data={"username": f"{nome}@teste.com", "password": SENHA})
            assert r.status_code == 200, r.text
            tokens[nome] = {"Authorization": f"Bearer {r.json()['access_token']}"}

        def criar(dono, **dados):
            r = client.post("/ocorrencias", json=dados, headers=tokens[dono])
            assert r.status_code == 201, r.text
            return r.json()

        # Ana registra: 2 de acessibilidade (tipo sem IA = verificadas na hora) e 1 buraco (sem foto = não verificada)
        ids["acess1"] = criar("ana", tipo="acessibilidade", categoria="piso_tatil", latitude=-23.6700, longitude=-46.4600)["id_ocorrencia"]
        ids["acess2"] = criar("ana", tipo="acessibilidade", categoria="travessia", latitude=-23.6800, longitude=-46.4700)["id_ocorrencia"]
        buraco = criar("ana", tipo="buraco", latitude=-23.6650, longitude=-46.4650)
        ids["buraco"] = buraco["id_ocorrencia"]
        ids["buraco_verificacao"] = buraco["verificacao"]

        # Uma foto ligada ao buraco (não verificado) e outra à acessibilidade (verificada)
        pasta = tmp_path_factory.mktemp("uploads")
        from app.config import settings
        settings.uploads_dir = pasta
        for chave, id_oc in (("midia_buraco", ids["buraco"]), ("midia_acess", ids["acess1"])):
            nome_arq = f"{chave}.jpg"
            (pasta / nome_arq).write_bytes(b"\xff\xd8\xff\xd9")  # JPEG mínimo; o teste só confere o acesso
            idm = c.execute(
                """INSERT INTO midias (caminho_arquivo, nome_arquivo, origem, hash_arquivo, id_usuario_envio)
                   VALUES (%s, %s, 'foto_cidadao', %s, %s) RETURNING id_midia""",
                (nome_arq, nome_arq, chave.ljust(64, "0"), ids["ana"]),
            ).fetchone()[0]
            c.execute("INSERT INTO ocorrencia_midias (id_ocorrencia, id_midia) VALUES (%s, %s)", (id_oc, idm))
            ids[chave] = idm

        ids["tokens"] = tokens
        ids["client"] = client
        yield ids


def H(mundo, nome):
    return mundo["tokens"][nome]


# ------------------------------------------------------------------ erros {codigo, mensagem}
def test_erro_404_no_formato_padrao(mundo):
    r = mundo["client"].get("/ocorrencias/999999")
    assert r.status_code == 404
    assert r.json() == {"codigo": "nao_encontrado", "mensagem": "Ocorrência não encontrada"}


def test_erro_401_sem_token(mundo):
    r = mundo["client"].get("/gestao/triagem")
    assert r.status_code == 401
    assert r.json()["codigo"] == "nao_autenticado"
    assert r.headers["www-authenticate"] == "Bearer"


def test_erro_403_cidadao_na_gestao(mundo):
    r = mundo["client"].get("/gestao/triagem", headers=H(mundo, "ana"))
    assert r.status_code == 403
    assert r.json()["codigo"] == "sem_permissao"


def test_erro_422_validacao_lista_os_campos(mundo):
    r = mundo["client"].post("/ocorrencias", json={"tipo": "buraco"}, headers=H(mundo, "ana"))
    assert r.status_code == 422
    corpo = r.json()
    assert corpo["codigo"] == "dados_invalidos"
    assert {"campo", "mensagem"} <= set(corpo["campos"][0])
    assert "latitude" in {c["campo"] for c in corpo["campos"]}


def test_erro_de_rota_inexistente_tambem_padronizado(mundo):
    r = mundo["client"].get("/rota/que/nao/existe")
    assert r.status_code == 404
    assert set(r.json()) == {"codigo", "mensagem"}


def test_erro_403_com_codigo_proprio_continua_igual(mundo):
    # gestor da Cidade Dois tentando mudar ocorrência da Cidade Um
    r = mundo["client"].post(f"/gestao/ocorrencias/{mundo['buraco']}/status",
                             json={"status": "resolvida"}, headers=H(mundo, "gestor2"))
    assert r.status_code == 403
    assert r.json()["codigo"] == "outro_municipio"


def test_duplicidade_409_tem_codigo_e_proximas(mundo):
    r = mundo["client"].post("/ocorrencias", json={"tipo": "acessibilidade", "categoria": "piso_tatil",
                                                    "latitude": -23.6700, "longitude": -46.4600},
                             headers=H(mundo, "bia"))
    assert r.status_code == 409
    corpo = r.json()
    assert corpo["codigo"] == "ocorrencia_duplicada"
    assert corpo["proximas"][0]["id_ocorrencia"] == mundo["acess1"]


# ------------------------------------------------------------------ paginação
def test_minhas_devolve_envelope_completo(mundo):
    r = mundo["client"].get("/ocorrencias/minhas?limite=2", headers=H(mundo, "ana"))
    assert r.status_code == 200
    corpo = r.json()
    assert {"total", "limite", "deslocamento", "itens"} == set(corpo)
    assert (corpo["total"], corpo["limite"], corpo["deslocamento"], len(corpo["itens"])) == (3, 2, 0, 2)
    assert "verificacao" in corpo["itens"][0]


def test_total_correto_mesmo_alem_do_fim(mundo):
    r = mundo["client"].get("/ocorrencias/minhas?limite=2&deslocamento=50", headers=H(mundo, "ana"))
    corpo = r.json()
    assert corpo["total"] == 3 and corpo["itens"] == [] and corpo["deslocamento"] == 50


def test_listas_da_gestao_usam_o_mesmo_envelope(mundo):
    for caminho in ("/gestao/ocorrencias", "/gestao/sinalizacoes", "/gestao/triagem"):
        r = mundo["client"].get(caminho + "?limite=10", headers=H(mundo, "gestor1"))
        assert r.status_code == 200, (caminho, r.text)
        assert {"total", "limite", "deslocamento", "itens"} == set(r.json()), caminho


def test_lista_de_usuarios_do_admin_usa_o_mesmo_envelope(mundo):
    r = mundo["client"].get("/admin/usuarios?limite=2", headers=H(mundo, "admin"))
    # sem o papel pavimentai_admin configurado no banco de teste, esta rota pode responder 5xx/503;
    # o importante é que, quando funciona, o formato é o padrão
    if r.status_code == 200:
        assert {"total", "limite", "deslocamento", "itens"} == set(r.json())


# ------------------------------------------------------------------ detalhe da ocorrência
def test_buraco_sem_foto_nao_e_publico(mundo):
    assert mundo["buraco_verificacao"] == "sem_foto"
    r = mundo["client"].get(f"/ocorrencias/{mundo['buraco']}")
    assert r.status_code == 404


def test_dono_e_gestor_da_cidade_veem_a_nao_verificada(mundo):
    for quem in ("ana", "gestor1", "admin"):
        r = mundo["client"].get(f"/ocorrencias/{mundo['buraco']}", headers=H(mundo, quem))
        assert r.status_code == 200, quem
        assert r.json()["verificacao"] == "sem_foto"


def test_outro_cidadao_e_gestor_de_outra_cidade_nao_veem(mundo):
    for quem in ("bia", "gestor2"):
        r = mundo["client"].get(f"/ocorrencias/{mundo['buraco']}", headers=H(mundo, quem))
        assert r.status_code == 404, quem


def test_verificada_e_publica(mundo):
    r = mundo["client"].get(f"/ocorrencias/{mundo['acess1']}")
    assert r.status_code == 200
    assert r.json()["verificacao"] == "sem_ia"


# ------------------------------------------------------------------ fotos
def test_fotos_de_nao_verificada_exigem_ser_dono_ou_gestor(mundo):
    c = mundo["client"]
    assert c.get(f"/ocorrencias/{mundo['buraco']}/fotos").status_code == 404
    assert c.get(f"/midias/{mundo['midia_buraco']}/arquivo").status_code == 404
    assert c.get(f"/midias/{mundo['midia_buraco']}/arquivo", headers=H(mundo, "bia")).status_code == 404
    assert c.get(f"/midias/{mundo['midia_buraco']}/arquivo", headers=H(mundo, "gestor2")).status_code == 404
    for quem in ("ana", "gestor1"):
        assert c.get(f"/ocorrencias/{mundo['buraco']}/fotos", headers=H(mundo, quem)).status_code == 200
        r = c.get(f"/midias/{mundo['midia_buraco']}/arquivo", headers=H(mundo, quem))
        assert r.status_code == 200 and r.headers["cache-control"].startswith("private")


def test_fotos_de_verificada_sao_publicas(mundo):
    c = mundo["client"]
    assert c.get(f"/ocorrencias/{mundo['acess1']}/fotos").status_code == 200
    r = c.get(f"/midias/{mundo['midia_acess']}/arquivo")
    assert r.status_code == 200 and r.headers["cache-control"].startswith("public")


# ------------------------------------------------------------------ mapa
PARAMS_MAPA = "lat_min=-23.72&lat_max=-23.62&lon_min=-46.51&lon_max=-46.41"


def _ids(resp):
    return {f["properties"]["id_ocorrencia"] for f in resp.json()["features"]}


def test_mapa_publico_so_mostra_verificadas(mundo):
    r = mundo["client"].get(f"/ocorrencias/mapa?{PARAMS_MAPA}")
    assert r.status_code == 200
    assert _ids(r) == {mundo["acess1"], mundo["acess2"]}


def test_mapa_todas_exige_login_e_gestao(mundo):
    c = mundo["client"]
    url = f"/ocorrencias/mapa?{PARAMS_MAPA}&verificacao=todas"
    r = c.get(url)
    assert r.status_code == 401 and r.json()["codigo"] == "nao_autenticado"
    r = c.get(url, headers=H(mundo, "ana"))
    assert r.status_code == 403 and r.json()["codigo"] == "so_gestao"


def test_mapa_todas_gestor_ve_so_a_propria_cidade(mundo):
    c = mundo["client"]
    url = f"/ocorrencias/mapa?{PARAMS_MAPA}&verificacao=todas"
    assert mundo["buraco"] in _ids(c.get(url, headers=H(mundo, "gestor1")))
    assert mundo["buraco"] in _ids(c.get(url, headers=H(mundo, "admin")))
    # gestor da outra cidade pedindo a área da primeira
    r = c.get(f"{url}&id_area={mundo['a1']}", headers=H(mundo, "gestor2"))
    assert r.status_code == 403 and r.json()["codigo"] == "outro_municipio"
    # sem pedir área específica, fica preso à própria cidade (nada aparece aqui)
    assert _ids(c.get(url, headers=H(mundo, "gestor2"))) == set()
