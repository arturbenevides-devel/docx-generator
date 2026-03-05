from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from docxtpl import DocxTemplate
from datetime import datetime
from typing import List
import uuid
import os
import zipfile

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
    if dia_inad in (4, 30, 45):
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


def gerar_documento_individual(item: dict, indice: int) -> tuple[str, str]:
    """Gera um DOCX para um único item do payload.
    Retorna (caminho_arquivo_tmp, nome_arquivo_final).
    """
    dia_inad = item.get("DiaInad")
    if dia_inad is None:
        raise HTTPException(400, f"Item {indice}: DiaInad não informado no payload")

    tipo_documento = determinar_tipo_documento(dia_inad)
    contexto = montar_contexto(item)
    possui_fiador = contexto["possuiFiador"]

    template_path = escolher_template(tipo_documento, possui_fiador)
    doc = DocxTemplate(template_path)
    doc.render(contexto)

    nome_pes = item.get("nome_pes", "documento")
    fiador_nome = ""
    fiadores = contexto.get("fiadores", [])
    if fiadores:
        fiador_nome = f"_fiador_{fiadores[0].get('Fiador', '')}"

    nome_final = f"{tipo_documento}_{nome_pes}{fiador_nome}.docx"
    # Limpar caracteres problemáticos do nome do arquivo
    nome_final = nome_final.replace("/", "_").replace("\\", "_")

    tmp_path = f"{TMP_FOLDER}/{uuid.uuid4()}.docx"
    doc.save(tmp_path)

    return tmp_path, nome_final


@app.post("/gerar-documento")
async def gerar_documento(data: List[dict]):
    if not data:
        raise HTTPException(400, "Payload vazio")

    # Se vier apenas 1 item, retorna o DOCX direto
    if len(data) == 1:
        tmp_path, nome_final = gerar_documento_individual(data[0], 0)
        return FileResponse(
            tmp_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=nome_final,
        )

    # Múltiplos itens: gera cada DOCX e empacota num ZIP
    arquivos_gerados = []
    nomes_usados = {}

    for i, item in enumerate(data):
        tmp_path, nome_final = gerar_documento_individual(item, i)

        # Evitar nomes duplicados no ZIP
        if nome_final in nomes_usados:
            nomes_usados[nome_final] += 1
            base, ext = os.path.splitext(nome_final)
            nome_final = f"{base}_{nomes_usados[nome_final]}{ext}"
        else:
            nomes_usados[nome_final] = 0

        arquivos_gerados.append((tmp_path, nome_final))

    zip_path = f"{TMP_FOLDER}/{uuid.uuid4()}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for tmp_path, nome_final in arquivos_gerados:
            zf.write(tmp_path, nome_final)

    # Limpar os DOCX temporários
    for tmp_path, _ in arquivos_gerados:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="documentos.zip",
    )