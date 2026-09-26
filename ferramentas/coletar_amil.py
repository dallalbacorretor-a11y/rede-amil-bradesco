"""Coleta a rede da Amil por unidade, na busca avancada do portal da Amil.

https://amil.com.br/portal/web/servicos/saude/rede-credenciada/amil/busca-avancada

A pagina da Amil deste site (amil/) guarda um registro por CNPJ com todos os
enderecos juntos. Para o comparativo bater unidade com unidade, a busca
avancada traz cada unidade separada: CNPJ da filial, endereco com CEP,
telefones, bairro e cidade. Uma consulta por produto, cidade e tipo de
servico, sem escolher especialidade (vem tudo, com a especialidade de cada
linha).

Grava ferramentas/amil/<UF>/<CIDADE>.json; o montar_comparativo.py usa esses
arquivos no lugar dos dados da pagina da Amil nas cidades coletadas.
Respostas ficam em ferramentas/.cache-amil/ (fora do git) para retomar.

Uso:
  python3 ferramentas/coletar_amil.py PR CURITIBA "SAO JOSE DOS PINHAIS"
  python3 ferramentas/coletar_amil.py PR --rmc          # Curitiba e regiao metropolitana
  python3 ferramentas/coletar_amil.py SC --todas        # todas as pracas do estado
"""
import argparse
import html as H
import http.cookiejar
import json
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "ferramentas" / "amil"
CACHE = RAIZ / "ferramentas" / ".cache-amil"
PORTAL = "https://amil.com.br"
PAGINA = PORTAL + "/portal/web/servicos/saude/rede-credenciada/amil/busca-avancada"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

# produto da pagina da Amil -> redes da busca avancada (QP; QC e a mesma rede).
# Conferido pelos hospitais de Curitiba: a mesma lista, produto a produto.
REDES = {
    "PR": {"bronze": [1123], "prata": [1079], "ouro": [1074], "platinum": [1081], "s80": [877],
           "s380": [884], "s450": [879], "s750": [880], "black": [1134, 1136], "s2500": [881],
           "s6500black": [882]},
    "SC": {"prata": [1079], "ouro": [1074], "platinum": [1081], "platmais": [1069], "s80sc": [1004],
           "s380": [884], "s450": [879], "s750": [880]},
    "SP": {"prata": [1079], "ouro": [1074], "platinum": [1081], "s380": [884], "s450": [879],
           "s750": [880], "black": [1134, 1136], "s2500": [881], "s6500black": [882]},
}
TIPOS = ["CONSULTORIOS - CLINICAS - TERAPIAS", "HEMODIALISE", "HOSPITAIS PARA INTERNACAO",
         "LABORATORIOS E EXAMES", "PRONTO ATENDIMENTO - HORARIO COMERCIAL",
         "PRONTO-SOCORRO 24H (URGENCIA E EMERGENCIA)", "TEA"]
RMC = ["ADRIANOPOLIS", "AGUDOS DO SUL", "ALMIRANTE TAMANDARE", "ARAUCARIA", "BALSA NOVA",
       "BOCAIUVA DO SUL", "CAMPINA GRANDE DO SUL", "CAMPO DO TENENTE", "CAMPO LARGO", "CAMPO MAGRO",
       "CERRO AZUL", "COLOMBO", "CONTENDA", "CURITIBA", "DOUTOR ULYSSES", "FAZENDA RIO GRANDE",
       "ITAPERUCU", "LAPA", "MANDIRITUBA", "PIEN", "PINHAIS", "PIRAQUARA", "QUATRO BARRAS",
       "QUITANDINHA", "RIO BRANCO DO SUL", "RIO NEGRO", "SAO JOSE DOS PINHAIS", "TIJUCAS DO SUL",
       "TUNAS DO PARANA"]

_cj = http.cookiejar.CookieJar()
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
_trava = threading.Lock()
_redes = {}


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").upper()


def pede(caminho, json_=False):
    h = {"User-Agent": UA, "Referer": PAGINA, "X-Requested-With": "XMLHttpRequest"}
    if json_:
        h["Accept"] = "application/vnd.amil.busca-credenciado.v2+json"
    url = PORTAL + caminho.replace("https://amil.com.br:443", "").replace(PORTAL, "")
    for tentativa in range(6):
        try:
            with _op.open(urllib.request.Request(url, headers=h), timeout=120) as r:
                t = r.read().decode()
            return json.loads(t) if json_ else t
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                return None
            if tentativa == 5:
                raise
            time.sleep(2 ** tentativa)


def inicia():
    with _trava:
        if not _redes:
            pede("/portal/web/servicos/saude/rede-credenciada/amil/busca-avancada")   # cookies
            for r in pede("/portal/web/servicos/saude/rede-credenciada/amil/redes-comercializadas",
                          json_=True)["redes"]:
                _redes[r["rede"]["codigo"]] = r["rede"]


