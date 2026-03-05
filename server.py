from fastapi import FastAPI
from fastapi.responses import FileResponse
from docxtpl import DocxTemplate
import uuid
import os

app = FastAPI()

TEMPLATE_PATH = "execucao_template.docx"

@app.post("/gerar-docx")
async def gerar_docx(data: dict):

    doc = DocxTemplate(TEMPLATE_PATH)

    contexto = {
        "nome": data.get("nome_pes"),
        "cpf": data.get("cpf_pes"),
        "endereco": data.get("Endereco_pend"),
        "numero": data.get("NumEnd_pend"),
        "bairro": data.get("Bairro_pend"),
        "cidade": data.get("Cidade_pend"),
        "uf": data.get("UF_pend"),
        "cep": data.get("CEP_pend"),
        "obra_nome": data.get("obra_nome"),
        "valor_parcela": data.get("ValorPar_Rea"),
        "data": data.get("hoje")
    }

    doc.render(contexto)

    filename = f"/tmp/{uuid.uuid4()}.docx"
    doc.save(filename)

    return FileResponse(
        filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="execucao_judicial.docx"
    )
