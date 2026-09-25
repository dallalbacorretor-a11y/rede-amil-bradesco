"""Monta comparativo/dados.js: a rede da Amil e a da Bradesco lado a lado,
cidade por cidade, so estabelecimentos (medico pessoa fisica fica de fora).

Le as duas redes ja sincronizadas (amil/index.html e bradesco/index.html) e
cruza os prestadores pelo nome dentro da mesma cidade. A mesma instituicao
vem escrita de jeitos diferentes em cada operadora ("HOSPITAL E MATERNIDADE
SANTA BRIGIDA" x "HOSP MATER STA BRIGIDA"), entao o nome e normalizado:
sem acento, abreviacoes expandidas, sem "LTDA"/"S/A" e palavras de ligacao,
e comparado palavra a palavra (uma palavra casa com o comeco da outra).

Uso: python3 ferramentas/montar_comparativo.py
"""
import json
from functools import lru_cache
import re
import unicodedata
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------- leitura
def json_depois(texto, marca, fim="\n"):
    i = texto.index(marca) + len(marca)
    j = texto.index(fim, i)
    return json.loads(texto[i:j].rstrip().rstrip(";"))


def ler_amil():
    html = (RAIZ / "amil" / "index.html").read_text(encoding="utf-8")
    return json_depois(html, "window.DADOS_UF=")


def ler_bradesco():
    html = (RAIZ / "bradesco" / "index.html").read_text(encoding="utf-8")
    m = re.search(r"const DADOS = (\{.*?\});\r?\n", html, re.S)
    return json.loads(m.group(1))


# ---------------------------------------------------------- normalizacao
def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").upper()


ABREV = {
    "HOSP": "HOSPITAL", "HOSPIT": "HOSPITAL", "HOSPITALAR": "HOSPITAL",
    "STA": "SANTA", "STO": "SANTO", "SRA": "SENHORA", "SR": "SENHOR",
    "MAT": "MATERNIDADE", "MATER": "MATERNIDADE", "MATERN": "MATERNIDADE",
    "INST": "INSTITUTO", "LAB": "LABORATORIO", "LABOR": "LABORATORIO",
    "LABS": "LABORATORIO", "LABORATORIOS": "LABORATORIO",
    "CLIN": "CLINICA", "CLINIC": "CLINICA", "CLINICAS": "CLINICA", "CLINCA": "CLINICA",
    "CENT": "CENTRO", "CTR": "CENTRO", "CTO": "CENTRO",
    "DIAG": "DIAGNOSTICO", "DIAGN": "DIAGNOSTICO", "DIAGNOSTICOS": "DIAGNOSTICO",
    "ASSOC": "ASSOCIACAO", "SOC": "SOCIEDADE", "BENEF": "BENEFICENTE",
    "FUND": "FUNDACAO", "UNIV": "UNIVERSITARIO", "INF": "INFANTIL",
    "IRM": "IRMANDADE", "MISERICORD": "MISERICORDIA", "PQ": "PARQUE",
    "JD": "JARDIM", "VL": "VILA", "AV": "AVENIDA", "R": "RUA",
    "ESP": "ESPECIALIDADES", "ESPEC": "ESPECIALIDADES",
    "ODONTO": "ODONTOLOGIA", "OFTALMO": "OFTALMOLOGIA", "ORTOP": "ORTOPEDIA",
    "CARDIO": "CARDIOLOGIA", "IMAG": "IMAGEM", "RADIOL": "RADIOLOGIA",
}
LIGACAO = {"DE", "DA", "DO", "DAS", "DOS", "E", "EM", "A", "O", "AS", "OS", "EM"}
JURIDICO = {"LTDA", "SA", "ME", "EPP", "EIRELI", "SS", "SIMPLES", "LIMITADA",
            "UNIDADE", "FILIAL", "MATRIZ", "UN", "UND"}