def municipios(rede, uf):
    d = pede(f"/portal/web/servicos/saude/rede-credenciada/{rede}/estado/{uf.lower()}", json_=True)
    return {sem_acento(m["value"]): m["value"] for m in (d or {}).get("municipios", [])}


def resultado(rede, uf, municipio, tipo):
    q = [("plano.codigo", ""), ("filtro.codigoPlano", ""), ("filtro.operadora", _redes[rede]["operadora"]),
         ("filtro.contexto", "amil"), ("filtro.linha", ""), ("identificacao", ""),
         ("filtro.codigoRede", str(rede)), ("filtro.uf", uf), ("filtro.municipio", municipio),
         ("filtro.bairro", "TODOS OS BAIRROS"), ("filtro.tipoServico", tipo),
         ("filtro.especialidade", ""), ("filtro.nomeCredenciado", "")]
    return pede("/portal/web/servicos/saude/rede-credenciada/resultado-partial?" + urllib.parse.urlencode(q))


def unidades(html):
    """Unidades de um resultado: {(codigo do credenciado, logradouro): unidade}."""
    out = {}
    for tab in re.split(r'<table class="tabelaBusca">', html or "")[1:]:
        m = re.search(r'credenciado-especialidade">([^<]*)<', tab)
        esp = H.unescape(m.group(1).strip()) if m else ""
        for cred in re.split(r'<tr class="credenciado', tab)[1:]:
            nome = re.search(r'nomeFantasia">([^<]*)<', cred)
            cnpj = re.search(r"CNPJ:\s*([\d./-]+)", cred)
            selos = re.findall(r'class="icn-([a-z])', cred.split('<tr class="estabelecimento')[0])
            for est in re.split(r'<tr class="estabelecimento', cred)[1:]:
                idm = re.search(r'id="dados-endereco-credenciado-([\d-]+)"', est)

                def span(c):
                    m = re.search(r'class="' + c + r'"[^>]*>([^<]*)<', est)
                    return H.unescape(m.group(1).strip()) if m else ""

                def valor(c):
                    m = re.search(r'class="' + c + r'" value="([^"]*)"', est)
                    return H.unescape(m.group(1).strip()) if m else ""
                cod = idm.group(1).split("-")[0] if idm else ""
                k = (cod, span("logradouro"))
                u = out.setdefault(k, {
                    "cod": cod, "nome": H.unescape(nome.group(1).strip()) if nome else "",
                    "cnpj": re.sub(r"\D", "", cnpj.group(1)) if cnpj else "",
                    "end": span("logradouro"), "compl": span("complemento"), "cep": span("cep"),
                    "cidade": sem_acento(valor("cidade")), "uf": valor("estado"),
                    "lat": valor("latitude"), "lon": valor("longitude"),
                    "tel": [H.unescape(t.strip()) for t in re.findall(r'class="telefone">([^<]*)<', est)],
                    "bairro": span("bairro"), "selos": selos, "esp": []})
                if esp and esp not in u["esp"]:
                    u["esp"].append(esp)
    return out


