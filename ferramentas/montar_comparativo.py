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
import math
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


def junto_ids(juntos):
    return {x for v in juntos.values() for x in v}


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
    Medico pessoa fisica (sem CNPJ) vem marcado "pf": so entra no comparativo se casar
    com um estabelecimento da Bradesco no mesmo consultorio."""
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
            pf = len(u.get("cnpj") or "") != 14
            if pf and not u.get("end"):
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
            if pf:
                tipo = 1
            lista.append({"uf": uf, "cidade": cidade, "certo": True, "cands": [cidade], "pf": pf,
                          "rede": por_credenciado[u["cod"]] > 1, "nome": u["nome"],
                          "bairro": u.get("bairro", ""), "end": end,
                          "tel": (u.get("tel") or [""])[0], "fones": fones(u.get("tel") or []),
                          "cnpj": "" if pf else u["cnpj"], "tipo": tipo, "p": sorted(u.get("produtos") or []),
                          "tok": tokens(u["nome"]), "cep": u.get("cep", ""),
                          "xy": coordenadas(u),
                          "acred": " · ".join(SELOS_AMIL.get(x, x.upper()) for x in u.get("selos") or [])})
        out[(uf, cidade)] = lista
    return out, datas


def coordenadas(u):
    try:
        return float(u["lat"]), float(u["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def perto(p, q, metros=120):
    """Dois pontos (lat, lon) a menos de tantos metros."""
    if not p or not q:
        return False
    dy = math.radians(q[0] - p[0])
    dx = math.radians(q[1] - p[1]) * math.cos(math.radians(p[0]))
    return 6371000 * math.hypot(dx, dy) < metros


def mesmo_predio_amil(a, b):
    """Duas unidades da Amil da mesma empresa (mesma raiz de CNPJ) no mesmo lugar: o
    mesmo endereco, ou, com o mesmo CNPJ, perto (hospital, mesmo numero ou 30 m)."""
    if mesmo_endereco(a["end"], b["end"]):
        return True
    if a["cnpj"] != b["cnpj"] or not perto(a.get("xy"), b.get("xy"), 120):
        return False
    return (a["tipo"] == 0 and b["tipo"] == 0 or perto(a["xy"], b["xy"], 30)
            or _partes_endereco(a["end"])[0] == _partes_endereco(b["end"])[0] != "")


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


def juntar_empresa(linhas, juntar_marcas):
    """Junta as linhas da mesma empresa numa cidade: mesma raiz de CNPJ com nome
    parecido, ou o mesmo nome (com alguma palavra que identifica). A linha junta
    lista os enderecos, marcando o que e so de uma operadora, e soma os planos."""
    pai = list(range(len(linhas)))

    def raiz(x):
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    def une(x, y):
        pai[raiz(x)] = raiz(y)
    toks = [[tokens(n) for n in l["_n"]] for l in linhas]
    por_raiz, por_nome = {}, {}
    for k, l in enumerate(linhas):
        for c in l["_c"]:
            por_raiz.setdefault(c[:8], []).append(k)
        for t in toks[k]:
            if parecido(t, t) > 0:          # tem palavra que identifica
                por_nome.setdefault(" ".join(sorted(t)), []).append(k)
    for ks in por_nome.values():
        for k in ks[1:]:
            une(ks[0], k)
    for ks in por_raiz.values():
        for x in range(len(ks)):
            for y in range(x + 1, len(ks)):
                p, q = ks[x], ks[y]
                if raiz(p) != raiz(q) and max(parecido(t, u) for t in toks[p] for u in toks[q]) >= 0.6:
                    une(p, q)
    grupos = {}
    for k in range(len(linhas)):
        grupos.setdefault(raiz(k), []).append(linhas[k])
    out = []
    for g in grupos.values():
        if len(g) == 1:
            out.append(g[0])
            continue
        g.sort(key=lambda l: ("ab", "a", "b").index(l["_l"]))
        lados = {l["_l"] for l in g}
        so = {"ab": "", "a": " (só Amil)", "b": " (só Bradesco)"}
        ends = []
        for l in g:
            e = l["e"] + (so[l["_l"]] if len(lados) > 1 else "")
            if l["e"] and e not in ends:
                ends.append(e)
        e = " / ".join(ends[:3]) + (" e mais " + str(len(ends) - 3) + " endereços" if len(ends) > 3 else "")
        n = g[0]["n"]
        nomes_b = []
        for l in g:
            nb = l["al"] or (l["n"] if l["_l"] != "a" else "")
            if l["_l"] != "a" and nb and sem_acento(nb) != sem_acento(n) and nb not in nomes_b:
                nomes_b.append(nb)
        m = ""
        for l in g:
            if l["m"]:
                m = juntar_marcas(m, l["m"]) if m else l["m"]
        a = sorted({x for l in g for x in l["a"]})
        linha = {"n": n, "al": " · ".join(nomes_b[:2]), "t": min(l["t"] for l in g),
                 "b": next((l["b"] for l in g if l["b"]), ""), "e": e,
                 "f": next((l["f"] for l in g if l["f"]), ""), "s": next((l["s"] for l in g if l["s"]), ""),
                 "a": a, "m": m}
        o = next((l["o"] for l in g if l.get("o")), "")
        if o and not (a and m):
            linha["o"] = o
        out.append(linha)
    for l in out:
        for k in ("_c", "_n", "_l"):
            l.pop(k, None)
    return out


def trocar_pelo_mesmo_lugar(au, bu, par_a, par_b, pares):
    """Par feito so pelo CNPJ, com enderecos diferentes, quando o outro lado tem sem
    par uma unidade no mesmo endereco e com o mesmo telefone: fica o par do mesmo
    lugar. A Amil da o CNPJ da "Clinica de Olhos Novo Mundo" na Av. Victor Ferreira
    do Amaral, 58, onde a Bradesco lista a clinica como "Alto da XV" (outro CNPJ, mesmo
    telefone); a unidade "Novo Mundo" da Bradesco fica na R. Georgi Wassouf, 28."""
    # so com a Amil conferida unidade a unidade (telefone de cada unidade; na pagina
    # da Amil o telefone e o do CNPJ, igual em todos os enderecos), o mesmo tipo e algo
    # do nome em comum ("Clinica de Olhos"): o consultorio de uma medica no andar de
    # outra clinica, com o mesmo telefone, continua com o CNPJ dela
    def no_lugar(x, y):
        return (x.get("xy") and x["tipo"] == y["tipo"] and bool(x["fones"] & y["fones"])
                and (mesmo_endereco(x["end"], y["end"]) or mesmo_cep(x, y))
                and parecido(x["tok"], y["tok"]) >= 0.3)

    def so_cnpj(x, y):
        return x["cnpj"] == y["cnpj"] and not (mesmo_endereco(x["end"], y["end"]) or mesmo_cep(x, y))
    for s, i, j in pares:
        a, b = au[i], bu[j]
        ja, jb = par_a.get(i), par_b.get(j)
        if ja == j or not no_lugar(a, b):
            continue
        # Amil i casada so pelo CNPJ com outra da Bradesco, e a Bradesco j livre
        if ja is not None and jb is None and so_cnpj(a, bu[ja]):
            del par_b[ja]
            par_a[i], par_b[j] = j, i
        # Bradesco j casada so pelo CNPJ com outra da Amil, e a Amil i livre
        elif jb is not None and ja is None and so_cnpj(au[jb], b):
            del par_a[jb]
            par_a[i], par_b[j] = j, i


def nota_pf(a, b):
    """Medico pessoa fisica de um lado e a empresa dele do outro: so no mesmo
    consultorio (mesma rua, numero e, se os dois disserem, a mesma sala) e com o
    nome do medico."""
    if a.get("pf") and b.get("pf") or a["cidade"] != b["cidade"]:
        return 0.0
    if not mesmo_endereco(a["end"], b["end"]) or parecido(a["tok"], b["tok"]) < 0.8:
        return 0.0
    na, xa, _, _ = _partes_endereco(a["end"])
    nb, xb, _, _ = _partes_endereco(b["end"])
    sa, sb = xa - {na}, xb - {nb}
    if sa and sb and not sa & sb:
        return 0.0
    return 0.73 + (0.1 if a["fones"] & b["fones"] else 0)


def nota_par(a, b):
    """Quanto a unidade da Amil e a da Bradesco parecem o mesmo lugar (0 = nao sao).
    O mesmo CNPJ e o mesmo lugar, ainda que o nome mude. CNPJ diferente so casa no
    mesmo endereco (a Amil cadastra as unidades de uma rede com o CNPJ da matriz) ou
    com o mesmo telefone e nome parecido; num predio medico, o mesmo endereco com
    nome diferente e outro consultorio."""
    if a.get("pf") or b.get("pf"):
        return nota_pf(a, b)
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
        # medico pessoa fisica: so para casar com o mesmo consultorio cadastrado como
        # empresa na Amil (o "Savio Lemos Machareth" que a Amil lista com CNPJ)
        pf = p[4] == 3 and not cnpj
        if p[4] not in TIPO_BRAD and not (p[4] == 3 and (cnpj or extra[0])):
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
                   "cep": extra[4] if len(extra) > 4 else "", "pf": pf,
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
    trocar_pelo_mesmo_lugar(au, bu, par_a, par_b, pares)

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
    # o mesmo predio com dois enderecos na Amil (a esquina, a outra entrada: Hospital
    # de Olhos do Parana na Al. Pres. Taunay, 483 e na R. Cel. Dulcidio, 199): mesmo
    # CNPJ e, perto um do outro, hospital, o mesmo numero ou a menos de 30 m. Vira uma
    # linha so, a do endereco que casou com a Bradesco. Unidades de rede com o CNPJ da
    # matriz ficam a quarteiroes umas das outras; a clinica com salas em dois predios
    # da mesma rua continua com duas linhas
    mesmo_predio = {}
    for i, a in enumerate(au):
        if len(a["cnpj"]) == 14:
            mesmo_predio.setdefault((a["uf"], a["cidade"], a["cnpj"][:8]), []).append(i)
    for grupo in mesmo_predio.values():
        soltos = [i for i in grupo if i not in par_a and i not in junto_ids(junto_a)]
        for i in soltos:
            alvo = [k for k in grupo if k != i and k not in junto_ids(junto_a)
                    and mesmo_predio_amil(au[i], au[k]) and (k in par_a or k < i)]
            if alvo:
                k = min(alvo, key=lambda k: (k not in par_a, k))
                junto_a.setdefault(k, []).append(i)
    ja_juntos = junto_ids(junto_a)

    def juntar_marcas(m1, m2):
        return "".join(max(x, y, key=lambda c: (c == "1", c != "0")) for x, y in zip(m1, m2))

    # quem ficou so numa operadora mas esta na outra em outro endereco (a mesma empresa:
    # o mesmo CNPJ, ou a mesma raiz com nome parecido): a linha avisa onde, para nao
    # parecer que falta. "Medicos de Olhos" da R. Benjamin Lins (so na Amil) esta na
    # Bradesco so na R. Josepha Deren Destefani
    def por_raiz_de(lista):
        idx = {}
        for k, u in enumerate(lista):
            if len(u["cnpj"]) == 14 and not u.get("pf"):
                idx.setdefault((u["uf"], u["cnpj"][:8]), []).append(k)
        return idx
    raiz_a, raiz_b = por_raiz_de(au), por_raiz_de(bu)

    def em_outro_endereco(u, idx, lista, operadora):
        if len(u["cnpj"]) != 14:
            return ""
        outros = []
        for k in idx.get((u["uf"], u["cnpj"][:8]), []):
            o = lista[k]
            if not o["end"] or o.get("pf") or o["cidade"] == u["cidade"]:
                continue
            if o["cnpj"] == u["cnpj"] or parecido(u["tok"], o["tok"]) >= 0.6:
                onde = bonito(o["end"]) + " (" + bonito(o["cidade"]) + ")"
                if onde not in outros:
                    outros.append(onde)
        if not outros:
            return ""
        if len(outros) <= 2:
            return "na " + operadora + " só em: " + " e ".join(outros)
        return "na " + operadora + " em outras cidades: " + str(len(outros)) + " endereços"

    # linhas por cidade: a do par fica na cidade da Bradesco (a da consulta oficial)
    por_cidade = {}
    for i, a in enumerate(au):
        if i in ja_juntos or a.get("pf") and i not in par_a:
            continue
        b = bu[par_a[i]] if i in par_a else None
        cnpjs = {a["cnpj"]} | {au[x]["cnpj"] for x in junto_a.get(i, [])}
        nomes_l = [a["nome"]] + [au[x]["nome"] for x in junto_a.get(i, [])]
        if b:
            cnpjs |= {b["cnpj"]} | {bu[y]["cnpj"] for y in junto_b.get(i, [])}
            nomes_l += [b["nome"]] + [bu[y]["nome"] for y in junto_b.get(i, [])]
        if junto_a.get(i):
            prods, ends = set(a["p"]), [a["end"]]
            for x in junto_a[i]:
                prods |= set(au[x]["p"])
                e = au[x]["end"]
                if e and not any(mesmo_endereco(e, f) or sem_acento(e) == sem_acento(f) for f in ends):
                    ends.append(e)
            a = dict(a, p=sorted(prods), end=" / ".join(ends))
        if b and (junto_a.get(i) or junto_b.get(i)):
            m, nomes_b = b["m"], [b["nome"]]
            for y in junto_b.get(i, []):
                m = juntar_marcas(m, bu[y]["m"])
                nomes_b.append(bu[y]["nome"])
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
            "s": a["acred"], "a": a["p"], "m": b["m"] if b else "",
            "_c": {x for x in cnpjs if len(x) == 14}, "_n": nomes_l, "_l": "ab" if b else "a"})
        if not b:
            nota = em_outro_endereco(a, raiz_b, bu, "Bradesco")
            if nota:
                c["linhas"][-1]["o"] = nota
    for j, b in enumerate(bu):
        if j in par_b or b.get("pf"):
            continue
        chave = (b["uf"], b["cidade"])
        por_cidade.setdefault(chave, {"amil": 0, "brad": 0, "ambos": 0, "linhas": []})
        c = por_cidade[chave]
        c["brad"] += 1
        c["linhas"].append({"n": bonito(b["nome"]), "al": "", "t": b["tipo"],
                            "b": bonito(b["bairro"]), "e": bonito(b.get("end", "")),
                            "f": b.get("tel", ""), "s": "", "a": [], "m": b["m"],
                            "_c": {b["cnpj"]} if len(b["cnpj"]) == 14 else set(), "_n": [b["nome"]], "_l": "b"})
        nota = em_outro_endereco(b, raiz_a, au, "Amil")
        if nota:
            c["linhas"][-1]["o"] = nota

    # a mesma empresa em varios enderecos na cidade vira uma linha so (Medicos de
    # Olhos na R. Benjamin Lins, so na Amil, e na R. Josepha Deren Destefani, nas duas):
    # nas duas operadoras se estiver nas duas, em qualquer endereco
    for c in por_cidade.values():
        c["linhas"] = juntar_empresa(c["linhas"], juntar_marcas)
        c["amil"] = sum(1 for l in c["linhas"] if l["a"])
        c["brad"] = sum(1 for l in c["linhas"] if l["m"])
        c["ambos"] = sum(1 for l in c["linhas"] if l["a"] and l["m"])

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