# palavras que todo prestador tem: sozinhas nao identificam ninguem
GENERICAS = {"HOSPITAL", "CLINICA", "CENTRO", "LABORATORIO", "INSTITUTO",
             "MEDICO", "MEDICA", "MEDICINA", "MED", "SAUDE", "DIAGNOSTICO",
             "IMAGEM", "SANTA", "SANTO", "SAO", "MATERNIDADE", "ESPECIALIDADES",
             "ANALISES", "CLINICAS", "SERVICOS", "SERVICO", "ASSOCIACAO",
             "SOCIEDADE", "INTEGRADA", "INTEGRADO", "NOSSA", "SENHORA",
             "RADIOLOGIA", "ULTRASSONOGRAFIA", "SERVICOS", "GRUPO", "REDE",
             "UNIDADE", "PRONTO", "SOCORRO", "ATENDIMENTO", "DR", "DRA",
             "CURITIBA", "PARANA", "BRASIL", "SUL", "PR", "SC", "SP", "RJ",
             "MG", "RS", "BR", "PAULO", "CATARINA", "PAULISTA", "PARANAENSE",
             "CATARINENSE"}
# palavra que diz que tipo de lugar e: hospital com clinica de mesmo nome
# costuma ser outro endereco
TIPO_PALAVRA = {"HOSPITAL": "H", "MATERNIDADE": "H", "CLINICA": "C",
                "LABORATORIO": "L", "ANALISES": "L", "IMAGEM": "I",
                "RADIOLOGIA": "I", "DIAGNOSTICO": "I", "ULTRASSONOGRAFIA": "I"}