def coleta_cidade(uf, cidade, paralelo=4):
    inicia()
    CACHE.mkdir(parents=True, exist_ok=True)
    produtos = REDES[uf]
    # onde cada rede atende (nome da cidade como a busca escreve)
    muns = {rede: municipios(rede, uf) for redes in produtos.values() for rede in redes}
    tarefas = [(prod, rede, muns[rede][cidade], tipo)
               for prod, redes in produtos.items() for rede in redes if cidade in muns[rede]
               for tipo in TIPOS]

    def uma(t):
        prod, rede, mun, tipo = t
        arq = CACHE / f"{rede}-{uf}-{sem_acento(mun)}-{re.sub(r'[^A-Z0-9]+', '_', tipo)}.html"
        if arq.exists():
            return t, arq.read_text(encoding="utf-8")
        html = resultado(rede, uf, mun, tipo) or ""
        arq.write_text(html, encoding="utf-8")
        return t, html

    unid = {}
    with ThreadPoolExecutor(paralelo) as ex:
        for (prod, rede, mun, tipo), html in ex.map(uma, tarefas):
            for k, u in unidades(html).items():
                if u["cidade"] != cidade:
                    continue        # a busca por cidade traz tambem vizinhos; cada um na sua cidade
                x = unid.setdefault(k, dict(u, esp={}, produtos=[], tipos=[]))
                x["esp"].setdefault(tipo, [])
                for e in u["esp"]:
                    if e not in x["esp"][tipo]:
                        x["esp"][tipo].append(e)
                if prod not in x["produtos"]:
                    x["produtos"].append(prod)
                if tipo not in x["tipos"]:
                    x["tipos"].append(tipo)
                x["selos"] = sorted(set(x["selos"]) | set(u["selos"]))
    lista = sorted(unid.values(), key=lambda u: (u["nome"], u["end"]))
    PASTA.joinpath(uf).mkdir(parents=True, exist_ok=True)
    saida = PASTA / uf / f"{cidade}.json"
    saida.write_text(json.dumps({"cidade": cidade, "uf": uf, "data": date.today().isoformat(),
                                 "fonte": PAGINA, "unidades": lista},
                                ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{cidade}/{uf}: {len(lista)} unidades, {len(tarefas)} consultas", flush=True)
    return lista


def vizinhas(uf, pular=()):
    """Unidade de um municipio que a busca nao oferece na lista de cidades do produto (Almirante
    Tamandare, por exemplo) so aparece na consulta de uma cidade vizinha, e coleta_cidade guarda
    so quem e da cidade pedida: ela ficava de fora. Aqui, a partir do cache (nenhuma consulta
    nova), cada unidade que apareceu na consulta de outra cidade entra no arquivo da cidade
    dela, com o produto, o tipo e a especialidade da consulta. So em cidade que ja tem arquivo
    (a coletada): nas outras, o comparativo continua usando a pagina da Amil. `pular`: cidades
    que ficam como estao. Devolve [(cidade, nome, endereco, produtos)] do que entrou."""
    tipo_de = {re.sub(r"[^A-Z0-9]+", "_", t): t for t in TIPOS}
    prod_de = {r: p for p, rs in REDES[uf].items() for r in rs}
    achadas = {}
    for arq in CACHE.glob(f"*-{uf}-*.html"):
        partes = arq.stem.split("-")
        if len(partes) != 4 or partes[3] not in tipo_de or not partes[0].isdigit() \
                or int(partes[0]) not in prod_de:
            continue
        r, cidade_q, tipo = int(partes[0]), partes[2], tipo_de[partes[3]]
        for k, u in unidades(arq.read_text(encoding="utf-8")).items():
            if u["uf"] != uf or u["cidade"] == cidade_q or u["cidade"] in pular:
                continue
            v = achadas.setdefault((u["cidade"], k), {"u": u, "p": set(), "esp": {}})
            v["p"].add(prod_de[r])
            es = v["esp"].setdefault(tipo, [])
            es += [e for e in u["esp"] if e not in es]
    entrou = []
    for c in sorted({c for c, _ in achadas}):
        f = PASTA / uf / f"{c}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        tem = {(x["cod"], x["end"]): x for x in d["unidades"]}
        mudou = False
        for (cv, k), v in achadas.items():
            if cv != c:
                continue
            y = tem.get(k)
            if not y:
                y = tem[k] = dict(v["u"], esp={}, produtos=[], tipos=[], achado="cidade vizinha")
                d["unidades"].append(y)
            novos = v["p"] - set(y["produtos"])
            if novos or not y["tipos"]:
                entrou.append((c, y["nome"], y["end"], sorted(novos or v["p"])))
            antes = json.dumps([y["produtos"], y["tipos"], y["esp"]], sort_keys=True)
            # so acrescenta, na ordem em que ja estava
            y["produtos"] += [p for p in sorted(v["p"]) if p not in y["produtos"]]
            y["tipos"] += [t for t in sorted(v["esp"]) if t not in y["tipos"]]
            for t, es in v["esp"].items():
                y["esp"].setdefault(t, [])
                y["esp"][t] += [e for e in es if e not in y["esp"][t]]
            mudou |= antes != json.dumps([y["produtos"], y["tipos"], y["esp"]], sort_keys=True)
        if mudou:
            d["unidades"].sort(key=lambda u: (u["nome"], u["end"]))
            f.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return entrou


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uf")
    ap.add_argument("cidades", nargs="*")
    ap.add_argument("--rmc", action="store_true", help="Curitiba e regiao metropolitana (PR)")
    ap.add_argument("--todas", action="store_true", help="todas as pracas dos produtos no estado")
    ap.add_argument("--paralelo", type=int, default=4)
    a = ap.parse_args()
    uf = a.uf.upper()
    inicia()
    cidades = [sem_acento(c) for c in a.cidades]
    if a.rmc:
        cidades += RMC
    if a.todas:
        todas = set()
        for redes in REDES[uf].values():
            for rede in redes:
                todas |= set(municipios(rede, uf))
        cidades += sorted(todas)
    feitas = set()
    for c in cidades:
        if c not in feitas:
            feitas.add(c)
            coleta_cidade(uf, c, a.paralelo)
    entrou = vizinhas(uf)
    print(f"{len(entrou)} unidades (ou produtos) achadas so na consulta de cidade vizinha", flush=True)


if __name__ == "__main__":
    main()
