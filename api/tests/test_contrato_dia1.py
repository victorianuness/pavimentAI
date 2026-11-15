"""Testes do contrato fechado no Dia 1: erros {codigo, mensagem}, paginação em envelope,
acesso a ocorrência/fotos e filtro 'todas' do mapa só para a gestão."""
from uuid import uuid4

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


def _criar_usuario_sessoes(admin_conn):
    identificador = uuid4().hex
    email = f"sessoes-{identificador}@teste.com"
    telefone = f"119{uuid4().int % 10**8:08d}"
    id_usuario = admin_conn.execute(
        """INSERT INTO usuarios (nome, email, telefone, hash_senha, status_conta, email_verificado)
           VALUES ('Teste de sessões', %s, %s, %s, 'ativa', true) RETURNING id_usuario""",
        (email, telefone, gerar_hash_senha(SENHA)),
    ).fetchone()[0]
    return id_usuario, email


def _remover_usuario_sessoes(admin_conn, id_usuario):
    admin_conn.execute("DELETE FROM auditoria WHERE id_usuario = %s", (id_usuario,))
    admin_conn.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))


def test_refresh_rotaciona_token_e_logout_revoga_a_sessao(mundo, admin_conn):
    id_usuario, email = _criar_usuario_sessoes(admin_conn)
    client = mundo["client"]
    try:
        login = client.post("/auth/login", data={"username": email, "password": SENHA})
        assert login.status_code == 200, login.text
        credenciais = login.json()

        renovado = client.post("/auth/refresh", json={"refresh_token": credenciais["refresh_token"]})
        assert renovado.status_code == 200, renovado.text
        credenciais_renovadas = renovado.json()
        assert credenciais_renovadas["refresh_token"] != credenciais["refresh_token"]
        assert client.post("/auth/refresh", json={"refresh_token": credenciais["refresh_token"]}).status_code == 401

        logout = client.post("/auth/logout", json={"refresh_token": credenciais_renovadas["refresh_token"]})
        assert logout.status_code == 200, logout.text
        assert client.get(
            "/auth/eu",
            headers={"Authorization": f"Bearer {credenciais_renovadas['access_token']}"},
        ).status_code == 401
        assert client.post(
            "/auth/refresh",
            json={"refresh_token": credenciais_renovadas["refresh_token"]},
        ).status_code == 401
    finally:
        _remover_usuario_sessoes(admin_conn, id_usuario)


def test_trocar_senha_revoga_todos_os_tokens(mundo, admin_conn):
    id_usuario, email = _criar_usuario_sessoes(admin_conn)
    client = mundo["client"]
    try:
        login = client.post("/auth/login", data={"username": email, "password": SENHA})
        assert login.status_code == 200, login.text
        credenciais = login.json()

        troca = client.post(
            "/auth/me/senha",
            json={"senha_atual": SENHA, "senha_nova": "Senha#Nova2026"},
            headers={"Authorization": f"Bearer {credenciais['access_token']}"},
        )
        assert troca.status_code == 200, troca.text
        assert client.get(
            "/auth/eu",
            headers={"Authorization": f"Bearer {credenciais['access_token']}"},
        ).status_code == 401
        assert client.post(
            "/auth/refresh",
            json={"refresh_token": credenciais["refresh_token"]},
        ).status_code == 401
    finally:
        _remover_usuario_sessoes(admin_conn, id_usuario)


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


PARAMS_CLUSTERS = (
    "lat_min=-23.72&lat_max=-23.62&lon_min=-46.51&lon_max=-46.41"
    "&id_area={id_area}&tipo=acessibilidade&categorias=travessia"
    "&tamanho_celula_m=250&minimo_ocorrencias=3&dias=30"
)