def tokens(nome):
    s = sem_acento(nome)
    s = re.sub(r"\bN\.?\s*S(RA|A)?\.?\b", " NOSSA SENHORA ", s)
    s = re.sub(r"\bS\.?\s*/\s*A\b", " SA ", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    out = []
    for t in s.split():
        t = ABREV.get(t, t)
        if t.startswith("MEDIC"):
            t = "MED"
        if t in LIGACAO or t in JURIDICO:
            continue
        if len(t) == 1 and not t.isdigit():
            continue
        out.extend(t.split())
    return out


def casa(a, b):
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    return False


def parecido(ta, tb):
    """0..1: quanto os nomes batem, olhando as palavras que identificam.
    Conta dos dois lados: "Hospital Santa Cruz" cabe inteiro em "Hospital
    Cruz Vermelha Brasileira", mas sobram duas palavras do outro lado."""
    if not ta or not tb:
        return 0.0
    da = [a for a in ta if a not in GENERICAS]
    db = [b for b in tb if b not in GENERICAS]
    if not da and not db:
        # so palavras genericas ("Maternidade Curitiba"): tem de ser igual
        return 1.0 if sorted(ta) == sorted(tb) else 0.0
    usados, iguais, distintivas = set(), 0, 0
    for a in ta:
        for j, b in enumerate(tb):
            if j not in usados and casa(a, b):
                usados.add(j)
                iguais += 1
                if a not in GENERICAS and b not in GENERICAS:
                    distintivas += 1
                break
    if not distintivas:
        return 0.0
    s = (0.45 * distintivas / max(1, min(len(da), len(db))) +
         0.35 * distintivas / max(1, max(len(da), len(db))) +
         0.20 * iguais / max(len(ta), len(tb)))
    ka = {TIPO_PALAVRA[t] for t in ta if t in TIPO_PALAVRA}
    kb = {TIPO_PALAVRA[t] for t in tb if t in TIPO_PALAVRA}
    if ka and kb and not (ka & kb):
        s -= 0.15
    return s


@lru_cache(maxsize=None)
def _partes_endereco(e):
    pedacos = [x.strip() for x in sem_acento(e).split(",")]
    rua = re.split(r"\s+-\s+", pedacos[0])[0]
    # rodovia: "ROD BR-116" e "RODOVIA BR 116" -> BR116
    rua = re.sub(r"\b([A-Z]{2})\s*-?\s*(\d{2,3})\b", r"\1\2", rua)
    nums = re.findall(r"\d+", pedacos[1]) if len(pedacos) > 1 else []
    extra = {n.lstrip("0") for x in pedacos[1:] for n in re.findall(r"\d{3,}", x)}
    palavras = [t for t in re.split(r"[^A-Z0-9]+", rua)
                if len(t) >= 3 and t not in LIGACAO and not t.isdigit()]
    return (nums[0].lstrip("0") if nums else ""), extra, (palavras[-1] if palavras else ""), frozenset(palavras)


def mesmo_endereco(a, b):
    """Mesmo numero e mesma rua. O numero pode vir repetido no complemento, com a
    faixa do predio ("7907, 7911/8 e 9" e o mesmo predio que "7911 LJ 09"). A Bradesco
    escreve faixas de numeracao na rua ("R X - ATE 2209/2210"), ignoradas aqui, e as
    vezes o bairro colado ao nome da rua ("AV REPUBLICA ARGENTINA AGUA VERDE")."""
    if not a or not b:
        return False
    na, xa, ra, pa = _partes_endereco(a)
    nb, xb, rb, pb = _partes_endereco(b)
    if not (na and nb and ra and rb and (ra == rb or mesma_rua(pa, pb))):
        return False
    return na == nb or (len(na) >= 3 and na in xb) or (len(nb) >= 3 and nb in xa)


TIPO_RUA = {"RUA", "AVENIDA", "AVE", "TRAVESSA", "ALAMEDA", "ROD", "RODOVIA", "PRACA",
            "ESTRADA", "EST", "LARGO", "VIA", "VIELA", "BECO", "LADEIRA", "TRV", "ALM"}


def mesma_rua(pa, pb):
    """Todas as palavras da rua mais curta (sem "RUA", "AVENIDA") estao na outra:
    "REPUBLICA ARGENTINA" e "REPUBLICA ARGENTINA AGUA VERDE", mas nao "SAO PAULO" e
    "PAULO GORSKI"."""
    pa, pb = pa - TIPO_RUA, pb - TIPO_RUA
    curta, longa = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    return bool(curta) and max(map(len, curta)) >= 4 and all(any(casa(x, y) for y in longa) for x in curta)


def mesmo_cep(a, b):
    """Mesmo CEP e mesmo numero: o mesmo lugar, ainda que a rua venha escrita de
    outro jeito (abreviada, com o nome antigo)."""
    if not (len(a.get("cep") or "") == 8 and a.get("cep") == b.get("cep")):
        return False
    na, xa, _, _ = _partes_endereco(a["end"] or "")
    nb, xb, _, _ = _partes_endereco(b["end"] or "")
    return bool(na and nb) and (na == nb or (len(na) >= 3 and na in xb) or (len(nb) >= 3 and nb in xa))


def periodo(datas):
    """{'24/09/2026', '25/09/2026'} -> '24/09/2026 a 25/09/2026'"""
    ds = sorted(datas, key=lambda d: d.split("/")[::-1])
    return "" if not ds else ds[0] if len(ds) == 1 else ds[0] + " a " + ds[-1]


def fones(textos):
    """Telefones so com os digitos que identificam: DDD + numero."""
    out = set()
    for t in textos:
        for x in re.split(r"[·|/]", t or ""):
            d = re.sub(r"\D", "", x)
            if len(d) >= 10:
                out.add(d[-10:])
            elif len(d) >= 8:
                out.add(d[-8:])
    return out


def chave_bairro(b):
    return re.sub(r"[^A-Z]", "", sem_acento(b or ""))


def unidades_amil(d, uf):
    """Uma unidade por endereco. A cidade de cada endereco vem da lista de cidades
    reais quando ela acompanha os enderecos; quando nao acompanha (uma rede em varias
    cidades), sai do bairro, aprendido dos registros em que endereco e cidade vem
    juntos. Sem jeito de saber, a unidade fica "incerta" e pode casar em qualquer
    das cidades do registro."""
    regs = [p for p in d["prestadores"] if len(re.sub(r"\D", "", p.get("c") or "")) == 14]
    bairro_cidade = {}
    for p in regs:
        es, cr, bs = p.get("e") or [], p.get("cr") or [], p.get("b") or []
        if len(es) == len(cr) == len(bs):
            for b, c in zip(bs, cr):
                cont = bairro_cidade.setdefault(chave_bairro(b), {})
                cont[sem_acento(c)] = cont.get(sem_acento(c), 0) + 1
    out = []
    for p in regs:
        es = p.get("e") or [""]
        cr = [sem_acento(c) for c in (p.get("cr") or p.get("cid") or [])]
        if not cr:
            continue
        bs, ts = p.get("b") or [""], p.get("t") or [""]
        pp = p.get("pp") or {}
        pp = {sem_acento(k): v for k, v in pp.items()}
        for k, e in enumerate(es):
            b = bs[k] if len(bs) == len(es) else (bs[0] if len(bs) == 1 else "")
            if len(cr) == len(es):
                cidade, certo = cr[k], True
            elif len(cr) == 1:
                cidade, certo = cr[0], True
            else:
                opc = bairro_cidade.get(chave_bairro(b), {})
                opc = sorted((c for c in opc if c in cr), key=lambda c: -opc[c])
                cidade, certo = (opc[0], True) if opc else (cr[0], False)
            out.append({"uf": uf, "cidade": cidade, "certo": certo, "cands": cr, "rede": len(es) > 1,
                        "nome": p["n"], "bairro": b, "end": e,
                        "tel": ts[k] if len(ts) == len(es) else ts[0],
                        "fones": fones(p.get("t") or []),
                        "cnpj": re.sub(r"\D", "", p["c"]), "tipo": tipo_amil(p),
                        "p": sorted(set(pp.get(cidade) or p.get("p") or [])),
                        "pp": {c: sorted(set(v)) for c, v in pp.items()},
                        "tok": tokens(p["n"]), "acred": " · ".join(p.get("s") or [])})
    return out


SELOS_AMIL = {"a": "ACRED", "e": "TE", "p": "ESP", "r": "RES", "d": "DOUT", "q": "Q", "i": "ISO",
              "n": "N", "g": "G"}


def unidades_amil_coletadas():
    """({(uf, cidade): [unidades]}, {(uf, cidade): data}) de ferramentas/amil/<UF>/<CIDADE>.json.
    So quem tem CNPJ (medico pessoa fisica fica de fora, como na Bradesco)."""
    out, datas = {}, {}
    for arq in sorted((RAIZ / "ferramentas" / "amil").glob("*/*.json")):
        d = json.loads(arq.read_text(encoding="utf-8"))
        uf, cidade = d["uf"], sem_acento(d["cidade"])
        datas[(uf, cidade)] = "/".join(reversed(d["data"].split("-")))
        lista = []
        por_credenciado = {}
        for u in d["unidades"]:
            por_credenciado[u["cod"]] = por_credenciado.get(u["cod"], 0) + 1
        for u in d["unidades"]:
            if len(u.get("cnpj") or "") != 14:
                continue
            tipos = set(u.get("tipos") or [])
            esp = " ".join(sem_acento(e) for es in (u.get("esp") or {}).values() for e in es)
            if tipos & {"HOSPITAIS PARA INTERNACAO", "PRONTO-SOCORRO 24H (URGENCIA E EMERGENCIA)",
                        "PRONTO ATENDIMENTO - HORARIO COMERCIAL"}:
                tipo = 0
            elif tipos == {"LABORATORIOS E EXAMES"}:
                tipo = 3 if IMAGEM_ESP.search(esp) and not LAB_ESP.search(esp) else 2
            else:
                tipo = 1
            end = u["end"] + (" " + u["compl"] if u.get("compl") else "")
            lista.append({"uf": uf, "cidade": cidade, "certo": True, "cands": [cidade],
                          "rede": por_credenciado[u["cod"]] > 1, "nome": u["nome"],
                          "bairro": u.get("bairro", ""), "end": end,
                          "tel": (u.get("tel") or [""])[0], "fones": fones(u.get("tel") or []),
                          "cnpj": u["cnpj"], "tipo": tipo, "p": sorted(u.get("produtos") or []),
                          "tok": tokens(u["nome"]), "cep": u.get("cep", ""),
                          "acred": " · ".join(SELOS_AMIL.get(x, x.upper()) for x in u.get("selos") or [])})
        out[(uf, cidade)] = lista
    return out, datas


def chave_endereco(end):
    """(numero, rua) para dizer que dois enderecos sao o mesmo; None sem numero."""
    pedacos = [x.strip() for x in sem_acento(end or "").split(",")]
    num = re.findall(r"\d+", pedacos[1]) if len(pedacos) > 1 else []
    rua = chave_rua(end)
    return (num[0], rua) if num and rua else None


def chave_rua(end):
    """A palavra que identifica a rua: 'AVENIDA MANOEL RIBAS, 5875' -> 'RIBAS'."""
    rua = re.split(r"\s+-\s+", sem_acento((end or "").split(",")[0]))[0]
    palavras = [t for t in re.split(r"[^A-Z0-9]+", rua)
                if len(t) >= 3 and t not in LIGACAO and not t.isdigit()]
    return palavras[-1] if palavras else ""


def resolver_cidades(au, bu):
    """Unidade da Amil sem cidade certa (rede sem bairro): a cidade sai da rua, pelos
    enderecos de cidade conhecida (Bradesco e Amil), entre as cidades do registro."""
    ruas = {}
    for u in bu + [u for u in au if u["certo"]]:
        k = (u["uf"], chave_rua(u["end"]))
        if k[1]:
            ruas.setdefault(k, {}).setdefault(u["cidade"], 0)
            ruas[k][u["cidade"]] += 1
    for u in au:
        if u["certo"]:
            continue
        opc = {c: n for c, n in ruas.get((u["uf"], chave_rua(u["end"])), {}).items() if c in u["cands"]}
        if opc:
            ordem = sorted(opc, key=lambda c: -opc[c])
            u["cidade"] = ordem[0]
            u["certo"] = len(ordem) == 1 or opc[ordem[0]] > opc[ordem[1]]
            u["p"] = u["pp"].get(u["cidade"]) or u["p"]


def nota_par(a, b):
    """Quanto a unidade da Amil e a da Bradesco parecem o mesmo lugar (0 = nao sao).
    O mesmo CNPJ e o mesmo lugar, ainda que o nome mude. CNPJ diferente so casa no
    mesmo endereco (a Amil cadastra as unidades de uma rede com o CNPJ da matriz) ou
    com o mesmo telefone e nome parecido; num predio medico, o mesmo endereco com
    nome diferente e outro consultorio."""
    mesmo_cnpj = bool(a["cnpj"] and a["cnpj"] == b["cnpj"])
    mesma_raiz = bool(a["cnpj"] and b["cnpj"] and a["cnpj"][:8] == b["cnpj"][:8])
    mesmo_end = mesmo_endereco(a["end"], b["end"]) or mesmo_cep(a, b)
    mesmo_fone = bool(a["fones"] & b["fones"])
    nome = parecido(a["tok"], b["tok"])
    # a mesma unidade de rede com o numero diferente de um lado (a esquina, a outra
    # entrada): mesmo nome, mesma empresa ou telefone e o mesmo CEP de trecho de rua
    # (CEP terminado em 000 e o da cidade ou da avenida inteira e nao conta)
    mesma_quadra = bool(not mesmo_end and len(a.get("cep") or "") == 8 and a["cep"] == b.get("cep")
                        and not a["cep"].endswith("000") and nome >= 0.9 and (mesma_raiz or mesmo_fone))
    # rede com varias unidades: o telefone e a central e, na Amil, o CNPJ costuma ser o
    # da matriz para todas; a unidade so e a mesma no mesmo endereco. Excecoes pelo
    # CNPJ exato: o hospital de esquina com dois enderecos na Amil (Bradesco com uma
    # unidade so) e a unidade da Amil com o CNPJ da filial que a Bradesco lista.
    if not (mesmo_end or mesma_quadra):
        if a.get("rede") and not (mesmo_cnpj and not b.get("rede")):
            return 0.0
        if b.get("rede") and not a.get("rede") and not mesmo_cnpj:
            return 0.0
    if a["cnpj"] and b["cnpj"] and not mesmo_cnpj:
        if not (mesmo_end or mesma_quadra) and not (mesmo_fone and nome > 0.5):
            return 0.0
        if not mesma_raiz and not mesmo_fone and nome < 0.4:
            return 0.0
    # outra cidade: so a mesma unidade cadastrada na cidade vizinha
    if a["cidade"] != b["cidade"] and not (not a["certo"] and b["cidade"] in a["cands"]):
        if not (mesmo_end and (mesmo_cnpj or mesma_raiz or mesmo_fone or nome >= 0.8)):
            return 0.0
    s = nome
    if mesmo_cnpj:
        s += 0.8
    if mesmo_end:
        s += 0.5
    elif mesma_quadra:
        s += 0.3
    if mesmo_fone:
        s += 0.3
    if a["bairro"] and b["bairro"] and chave_bairro(a["bairro"])[:4] == chave_bairro(b["bairro"])[:4]:
        s += 0.1
    s += 0.05 if a["tipo"] == b["tipo"] else -0.1
    return s


# --------------------------------------------------------------- tipos
IMAGEM_ESP = re.compile(r"RESSONAN|TOMOGRAF|ULTRASS|ULTRA-SS|RAIO|RADIOLOG|MAMOGRAF|"
                        r"DENSITOMET|IMAGEM|ECOGRAF|DOPPLER|MEDICINA NUCLEAR|PET|"
                        r"CINTILOGRAF|ECOCARDIO")
LAB_ESP = re.compile(r"ANALISES CLINICAS|PATOLOGIA|LABORATOR|CITOPATOLOG|"
                     r"ANATOMIA PATOLOG|GENETIC")
TIPOS = ["Hospitais", "Clínicas", "Laboratórios", "Centros de imagem"]
# tipos da Bradesco: 0 clinica, 1 hospital, 2 laboratorio, 3 medico, 4 imagem
TIPO_BRAD = {0: 1, 1: 0, 2: 2, 4: 3}


def tipo_amil(p):
    cats = set(p.get("cats") or [p.get("cat")])
    if cats & {"Hospitais", "Pronto-socorro 24h", "Pronto atendimento"}:
        return 0
    if "Laboratorios e imagem" in cats and p.get("cat") == "Laboratorios e imagem":
        esp = " ".join(sem_acento(e) for e in (p.get("pc") or {}).get(
            "Laboratorios e imagem", p.get("esp") or []))
        img, lab = bool(IMAGEM_ESP.search(esp)), bool(LAB_ESP.search(esp))
        return 3 if img and not lab else 2
    return 1


def bonito(t):
    """Nome em caixa de texto; siglas curtas ficam em caixa alta."""
    miudas = {"DA", "DAS", "DE", "DO", "DOS", "E", "EM"}
    out = []
    for i, w in enumerate((t or "").split()):
        if len(w) <= 3 and not re.search(r"[AEIOU]", w):
            out.append(w)
        elif i and w in miudas:
            out.append(w.lower())
        else:
            out.append(w[:1] + w[1:].lower())
    return " ".join(out)


# ------------------------------------------------------------ montagem
def montar():
    A = ler_amil()
    B = ler_bradesco()

    # produtos da Bradesco como aparecem na tela (5 grupos)
    grupos = B.get("grupos") or [{"rot": p, "bits": [i], "sub": None}
                                 for i, p in enumerate(B["planos"])]
    cores_b = ["#a3123c", "#b0552a", "#1d5089", "#0e6b64", "#6b3fa0"]

    def marcas_brad(mask):
        out = ""
        for g in grupos:
            on = [b for b in g["bits"] if (mask >> b) & 1]
            if not on:
                out += "0"
            elif len(on) == len(g["bits"]) or not g.get("sub"):
                out += "1"
            else:
                out += str(2 + g["bits"].index(on[0]))   # 2 = so enf, 3 = so apto
        return out

    # Bradesco: uma unidade por prestador (estabelecimentos e medico com CNPJ, que a
    # Amil tambem lista). Nas cidades da consulta oficial o 8o campo traz
    # [endereco, telefones, "", cnpj]; quem esta marcado "fora da busca oficial"
    # (estava na base antiga e nao aparece na consulta) nao entra.
    uf_b, cid_b, bai_b, nom_b = B["uf"], B["cid"], B["bai"], B["nom"]
    bu, datas_b = [], set()
    for p in B["pr"]:
        uf, cidade = uf_b[cid_b[p[1]][0]], sem_acento(cid_b[p[1]][1])
        if uf not in A or (len(p) > 6 and p[6] and p[6][2] == 2):
            continue
        extra = p[7] if len(p) > 7 and p[7] else ["", ""]
        cnpj = extra[3] if len(extra) > 3 else ""
        if p[4] not in TIPO_BRAD and not (p[4] == 3 and cnpj):
            continue
        data = (B.get("consulta") or {}).get(str(p[1]))
        if data:
            datas_b.add(data)
        mask = 0
        for k in range(1, len(p[5]), 2):
            mask |= p[5][k]
        bu.append({"uf": uf, "cidade": cidade, "nome": nom_b[p[0]],
                   "bairro": bai_b[p[2]] if p[2] is not None and p[2] >= 0 else "",
                   "end": extra[0] or "", "tel": (extra[1] or "").split(" · ")[0],
                   "fones": fones([extra[1]]), "cnpj": cnpj, "tipo": TIPO_BRAD.get(p[4], 1),
                   "cep": extra[4] if len(extra) > 4 else "",
                   "m": marcas_brad(mask), "tok": tokens(nom_b[p[0]])})

    # Amil: nas cidades coletadas unidade a unidade na busca avancada (coletar_amil.py),
    # as unidades de la, cada uma com os produtos dela. Nas outras, a pagina da Amil:
    # um registro por CNPJ pode ter varios enderecos (uma rede de laboratorios com 31
    # unidades); cada endereco vira uma unidade, na cidade dele
    coletadas, datas_a = unidades_amil_coletadas()
    au = [u for uf in A for u in unidades_amil(A[uf], uf)]
    resolver_cidades(au, bu)
    au = [u for u in au if (u["uf"], u["cidade"]) not in coletadas]
    for lista in coletadas.values():
        au += lista
    # rede com varias unidades (do lado da Bradesco: varias unidades com a mesma raiz
    # de CNPJ no estado): unidade so casa com unidade no mesmo endereco
    raizes = {}
    for b in bu:
        if b["cnpj"]:
            raizes[(b["uf"], b["cnpj"][:8])] = raizes.get((b["uf"], b["cnpj"][:8]), 0) + 1
    for b in bu:
        b["rede"] = raizes.get((b["uf"], b["cnpj"][:8]), 0) > 1 if b["cnpj"] else False

    # candidatos: a mesma cidade; as cidades possiveis de quem a Amil nao diz onde
    # fica; e, em qualquer cidade do estado, o mesmo CNPJ, raiz de CNPJ ou telefone
    # (a mesma unidade cadastrada numa cidade vizinha)
    por_cid, por_cnpj, por_raiz, por_fone = {}, {}, {}, {}
    for j, b in enumerate(bu):
        por_cid.setdefault((b["uf"], b["cidade"]), []).append(j)
        if b["cnpj"]:
            por_cnpj.setdefault(b["cnpj"], []).append(j)
            por_raiz.setdefault((b["uf"], b["cnpj"][:8]), []).append(j)
        for f in b["fones"]:
            por_fone.setdefault((b["uf"], f), []).append(j)
    pares = []
    for i, a in enumerate(au):
        cands = set(por_cid.get((a["uf"], a["cidade"]), []))
        if not a["certo"]:
            for c in a["cands"]:
                cands.update(por_cid.get((a["uf"], c), []))
        cands.update(j for j in por_cnpj.get(a["cnpj"], []) if bu[j]["uf"] == a["uf"])
        cands.update(por_raiz.get((a["uf"], a["cnpj"][:8]), []))
        for f in a["fones"]:
            cands.update(por_fone.get((a["uf"], f), []))
        for j in cands:
            s = nota_par(a, bu[j])
            if s >= 0.72:
                pares.append((s, i, j))
    # um para um, melhor evidencia primeiro
    pares.sort(key=lambda x: -x[0])
    par_a, par_b = {}, {}
    for s, i, j in pares:
        if i not in par_a and j not in par_b:
            par_a[i], par_b[j] = j, i

    # hospital repetido do mesmo lado no mesmo endereco (a mantenedora e o hospital:
    # "Liga Paranaense de Combate ao Cancer" e o Erasto Gaertner; o "Hospital Espirita
    # de Psiquiatria" e o Uniica Bom Retiro): entra na linha do hospital ja casado
    hosp_par = {}
    for i, j in par_a.items():
        a, b = au[i], bu[j]
        if a["tipo"] == 0 and b["tipo"] == 0 and chave_endereco(a["end"]):
            hosp_par.setdefault((a["uf"], chave_endereco(a["end"])), i)
            hosp_par.setdefault((b["uf"], chave_endereco(b["end"])), i)
    junto_a, junto_b = {}, {}
    for i, a in enumerate(au):
        k = (a["uf"], chave_endereco(a["end"]))
        if i not in par_a and a["tipo"] == 0 and k in hosp_par:
            junto_a.setdefault(hosp_par[k], []).append(i)
    for j, b in enumerate(bu):
        k = (b["uf"], chave_endereco(b["end"]))
        if j not in par_b and b["tipo"] == 0 and k in hosp_par:
            junto_b.setdefault(hosp_par[k], []).append(j)
            par_b[j] = hosp_par[k]
    ja_juntos = {x for v in junto_a.values() for x in v}

    def juntar_marcas(m1, m2):
        return "".join(max(x, y, key=lambda c: (c == "1", c != "0")) for x, y in zip(m1, m2))

    # linhas por cidade: a do par fica na cidade da Bradesco (a da consulta oficial)
    por_cidade = {}
    for i, a in enumerate(au):
        if i in ja_juntos:
            continue
        b = bu[par_a[i]] if i in par_a else None
        if b and (junto_a.get(i) or junto_b.get(i)):
            prods = set(a["p"])
            for x in junto_a.get(i, []):
                prods |= set(au[x]["p"])
            m, nomes_b = b["m"], [b["nome"]]
            for y in junto_b.get(i, []):
                m = juntar_marcas(m, bu[y]["m"])
                nomes_b.append(bu[y]["nome"])
            a = dict(a, p=sorted(prods))
            nomes_b = [n for n in nomes_b if sem_acento(n) != sem_acento(a["nome"])] or [a["nome"]]
            b = dict(b, m=m, nome=" · ".join(nomes_b))
        chave = (b["uf"], b["cidade"]) if b else (a["uf"], a["cidade"])
        por_cidade.setdefault(chave, {"amil": 0, "brad": 0, "ambos": 0, "linhas": []})
        c = por_cidade[chave]
        c["amil"] += 1
        if b:
            c["brad"] += 1
            c["ambos"] += 1
        c["linhas"].append({
            "n": bonito(a["nome"]), "al": bonito(b["nome"]) if b and
                 sem_acento(b["nome"]) != sem_acento(a["nome"]) else "",
            "t": b["tipo"] if b else a["tipo"], "b": bonito(a["bairro"] or (b or {}).get("bairro", "")),
            "e": bonito(a["end"] or (b or {}).get("end", "")), "f": a["tel"] or (b or {}).get("tel", ""),
            "s": a["acred"], "a": a["p"], "m": b["m"] if b else ""})
    for j, b in enumerate(bu):
        if j in par_b:
            continue
        chave = (b["uf"], b["cidade"])
        por_cidade.setdefault(chave, {"amil": 0, "brad": 0, "ambos": 0, "linhas": []})
        c = por_cidade[chave]
        c["brad"] += 1
        c["linhas"].append({"n": bonito(b["nome"]), "al": "", "t": b["tipo"],
                            "b": bonito(b["bairro"]), "e": bonito(b.get("end", "")),
                            "f": b.get("tel", ""), "s": "", "a": [], "m": b["m"]})

    cidades, linhas_por_cidade, casados_total = [], {}, 0
    for (uf, cidade), c in sorted(por_cidade.items()):
        if not c["amil"] or not c["brad"]:
            continue                      # so interessa onde as duas operadoras tem rede
        c["linhas"].sort(key=lambda l: (l["t"], sem_acento(l["n"])))
        casados_total += c["ambos"]
        chave_txt = uf + "|" + cidade
        linhas_por_cidade[chave_txt] = c["linhas"]
        cidades.append({"k": chave_txt, "uf": uf, "nome": bonito(cidade),
                        "amil": c["amil"], "brad": c["brad"], "ambos": c["ambos"]})

    produtos_amil = {uf: [{"c": p["codigo"], "r": (p["rotulo"] + " " + (p.get("acomodacao") or "")).strip(),
                           "l": p["linha"], "cor": p.get("cor") or "#2733c4"}
                          for p in d["produtos"]] for uf, d in A.items()}
    dados = {
        "gerado": date.today().strftime("%d/%m/%Y"),
        "baseAmil": {uf: d.get("gerado_em", "") for uf, d in A.items()},
        # cidades conferidas unidade a unidade na busca avancada (coletar_amil.py)
        "baseAmilCid": {uf + "|" + c: dt for (uf, c), dt in datas_a.items()},
        # consulta oficial de rede referenciada (dia ou periodo); sem ela, a base do buscador
        "baseBradesco": periodo(datas_b) or B.get("ref", ""),
        "fonteBradesco": "consulta" if datas_b else "buscador",
        "tipos": TIPOS,
        "amil": produtos_amil,
        "bradesco": [{"r": g["rot"], "cor": cores_b[i % len(cores_b)],
                      "sub": g.get("sub")} for i, g in enumerate(grupos)],
        "cidades": sorted(cidades, key=lambda c: -(c["amil"] + c["brad"])),
        "rede": linhas_por_cidade,
    }
    destino = RAIZ / "comparativo" / "dados.js"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text("/* gerado por ferramentas/montar_comparativo.py - nao editar */\n"
                       "window.COMPARATIVO=" + json.dumps(dados, ensure_ascii=False,
                                                          separators=(",", ":")) + ";\n",
                       encoding="utf-8")
    print(f"{len(cidades)} cidades, {casados_total} prestadores nas duas redes, "
          f"{destino.stat().st_size // 1024} KB")
    return dados


if __name__ == "__main__":
    montar()
