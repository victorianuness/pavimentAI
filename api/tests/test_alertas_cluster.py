"""Testes dos alertas automáticos de cluster (migração v12 + notificacoes.py + /gestao/alertas).

Precisam do banco de teste com a migração v12 aplicada (veja tests/conftest.py).
As regras que não dependem de banco (decidir_motivo, texto do e-mail) rodam sempre.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app import email_envio, notificacoes
from app.notificacoes import decidir_motivo, montar_mensagem, srid_da_area
from app.seguranca import gerar_hash_senha

SENHA = "Senha#12345"
CIDADE_UM = (-23.72, -23.62, -46.51, -46.41)  # lat_min, lat_max, lon_min, lon_max
CIDADE_DOIS = (-23.57, -23.53, -46.65, -46.61)
PONTO = (-23.6700, -46.4600)  # lat, lon: fica dentro da Cidade Um


# ----------------------------------------------------------------- regras sem banco
AGORA = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def _motivo(nivel, criados, ultimo, **kw):
    return decidir_motivo(nivel, criados, ultimo, AGORA, minimo=kw.get("minimo", 3), reenvio_h=kw.get("reenvio_h", 24))


def test_cluster_nunca_avisado_e_novo():
    assert _motivo("normal", [AGORA] * 3, None) == "novo"


def test_mesmo_cluster_logo_depois_nao_avisa_de_novo():
    ultimo = {"nivel": "normal", "criado_em": AGORA - timedelta(hours=1)}
    assert _motivo("normal", [AGORA - timedelta(hours=2)] * 3, ultimo) is None


def test_subir_de_nivel_avisa_mesmo_dentro_do_prazo():
    ultimo = {"nivel": "normal", "criado_em": AGORA - timedelta(minutes=10)}
    assert _motivo("moderada", [AGORA] * 5, ultimo) == "escalada"


def test_nao_avisa_ao_descer_de_nivel():
    ultimo = {"nivel": "alta", "criado_em": AGORA - timedelta(days=3)}
    assert _motivo("normal", [AGORA - timedelta(days=4)] * 3, ultimo) is None


def test_crescimento_exige_prazo_e_ocorrencias_novas_depois_do_ultimo_aviso():
    ultimo = {"nivel": "normal", "criado_em": AGORA - timedelta(hours=30)}
    velhas = [AGORA - timedelta(hours=40)] * 3
    novas = [AGORA - timedelta(hours=2)] * 3
    assert _motivo("normal", velhas, ultimo) is None  # passou o prazo, mas nada novo
    assert _motivo("normal", velhas + novas[:2], ultimo) is None  # só 2 novas (< mínimo)
    assert _motivo("normal", velhas + novas, ultimo) == "crescimento"
    recente = {"nivel": "normal", "criado_em": AGORA - timedelta(hours=3)}
    assert _motivo("normal", velhas + novas, recente) is None  # novas, mas ainda dentro do prazo


def test_srid_da_area_zona_utm_do_hemisferio_sul():
    assert srid_da_area(-46.41, -23.66) == 32723  # Grande São Paulo = UTM 23S
    assert srid_da_area(10.0, 50.0) == 32632  # hemisfério norte usa 326xx


def test_mensagem_traz_o_que_a_secretaria_precisa():
    assunto, texto = montar_mensagem(
        "Mauá\r\nBcc: x@y.com",
        {
            "total": 7, "nivel": "moderada", "motivo": "novo", "janela_h": 72, "celula_m": 250,
            "por_tipo": {"Buraco na via": 5, "Acessibilidade": 2},
            "por_gravidade": {"leve": 1, "grave": 2, "sem_classificacao": 4},
            "latitude": -23.67, "longitude": -46.46,
            "ultima_ocorrencia_em": datetime(2026, 11, 15, 15, 30, tzinfo=timezone.utc),
        },
    )
    assert "\n" not in assunto and "\r" not in assunto  # nome da cidade não quebra o cabeçalho
    assert "7 ocorrências" in assunto and "moderada" in assunto
    assert "Buraco na via: 5" in texto and "grave: 2" in texto
    assert texto.index("grave: 2") < texto.index("leve: 1")  # gravidade da pior para a melhor
    assert "15/11/2026 12:30" in texto  # horário de Brasília (UTC-3)
    assert "https://www.google.com/maps?q=-23.670000,-46.460000" in texto
    assert "não o risco real" in texto


def test_email_sem_smtp_e_simulado_e_com_smtp_quebrado_falha(monkeypatch):
    monkeypatch.setattr(email_envio.settings, "smtp_host", None)
    assert email_envio.enviar_email_com_resultado("a@b.com", "assunto", "texto") == "simulado"
    # SMTP configurado, mas sem usuário/senha: não pode dizer que enviou
    monkeypatch.setattr(email_envio.settings, "smtp_host", "localhost")
    monkeypatch.setattr(email_envio.settings, "smtp_usuario", None)
    assert email_envio.enviar_email_com_resultado("a@b.com", "assunto", "texto") == "falhou"
    # SMTP configurado, mas ninguém atende na porta
    monkeypatch.setattr(email_envio.settings, "smtp_usuario", "u")
    monkeypatch.setattr(email_envio.settings, "smtp_senha", "s")
    monkeypatch.setattr(email_envio.settings, "smtp_porta", 1)
    assert email_envio.enviar_email_com_resultado("a@b.com", "assunto", "texto") == "falhou"


def test_laco_automatico_repete_e_sobrevive_a_erro(monkeypatch):
    chamadas = []

    def falsa_executar(*a, **k):
        chamadas.append(1)
        if len(chamadas) == 1:
            raise RuntimeError("erro de mentira na primeira conferência")

    real_sleep = asyncio.sleep

    async def sono_curto(_segundos):
        await real_sleep(0.001)

    monkeypatch.setattr(notificacoes, "executar", falsa_executar)
    monkeypatch.setattr(notificacoes.asyncio, "sleep", sono_curto)

    async def rodar():
        tarefa = asyncio.create_task(notificacoes.laco_de_verificacao())
        await real_sleep(0.1)
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa

    asyncio.run(rodar())
    assert len(chamadas) >= 2  # o erro da 1ª não derrubou o laço


# ----------------------------------------------------------------- com banco
def _poligono(lat_min, lat_max, lon_min, lon_max) -> str:
    return (
        f"SRID=4326;MULTIPOLYGON((({lon_min} {lat_min},{lon_max} {lat_min},{lon_max} {lat_max},"
        f"{lon_min} {lat_max},{lon_min} {lat_min})))"
    )


@pytest.fixture(scope="module")
def mundo(admin_conn, client_api):
    c = admin_conn
    c.execute(
        "TRUNCATE alertas_cluster, contatos_alerta, ocorrencia_midias, midias, deteccoes_ia, "
        "historico_status, sinalizacoes, ocorrencias, usuarios, areas_atendimento RESTART IDENTITY CASCADE"
    )
    a1 = c.execute(
        "INSERT INTO areas_atendimento (nome, codigo_ibge, geometria) VALUES ('Cidade Um', '9999991', %s) "
        "RETURNING id_area", (_poligono(*CIDADE_UM),)).fetchone()[0]
    a2 = c.execute(
        "INSERT INTO areas_atendimento (nome, codigo_ibge, geometria) VALUES ('Cidade Dois', '9999992', %s) "
        "RETURNING id_area", (_poligono(*CIDADE_DOIS),)).fetchone()[0]

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
        "gestor1": usuario("gestor1", "gestor", a1),
        "gestor2": usuario("gestor2", "gestor", a2),
        "admin": usuario("admin", "admin"),
    }
    ids["tokens"] = {}
    for nome in ("ana", "gestor1", "gestor2", "admin"):
        r = client_api.post("/auth/login", data={"username": f"{nome}@teste.com", "password": SENHA})
        assert r.status_code == 200, r.text
        ids["tokens"][nome] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    ids["client"] = client_api
    ids["conn"] = c
    yield ids


def H(mundo, nome):
    return mundo["tokens"][nome]


def _inserir(mundo, n, *, area="a1", tipo="acessibilidade", categoria="piso_tatil", horas_atras=1,
             situacao_ia=None, status="aberta", ponto=PONTO, tirar=0):
    """Insere n ocorrências coladas umas nas outras (mesma célula de 250 m)."""
    for i in range(n):
        mundo["conn"].execute(
            """INSERT INTO ocorrencias (tipo, categoria, latitude, longitude, status, id_usuario_criador,
                                        id_area, criado_em, situacao_ia)
               VALUES (%s, %s, %s, %s, %s, %s, %s, now() - make_interval(hours => %s), %s)""",
            (tipo, categoria, ponto[0] + (tirar + i) * 0.00002, ponto[1], status, mundo["ana"],
             mundo[area], horas_atras, situacao_ia),
        )


def _limpar(mundo):
    mundo["conn"].execute("DELETE FROM ocorrencias")
    mundo["conn"].execute("TRUNCATE alertas_cluster, contatos_alerta RESTART IDENTITY")
    mundo["conn"].execute("DELETE FROM auditoria WHERE acao LIKE 'alerta_cluster%' OR acao LIKE 'contato_alerta%'")


def _contato(mundo, quem="gestor1", email="obras@cidade1.gov.br", **extra):
    return mundo["client"].post(
        "/gestao/alertas/contatos", json={"destino": email, **extra}, headers=H(mundo, quem)
    )


def _verificar(mundo, quem="gestor1", **params):
    r = mundo["client"].post("/gestao/alertas/verificar", params=params, headers=H(mundo, quem))
    assert r.status_code == 200, r.text
    return r.json()


def _alertas_no_banco(mundo):
    campos = ("status", "nivel", "motivo", "total_ocorrencias", "destinatarios_total", "destinatarios_enviados")
    linhas = mundo["conn"].execute(
        f"SELECT {', '.join(campos)} FROM alertas_cluster ORDER BY id_alerta"
    ).fetchall()
    return [dict(zip(campos, linha)) for linha in linhas]


# ---- contatos
def test_so_gestao_mexe_nos_alertas(mundo):
    c = mundo["client"]
    assert c.get("/gestao/alertas").status_code == 401
    assert c.get("/gestao/alertas/contatos", headers=H(mundo, "ana")).status_code == 403
    assert c.post("/gestao/alertas/verificar", headers=H(mundo, "ana")).status_code == 403


def test_contatos_cadastro_validacoes_e_isolamento(mundo):
    _limpar(mundo)
    r = _contato(mundo, email="Obras@Cidade1.gov.br", rotulo="  Secretaria   de Obras ")
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["destino"] == "obras@cidade1.gov.br" and corpo["rotulo"] == "Secretaria de Obras"
    assert corpo["id_area"] == mundo["a1"]  # gestor usa a própria cidade

    assert _contato(mundo, email="obras@cidade1.gov.br").status_code == 409  # repetido
    assert _contato(mundo, email="isso-nao-e-email").status_code == 422
    r = mundo["client"].post(
        "/gestao/alertas/contatos", json={"destino": "x@y.com", "canal": "whatsapp"}, headers=H(mundo, "gestor1")
    )
    assert r.status_code == 422  # WhatsApp ainda não é enviado pela API

    # gestor de outra cidade não vê nem apaga
    assert mundo["client"].get("/gestao/alertas/contatos", headers=H(mundo, "gestor2")).json() == []
    r = mundo["client"].delete(f"/gestao/alertas/contatos/{corpo['id_contato']}", headers=H(mundo, "gestor2"))
    assert r.status_code == 404
    # gestor tentando cadastrar em outra cidade: 403
    assert _contato(mundo, email="a@b.com", id_area=mundo["a2"]).status_code == 403
    # admin precisa dizer a cidade
    assert _contato(mundo, quem="admin", email="a@b.com").status_code == 422
    assert _contato(mundo, quem="admin", email="a@b.com", id_area=mundo["a2"]).status_code == 201

    r = mundo["client"].delete(f"/gestao/alertas/contatos/{corpo['id_contato']}", headers=H(mundo, "gestor1"))
    assert r.status_code == 204
    assert mundo["client"].get("/gestao/alertas/contatos", headers=H(mundo, "gestor1")).json() == []


def test_limite_de_contatos_por_cidade(mundo, monkeypatch):
    _limpar(mundo)
    monkeypatch.setattr("app.routers.alertas.settings.max_contatos_alerta_por_area", 2)
    assert _contato(mundo, email="a1@x.com").status_code == 201
    assert _contato(mundo, email="a2@x.com").status_code == 201
    assert _contato(mundo, email="a3@x.com").status_code == 422


# ---- detecção
def test_cidade_sem_contato_nao_gera_alerta(mundo):
    _limpar(mundo)
    _inserir(mundo, 4)
    r = _verificar(mundo)
    assert r["alertas"] == [] and r["areas_sem_contato"] == [mundo["a1"]]
    assert _alertas_no_banco(mundo) == []


def test_simular_mostra_mas_nao_grava_nem_envia(mundo, monkeypatch):
    _limpar(mundo)
    _contato(mundo)
    _inserir(mundo, 4)
    enviados = []
    monkeypatch.setattr(notificacoes, "enviar_email_com_resultado", lambda *a: enviados.append(a) or "enviado")
    r = _verificar(mundo, simular="true")
    assert r["simulado"] is True and len(r["alertas"]) == 1
    assert r["alertas"][0]["motivo"] == "novo" and r["alertas"][0]["status"] == "nao_enviado"
    assert r["alertas"][0]["id_alerta"] is None and r["alertas"][0]["total_ocorrencias"] == 4
    assert _alertas_no_banco(mundo) == [] and enviados == []


def test_abaixo_do_minimo_nao_e_cluster(mundo):
    _limpar(mundo)
    _contato(mundo)
    _inserir(mundo, 2)
    assert _verificar(mundo)["alertas"] == []


def test_so_conta_ocorrencia_aberta_verificada_recente_e_da_cidade(mundo):
    _limpar(mundo)
    _contato(mundo)
    _inserir(mundo, 2)                                   # 2 válidas (acessibilidade = verificada na hora)
    _inserir(mundo, 5, tipo="buraco", categoria=None)    # buraco sem confirmação da IA: não conta
    _inserir(mundo, 5, horas_atras=200)                  # fora da janela de 72 h
    _inserir(mundo, 5, status="resolvida")               # já resolvidas
    _inserir(mundo, 5, area="a2", ponto=(-23.5500, -46.6300))  # outra cidade
    assert _verificar(mundo)["alertas"] == []
    _inserir(mundo, 1, tipo="buraco", categoria=None, situacao_ia="confirmada")  # buraco confirmado conta
    r = _verificar(mundo)
    assert len(r["alertas"]) == 1 and r["alertas"][0]["total_ocorrencias"] == 3


def test_alerta_sem_smtp_fica_simulado_e_nao_repete(mundo):
    _limpar(mundo)
    _contato(mundo)
    _inserir(mundo, 3)
    r = _verificar(mundo)
    assert [a["status"] for a in r["alertas"]] == ["simulado"]
    assert _alertas_no_banco(mundo) == [
        {"status": "simulado", "nivel": "normal", "motivo": "novo", "total_ocorrencias": 3,
         "destinatarios_total": 1, "destinatarios_enviados": 1}
    ]
    assert _verificar(mundo)["alertas"] == []  # mesmo cluster: não avisa de novo


def test_subir_de_nivel_avisa_de_novo(mundo):
    _limpar(mundo)
    _contato(mundo)
    _inserir(mundo, 3)
    _verificar(mundo)
    _inserir(mundo, 2, tirar=3)  # agora 5 = nível "moderada"
    r = _verificar(mundo)
    assert [(a["motivo"], a["nivel"], a["total_ocorrencias"]) for a in r["alertas"]] == [("escalada", "moderada", 5)]
    assert _verificar(mundo)["alertas"] == []


def test_envio_de_verdade_manda_um_email_por_contato(mundo, monkeypatch):
    _limpar(mundo)
    _contato(mundo, email="obras@cidade1.gov.br")
    _contato(mundo, email="mobilidade@cidade1.gov.br")
    _inserir(mundo, 4)
    enviados = []
    monkeypatch.setattr(notificacoes, "enviar_email_com_resultado", lambda *a: enviados.append(a) or "enviado")
    r = _verificar(mundo)
    assert r["alertas"][0]["status"] == "enviado"
    assert sorted(e[0] for e in enviados) == ["mobilidade@cidade1.gov.br", "obras@cidade1.gov.br"]
    assert "4 ocorrências" in enviados[0][1] and "Cidade Um" in enviados[0][1]
    assert _alertas_no_banco(mundo)[0]["destinatarios_enviados"] == 2
    audit = mundo["conn"].execute(
        "SELECT detalhes FROM auditoria WHERE acao = 'alerta_cluster_gerado'").fetchall()
    assert len(audit) == 1 and "@" not in str(audit[0][0])  # e-mail não vai para a auditoria


def test_falha_total_nao_conta_como_avisado_e_tenta_de_novo(mundo, monkeypatch):
    _limpar(mundo)
    _contato(mundo)
    _inserir(mundo, 3)
    monkeypatch.setattr(notificacoes, "enviar_email_com_resultado", lambda *a: "falhou")
    assert _verificar(mundo)["alertas"][0]["status"] == "falhou"
    monkeypatch.setattr(notificacoes, "enviar_email_com_resultado", lambda *a: "enviado")
    r = _verificar(mundo)
    assert [a["status"] for a in r["alertas"]] == ["enviado"]  # tentou de novo e deu certo
    assert [a["status"] for a in _alertas_no_banco(mundo)] == ["falhou", "enviado"]


def test_falha_em_um_contato_marca_parcial(mundo, monkeypatch):
    _limpar(mundo)
    _contato(mundo, email="bom@cidade1.gov.br")
    _contato(mundo, email="ruim@cidade1.gov.br")
    _inserir(mundo, 3)
    monkeypatch.setattr(
        notificacoes, "enviar_email_com_resultado", lambda d, *a: "falhou" if d.startswith("ruim") else "enviado"
    )
    assert _verificar(mundo)["alertas"][0]["status"] == "parcial"
    assert _alertas_no_banco(mundo)[0]["destinatarios_enviados"] == 1
    assert _verificar(mundo)["alertas"] == []  # parcial já avisou alguém: não repete


def test_historico_paginado_e_isolado_por_cidade(mundo):
    _limpar(mundo)
    _contato(mundo)
    _inserir(mundo, 3)
    _verificar(mundo)
    r = mundo["client"].get("/gestao/alertas", headers=H(mundo, "gestor1")).json()
    assert set(r) == {"total", "limite", "deslocamento", "itens"} and r["total"] == 1
    item = r["itens"][0]
    assert item["nivel"] == "normal" and item["status"] == "simulado" and item["resumo"]["por_tipo"] == {"Acessibilidade": 3}
    assert mundo["client"].get("/gestao/alertas", headers=H(mundo, "gestor2")).json()["total"] == 0
    assert mundo["client"].get("/gestao/alertas", params={"id_area": mundo["a1"]}, headers=H(mundo, "gestor2")).status_code == 403
    assert mundo["client"].get("/gestao/alertas", params={"id_area": mundo["a1"]}, headers=H(mundo, "admin")).json()["total"] == 1


def test_gestor_nao_confere_outra_cidade_e_admin_confere_todas(mundo):
    _limpar(mundo)
    _contato(mundo)
    _contato(mundo, quem="admin", email="obras@cidade2.gov.br", id_area=mundo["a2"])
    _inserir(mundo, 3)
    _inserir(mundo, 3, area="a2", ponto=(-23.5500, -46.6300))
    r = mundo["client"].post(
        "/gestao/alertas/verificar", params={"id_area": mundo["a2"]}, headers=H(mundo, "gestor1"))
    assert r.status_code == 403
    r = _verificar(mundo, quem="admin")
    assert sorted(a["area"] for a in r["alertas"]) == ["Cidade Dois", "Cidade Um"]
