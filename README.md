# docx-generator

API que gera os documentos da régua de cobrança da BP8 a partir de templates Word (`.docx`):

| `DiaInad` | Documento | Template |
|---|---|---|
| `30` | Notificação extrajudicial | `templates/notificacao/` |
| `61` | Execução judicial | `templates/execucao/` |

Cada documento sai na versão **com fiador** ou **sem fiador**, conforme a lista `fiadores` do item. A resposta é sempre um `.zip`, mesmo quando só um documento é gerado.

## Rodar localmente

```bash
pip install -r requirements.txt   # versões fixadas nas que rodam em produção
uvicorn server:app --host 0.0.0.0 --port 8000
```

A documentação interativa fica em `http://localhost:8000/docs`. O serviço não usa variáveis de ambiente.

## Endpoint

### `POST /gerar-documento`

Recebe uma **lista** de itens (um documento por item) e devolve um ZIP com todos os documentos.

```bash
curl -X POST http://localhost:8000/gerar-documento \
  -H 'Content-Type: application/json' \
  -o documentos.zip \
  -d '[
    {
      "DiaInad": 30,
      "nome_pes": "MARIA DA SILVA",
      "cpf_pes": "12345678901",
      "ConcatIdentificador_unid": "2-176",
      "obra_nome": "VILLA NOVA FAZENDINHA - FASE 01",
      "obra_endereco": "Estrada Fazendinha, 2158",
      "obra_bairro": "Jardim Ana Estela",
      "obra_cidade": "Carapicuíba",
      "obra_uf": "SP",
      "obra_cep": "06364000",
      "Endereco_pend": "Rua das Flores",
      "NumEnd_pend": "100",
      "ComplEndereco_pend": "Apto 12",
      "Bairro_pend": "Centro",
      "Cidade_pend": "São Paulo",
      "UF_pend": "SP",
      "CEP_pend": "01000000",
      "fiadores": []
    }
  ]'
```

#### Resposta

- **`200`** com `Content-Type: application/zip`, arquivo `documentos.zip`.
- Cada documento dentro do ZIP se chama `{nome_pes}_{cpf_pes}.docx`.
  - `/` e `\` no nome viram `_`.
  - Nomes repetidos (mesmo cliente com mais de uma parcela) ganham sufixo: `NOME_CPF.docx`, `NOME_CPF_1.docx`, `NOME_CPF_2.docx`...
  - Os arquivos ficam no ZIP **na mesma ordem dos itens enviados**.
- Header **`X-Documentos`**: JSON com `[{ "nome", "cpf" }]` de cada documento, na mesma ordem. Acentos vêm escapados (`JO\u00c3O`).

#### Erros

| Status | Quando |
|---|---|
| `400` | Lista vazia (`Payload vazio`) |
| `400` | Item sem `DiaInad` |
| `400` | `DiaInad` diferente de `30` ou `61` |
| `500` | Arquivo de template não encontrado |

**Um item inválido derruba o lote inteiro**: nenhum documento é gerado, nem os dos itens válidos. Filtre os itens antes de chamar a API.

## Campos do payload

Todo campo enviado fica disponível no template. Os campos usados hoje pelos templates são:

**Todos os documentos**

| Campo | Conteúdo |
|---|---|
| `DiaInad` | `30` ou `61`, **como número** |
| `nome_pes` | Nome do cliente (também usado no nome do arquivo) |
| `cpf_pes` | CPF só com dígitos (também usado no nome do arquivo) |
| `ConcatIdentificador_unid` | Unidade (ex.: `2-176`) |
| `obra_nome`, `obra_cidade` | Empreendimento |
| `Endereco_pend`, `NumEnd_pend`, `Bairro_pend`, `Cidade_pend`, `UF_pend`, `CEP_pend` | Endereço do cliente |
| `fiadores` | Lista de fiadores. Vazia (ou ausente) = template **sem fiador** |

**Só na notificação (30)**

| Campo | Conteúdo |
|---|---|
| `ComplEndereco_pend` | Complemento do endereço do cliente (opcional) |
| `obra_endereco`, `obra_bairro`, `obra_uf`, `obra_cep` | Endereço do empreendimento |
| `fiadores[].Fiador`, `fiadores[].fiador_cpf`, `fiadores[].fiador_endereco`, `fiadores[].fiador_num_endereco`, `fiadores[].fiador_complemento`, `fiadores[].fiador_bairro`, `fiadores[].fiador_cidade`, `fiadores[].fiador_uf`, `fiadores[].fiador_cep` | Dados de **cada** fiador (o template repete o bloco pra cada item da lista) |

**Só na execução (61)**

| Campo | Conteúdo |
|---|---|
| `Fiador`, `fiador_cpf`, `fiador_endereco`, `fiador_num_endereco`, `fiador_bairro`, `fiador_uf`, `fiador_cep` | Dados do fiador, **no nível do item** (não dentro de `fiadores`) |

**Gerados pelo servidor** (não precisa enviar)

| Campo | Conteúdo |
|---|---|
| `hoje_extenso` | Data de hoje por extenso: `24 de Setembro de 2026` |
| `cpf_formatado` | `cpf_pes` no formato `123.456.789-01` (se tiver 11 dígitos) |
| `possuiFiador` | Calculado pelo tamanho de `fiadores`. **O valor enviado no payload é ignorado.** |

## Templates

```
templates/
├── notificacao/
│   ├── com_fiador.docx
│   └── sem_fiador.docx
└── execucao/
    ├── com_fiador.docx
    └── sem_fiador.docx
```

- **Para editar**, abra o `.docx` no Word e mantenha os marcadores `{{ campo }}` e `{% ... %}` (sintaxe [docxtpl](https://docxtpl.readthedocs.io/)).
- Os valores do payload entram no documento com escape automático (`autoescape=True`): `&`, `<` e `>` em nomes e endereços saem como texto, sem quebrar o arquivo.
- A data "São Paulo, …" (cabeçalho e bloco de assinatura da notificação) é `{{ hoje_extenso }}`, a data da geração.

## Uso no n8n

Fluxo da régua de cobrança:

1. Um Switch separa os itens por `DiaInad` (30, 61 e o resto, que não vai pra API).
2. Os itens de cada régua são agrupados numa lista e enviados numa única chamada `POST /gerar-documento`.
3. O ZIP de resposta passa por um node de descompressão. Ele devolve **um item com vários binários** (`file_0`, `file_1`, ...).
4. Um Code node separa cada binário em um item próprio (campo `data`) e liga cada documento ao item que o gerou pela regra de nome do arquivo (`{nome_pes}_{cpf_pes}.docx`, com os sufixos `_1`, `_2`). A partir daí cada documento segue pro e-mail e pro ticket do Octadesk.
