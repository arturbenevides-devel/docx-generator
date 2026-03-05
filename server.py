from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from docxtpl import DocxTemplate
from datetime import datetime
from typing import List
import uuid
import os

app = FastAPI()

BASE_TEMPLATE = "templates"
TMP_FOLDER = "/tmp"

MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
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


@app.post("/gerar-documento")
async def gerar_documento(data: dict):

    dia_inad = data.get("DiaInad")
    if dia_inad is None:
        raise HTTPException(400, "DiaInad não informado no payload")

    tipo_documento = determinar_tipo_documento(dia_inad)
    contexto = montar_contexto(data)
    possui_fiador = contexto["possuiFiador"]

    template_path = escolher_template(tipo_documento, possui_fiador)
    doc = DocxTemplate(template_path)
    doc.render(contexto)

    nome_pes = data.get("nome_pes", "documento")
    filename = f"{TMP_FOLDER}/{uuid.uuid4()}.docx"
    doc.save(filename)

    return FileResponse(
        filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{tipo_documento}_{nome_pes}.docx"
    )