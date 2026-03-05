from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from docxtpl import DocxTemplate
from datetime import datetime
from typing import List
from dotenv import load_dotenv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import uuid
import os

load_dotenv()

app = FastAPI()

BASE_TEMPLATE = "templates"
TMP_FOLDER = "/tmp"

# SMTP config
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO", "cobranca@bp8construtora.com.br")

MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

TIPO_LABEL = {
    "notificacao": "Notificação Extrajudicial",
    "execucao": "Ação de Execução"
}


def formatar_data_extenso():
    hoje = datetime.now()
    return f"{hoje.day} de {MESES[hoje.month]} de {hoje.year}"


def formatar_cpf(cpf):
    if cpf and len(cpf) == 11:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf or ""


def determinar_tipo_documento(dia_inad):
    if dia_inad in (30, 45):
        return "notificacao"
    elif dia_inad == 61:
        return "execucao"
    else:
        raise HTTPException(400, f"DiaInad {dia_inad} não mapeado para nenhum tipo de documento")


def escolher_template(tipo_documento, possui_fiador):
    pasta = os.path.join(BASE_TEMPLATE, tipo_documento)
    if not os.path.exists(pasta):
        raise HTTPException(400, "tipo_documento inválido")

    arquivo = "com_fiador.docx" if possui_fiador else "sem_fiador.docx"
    caminho = os.path.join(pasta, arquivo)

    if not os.path.exists(caminho):
        raise HTTPException(500, "template não encontrado")

    return caminho


def montar_contexto(payload):
    contexto = payload.copy()

    fiadores = payload.get("fiadores")
    if fiadores and not isinstance(fiadores, list):
        fiadores = [fiadores]

    contexto["fiadores"] = fiadores or []
    contexto["possuiFiador"] = len(contexto["fiadores"]) > 0
    contexto["hoje_extenso"] = formatar_data_extenso()
    contexto["cpf_formatado"] = formatar_cpf(payload.get("cpf_pes", ""))

    return contexto


def enviar_email(anexos, tipo_documento):
    """Envia email com os .docx gerados em anexo."""

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_DESTINATARIO

    label = TIPO_LABEL.get(tipo_documento, tipo_documento)

    if len(anexos) == 1:
        nome = anexos[0]["nome"]
        msg["Subject"] = f"{label} - {nome}"
        corpo = f"Segue em anexo o documento de {label} referente a {nome}."
    else:
        msg["Subject"] = f"{label} - {len(anexos)} documentos"
        nomes = "\n".join([f"  • {a['nome']}" for a in anexos])
        corpo = f"Seguem em anexo {len(anexos)} documentos de {label}:\n\n{nomes}"

    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    # Anexa cada .docx
    for anexo in anexos:
        with open(anexo["arquivo"], "rb") as f:
            part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{anexo["filename"]}"')
            msg.attach(part)

    # Envia
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


@app.post("/gerar-documento")
async def gerar_documento(data: List[dict]):

    resultados = []

    for item in data:

        dia_inad = item.get("DiaInad")
        if dia_inad is None:
            raise HTTPException(400, "DiaInad não informado no payload")

        tipo_documento = determinar_tipo_documento(dia_inad)
        contexto = montar_contexto(item)
        possui_fiador = contexto["possuiFiador"]

        template_path = escolher_template(tipo_documento, possui_fiador)
        doc = DocxTemplate(template_path)
        doc.render(contexto)

        filename = f"{TMP_FOLDER}/{uuid.uuid4()}.docx"
        doc.save(filename)

        nome_pes = item.get("nome_pes", "documento")
        resultados.append({
            "nome": nome_pes,
            "tipo": tipo_documento,
            "arquivo": filename,
            "filename": f"{tipo_documento}_{nome_pes}.docx"
        })

    # Envia por email
    try:
        enviar_email(resultados, resultados[0]["tipo"])
    except Exception as e:
        raise HTTPException(500, f"Documento gerado, mas falha ao enviar email: {str(e)}")

    # Limpa arquivos temporários
    for r in resultados:
        try:
            os.remove(r["arquivo"])
        except OSError:
            pass

    return {
        "status": "sucesso",
        "mensagem": f"{len(resultados)} documento(s) gerado(s) e enviado(s) para {EMAIL_DESTINATARIO}",
        "documentos": [{"nome": r["nome"], "tipo": r["tipo"]} for r in resultados]
    }