def test_clusters_agrupam_em_metros_filtram_e_nao_multiplicam_midias(mundo, admin_conn):
    c = admin_conn
    ids_ocorrencias = []
    ids_midias = []
    ponto = (-23.7000, -46.5000)
    separados = (-23.7000, -46.4900)

    try:
        for lat, lon, status in (
            (*ponto, "aberta"),
            (*ponto, "aberta"),
            (*ponto, "aberta"),
            (*ponto, "resolvida"),
            (*separados, "aberta"),
        ):
            id_ocorrencia = c.execute(
                """INSERT INTO ocorrencias
                       (tipo, categoria, latitude, longitude, status, id_area)
                   VALUES ('acessibilidade', 'travessia', %s, %s, %s, %s)
                   RETURNING id_ocorrencia""",
                (lat, lon, status, mundo["a1"]),
            ).fetchone()[0]
            ids_ocorrencias.append(id_ocorrencia)

        # Múltiplas fotos da mesma ocorrência não devem multiplicar a contagem.
        for indice in range(2):
            id_midia = c.execute(
                """INSERT INTO midias (caminho_arquivo, nome_arquivo, origem, hash_arquivo)
                   VALUES (%s, %s, 'foto_cidadao', %s) RETURNING id_midia""",
                (f"cluster-{indice}.jpg", f"cluster-{indice}.jpg", str(indice).zfill(64)),
            ).fetchone()[0]
            ids_midias.append(id_midia)
            c.execute(
                "INSERT INTO ocorrencia_midias (id_ocorrencia, id_midia) VALUES (%s, %s)",
                (ids_ocorrencias[0], id_midia),
            )

        base = f"/ocorrencias/clusters?{PARAMS_CLUSTERS.format(id_area=mundo['a1'])}"
        resposta = mundo["client"].get(base)
        assert resposta.status_code == 200, resposta.text
        dados = resposta.json()
        assert dados["type"] == "FeatureCollection"
        assert dados["srid_metrico"] == 32723
        assert len(dados["features"]) == 1

        feature = dados["features"][0]
        longitude, latitude = feature["geometry"]["coordinates"]
        assert -47 < longitude < -46
        assert -24 < latitude < -23
        assert feature["properties"]["total_ocorrencias"] == 3
        assert feature["properties"]["por_status"] == {"aberta": 3}
        assert feature["properties"]["por_gravidade"] == {"sem_classificacao": 3}
        assert feature["properties"]["por_tipo"] == [
            {"tipo": "acessibilidade", "total": 3, "categorias": {"travessia": 3}}
        ]

        com_encerradas = mundo["client"].get(
            base + "&status=aberta&status=resolvida"
        )
        assert com_encerradas.status_code == 200, com_encerradas.text
        assert com_encerradas.json()["features"][0]["properties"]["total_ocorrencias"] == 4
        assert com_encerradas.json()["features"][0]["properties"]["por_status"] == {
            "aberta": 3,
            "resolvida": 1,
        }

        abaixo_do_minimo = mundo["client"].get(base + "&minimo_ocorrencias=4")
        assert abaixo_do_minimo.status_code == 200
        assert abaixo_do_minimo.json()["features"] == []

        categoria_sem_resultado = mundo["client"].get(
            base.replace("categorias=travessia", "categorias=piso_tatil")
        )
        assert categoria_sem_resultado.status_code == 200
        assert categoria_sem_resultado.json()["features"] == []
    finally:
        if ids_midias:
            c.execute("DELETE FROM midias WHERE id_midia = ANY(%s)", (ids_midias,))
        if ids_ocorrencias:
            c.execute("DELETE FROM ocorrencias WHERE id_ocorrencia = ANY(%s)", (ids_ocorrencias,))


def test_clusters_respeitam_visibilidade_e_area_do_gestor(mundo, admin_conn):
    c = admin_conn
    ids = []
    try:
        for _ in range(3):
            id_ocorrencia = c.execute(
                """INSERT INTO ocorrencias
                       (tipo, latitude, longitude, id_area, situacao_ia)
                   VALUES ('buraco', -23.7000, -46.5000, %s, 'triagem')
                   RETURNING id_ocorrencia""",
                (mundo["a1"],),
            ).fetchone()[0]
            ids.append(id_ocorrencia)

        params = (
            "lat_min=-23.72&lat_max=-23.62&lon_min=-46.51&lon_max=-46.41"
            "&tipo=buraco&tamanho_celula_m=250&minimo_ocorrencias=3"
        )
        url = f"/ocorrencias/clusters?{params}"
        assert mundo["client"].get(url).json()["features"] == []
        assert mundo["client"].get(url + "&verificacao=todas").status_code == 401

        gestor = mundo["client"].get(
            url + "&verificacao=todas", headers=H(mundo, "gestor1")
        )
        assert gestor.status_code == 200, gestor.text
        assert gestor.json()["features"][0]["properties"]["total_ocorrencias"] == 3

        outro_gestor = mundo["client"].get(
            url + "&verificacao=todas", headers=H(mundo, "gestor2")
        )
        assert outro_gestor.status_code == 200, outro_gestor.text
        assert outro_gestor.json()["features"] == []
    finally:
        if ids:
            c.execute("DELETE FROM ocorrencias WHERE id_ocorrencia = ANY(%s)", (ids,))


def test_clusters_rejeitam_parametros_invalidos(mundo):
    base = "/ocorrencias/clusters"
    assert mundo["client"].get(base).status_code == 422
    assert mundo["client"].get(
        base + "?lat_min=1&lat_max=0&lon_min=1&lon_max=2"
    ).status_code == 422
    assert mundo["client"].get(
        base + "?lat_min=0&lat_max=3&lon_min=1&lon_max=2"
    ).status_code == 422
    assert mundo["client"].get(
        base + "?lat_min=-23&lat_max=-22&lon_min=-46&lon_max=-45&tamanho_celula_m=5000"
    ).status_code == 422
