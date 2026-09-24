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

    # Bradesco por cidade (so estabelecimentos)
    uf_b, cid_b, bai_b, nom_b = B["uf"], B["cid"], B["bai"], B["nom"]
    brad = {}
    for p in B["pr"]:
        tipo = p[4]
        if tipo not in TIPO_BRAD:
            continue
        uf, cidade = uf_b[cid_b[p[1]][0]], sem_acento(cid_b[p[1]][1])
        if uf not in A:
            continue
        mask = 0
        e = p[5]
        for k in range(1, len(e), 2):
            mask |= e[k]
        brad.setdefault((uf, cidade), []).append({
            "nome": nom_b[p[0]], "bairro": bai_b[p[2]] if p[2] is not None and p[2] >= 0 else "",
            "tipo": TIPO_BRAD[tipo], "m": marcas_brad(mask), "tok": tokens(nom_b[p[0]])})

    # Amil por cidade onde o prestador fica
    amil = {}
    for uf, d in A.items():
        for p in d["prestadores"]:
            if len(re.sub(r"\D", "", p.get("c") or "")) != 14:
                continue                      # sem CNPJ: medico pessoa fisica
            cidades = p.get("cr") or p.get("cid") or []
            if not cidades:
                continue
            cidade = sem_acento(cidades[0])
            pp = p.get("pp") or {}
            prods = sorted(set(pp.get(cidades[0]) or p.get("p") or []))
            amil.setdefault((uf, cidade), []).append({
                "nome": p["n"], "bairro": (p.get("b") or [""])[0],
                "end": (p.get("e") or [""])[0], "tel": (p.get("t") or [""])[0],
                "tipo": tipo_amil(p), "p": prods, "tok": tokens(p["n"]),
                "acred": " · ".join(p.get("s") or [])})

    cidades, linhas_por_cidade, casados_total = [], {}, 0
    for chave in sorted(amil):
        uf, cidade = chave
        la, lb = amil[chave], brad.get(chave, [])
        if not lb:
            continue
        # pares candidatos, melhor primeiro
        pares = []
        for i, a in enumerate(la):
            for j, b in enumerate(lb):
                s = parecido(a["tok"], b["tok"])
                if s <= 0:
                    continue
                s += 0.05 if a["tipo"] == b["tipo"] else -0.1
                if a["bairro"] and b["bairro"] and \
                   sem_acento(a["bairro"])[:4] == sem_acento(b["bairro"])[:4]:
                    s += 0.1
                if s >= 0.72:
                    pares.append((s, i, j))
        pares.sort(reverse=True)
        par_a, par_b, extra_b = {}, {}, {}
        for s, i, j in pares:
            if i in par_a and j in par_b:
                continue
            if i not in par_a and j not in par_b:
                par_a[i] = j
                par_b[j] = i
            elif s >= 0.9:
                # outra unidade da mesma instituicao, de um lado ou do outro:
                # junta na linha que ja existe em vez de aparecer como exclusiva
                if i not in par_a:
                    par_a[i] = j
                else:
                    extra_b.setdefault(par_a[i], []).append(j)
                    par_b[j] = i
        linhas = []
        def juntar_marcas(m1, m2):
            return "".join(max(x, y, key=lambda c: (c == "1", c != "0"))
                           for x, y in zip(m1, m2))
        for i, a in enumerate(la):
            b = lb[par_a[i]] if i in par_a else None
            if b:
                m = b["m"]
                for j in extra_b.get(i, []):
                    m = juntar_marcas(m, lb[j]["m"])
                b = dict(b, m=m)
            linhas.append({
                "n": bonito(a["nome"]), "al": bonito(b["nome"]) if b and
                     sem_acento(b["nome"]) != sem_acento(a["nome"]) else "",
                "t": b["tipo"] if b else a["tipo"], "b": bonito(a["bairro"] or (b or {}).get("bairro", "")),
                "e": bonito(a["end"]), "f": a["tel"], "s": a["acred"],
                "a": a["p"], "m": b["m"] if b else ""})
        for j, b in enumerate(lb):
            if j in par_b:
                continue
            linhas.append({"n": bonito(b["nome"]), "al": "", "t": b["tipo"],
                           "b": bonito(b["bairro"]), "e": "", "f": "", "s": "",
                           "a": [], "m": b["m"]})
        linhas.sort(key=lambda l: (l["t"], sem_acento(l["n"])))
        casados = len(set(par_a))
        casados_total += casados
        chave_txt = uf + "|" + cidade
        linhas_por_cidade[chave_txt] = linhas
        cidades.append({"k": chave_txt, "uf": uf, "nome": bonito(cidade),
                        "amil": len(la), "brad": len(lb), "ambos": casados})

    produtos_amil = {uf: [{"c": p["codigo"], "r": (p["rotulo"] + " " + (p.get("acomodacao") or "")).strip(),
                           "l": p["linha"], "cor": p.get("cor") or "#2733c4"}
                          for p in d["produtos"]] for uf, d in A.items()}
    dados = {
        "gerado": date.today().strftime("%d/%m/%Y"),
        "baseAmil": {uf: d.get("gerado_em", "") for uf, d in A.items()},
        "baseBradesco": B.get("ref", ""),
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
