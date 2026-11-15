"""Envio de e-mail do PavimentAI.

- Se SMTP_HOST NÃO estiver no .env, esta função não faz nada (o código continua
  aparecendo no terminal da API quando AMBIENTE=dev).
- Se SMTP_HOST estiver no .env, o e-mail é enviado de verdade com verificação TLS.
- Nunca levanta erro para o usuário: se o envio falhar, registra no log da API.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("pavimentai.email")


def _enviar_smtp(destino: str, assunto: str, texto: str) -> None:
    """Monta e envia a mensagem. Levanta erro se algo falhar (quem chama decide o que fazer)."""
    if not settings.smtp_usuario or not settings.smtp_senha:
        raise RuntimeError("Defina SMTP_USUARIO e SMTP_SENHA no .env (junto com SMTP_HOST).")

    msg = EmailMessage()
    msg["From"] = settings.smtp_remetente or settings.smtp_usuario
    msg["To"] = destino
    msg["Subject"] = assunto
    msg.set_content(texto)

    contexto_tls = ssl.create_default_context()

    if settings.smtp_porta == 465:  # conexão já criptografada desde o início
        with smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_porta, timeout=15, context=contexto_tls
        ) as smtp:
            smtp.login(settings.smtp_usuario, settings.smtp_senha)
            smtp.send_message(msg)
    else:  # porta 587: começa simples e ativa STARTTLS com validação de certificado
        with smtplib.SMTP(settings.smtp_host, settings.smtp_porta, timeout=15) as smtp:
            smtp.starttls(context=contexto_tls)
            smtp.login(settings.smtp_usuario, settings.smtp_senha)
            smtp.send_message(msg)


def enviar_email_com_resultado(destino: str, assunto: str, texto: str) -> str:
    """Como enviar_email, mas diz o que aconteceu (para quem precisa registrar o resultado).

    Devolve: "enviado" (saiu pelo SMTP), "simulado" (SMTP não configurado, nada saiu)
    ou "falhou" (o SMTP recusou ou deu erro; o detalhe fica no log da API).
    """
    if not settings.smtp_host:
        return "simulado"
    try:
        _enviar_smtp(destino, assunto, texto)
    except Exception:
        log.exception("Falha ao enviar e-mail para %s", destino)
        return "falhou"
    return "enviado"


def enviar_email(destino: str, assunto: str, texto: str) -> None:
    if not settings.smtp_host:
        if settings.ambiente != "dev":
            log.warning("SMTP não configurado: o e-mail para %s não foi enviado.", destino)
        return
    enviar_email_com_resultado(destino, assunto, texto)
