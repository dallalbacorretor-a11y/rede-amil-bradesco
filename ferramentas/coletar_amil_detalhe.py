"""Coleta de detalhe da Amil em Curitiba e na regiao metropolitana (busca avancada).

O coletar_amil.py consulta cada produto x cidade x tipo de servico. Aqui, para os
29 municipios da RMC, a mesma coleta e refeita do zero e conferida por dois
caminhos que nao dependem dela:

0. a unidade de um municipio que a busca nao oferece na lista de cidades
   (Almirante Tamandare, por exemplo) aparece na consulta da cidade vizinha; o
   coletar_amil.py a descartava por ser de outra cidade. Aqui ela entra na cidade
   dela, com o tipo e a especialidade da consulta em que apareceu.
1. a busca SEM tipo de servico, uma por produto e cidade: traz a rede inteira do
   produto na cidade. A uniao das consultas por tipo tem de ser igual a ela; a
   unidade que so aparece sem tipo (cadastrada num tipo fora dos sete) entra.
2. a busca POR NOME, nos 12 produtos, de cada estabelecimento que a Bradesco ou a
   SulAmerica lista na RMC e que o comparativo mostra sem Amil (comparativo/dados.js),
   e de quem a pagina da Amil (amil/index.html, outra base) tem na RMC e a busca
   avancada nao trouxe. A unidade da Amil que so aparece pelo nome entra.

Grava ferramentas/amil/PR/<CIDADE>.json (mesmo formato do coletar_amil.py) e o
relatorio ferramentas/amil_detalhe_rmc.json.

Uso: python3 ferramentas/coletar_amil_detalhe.py [--paralelo 6]
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coletar_amil as ca  # noqa: E402
import montar_comparativo as mc  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
UF = "PR"
RELATORIO = RAIZ / "ferramentas" / "amil_detalhe_rmc.json"
RMC = {ca.sem_acento(c) for c in ca.RMC}


def consulta(rede, municipio, tipo="", nome=""):
    q = [("plano.codigo", ""), ("filtro.codigoPlano", ""), ("filtro.operadora", ca._redes[rede]["operadora"]),
         ("filtro.contexto", "amil"), ("filtro.linha", ""), ("identificacao", ""),
         ("filtro.codigoRede", str(rede)), ("filtro.uf", UF), ("filtro.municipio", municipio),
         ("filtro.bairro", "TODOS OS BAIRROS"), ("filtro.tipoServico", tipo),
         ("filtro.especialidade", ""), ("filtro.nomeCredenciado", nome)]
    return ca.pede("/portal/web/servicos/saude/rede-credenciada/resultado-partial?" + urllib.parse.urlencode(q))


def total(html):
    m = re.search(r"localizou\s*(?:<[^>]+>\s*)*([\d.]+)", html or "")
    return int(m.group(1).replace(".", "")) if m else 0


def em_cache(nome, gerar):
    arq = ca.CACHE / nome
    if arq.exists():
        return arq.read_text(encoding="utf-8")
    html = gerar() or ""
    arq.write_text(html, encoding="utf-8")
    return html


def termo(nome, cidade):
    """A palavra mais longa que identifica o prestador (nem generica nem o nome da cidade)."""
    fora = set(mc.tokens(cidade)) | mc.GENERICAS
    pal = [p for p in re.sub(r"[^A-Z0-9 ]+", " ", ca.sem_acento(nome)).split()
           if len(p) >= 4 and not p.isdigit() and p not in mc.LIGACAO and p not in mc.JURIDICO]
    boas = [p for p in pal if mc.ABREV.get(p, p) not in fora] or pal
    return max(boas, key=len) if boas else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paralelo", type=int, default=6)
    ap.add_argument("--antes", help="pasta com os <CIDADE>.json de antes (para o relatorio)")
    a = ap.parse_args()
    # cache novo, do dia: a coleta e refeita do zero
    ca.CACHE = RAIZ / "ferramentas" / ".cache-amil-detalhe" / date.today().isoformat()
    ca.CACHE.mkdir(parents=True, exist_ok=True)
    ca.inicia()
    inicio = time.time()
    produtos = ca.REDES[UF]
    redes = sorted({r for rs in produtos.values() for r in rs})
    prod_de = {r: p for p, rs in produtos.items() for r in rs}
    muns = {r: ca.municipios(r, UF) for r in redes}

    # 1. coleta por tipo (coletar_amil.py), cidade a cidade
    antes = {}
    for c in sorted(RMC):
        f = (Path(a.antes) if a.antes else ca.PASTA / UF) / f"{c}.json"
        if f.exists():
            antes[c] = {(u["cod"], u["end"]) for u in json.loads(f.read_text(encoding="utf-8"))["unidades"]}
    print(f"coleta por tipo: {len(RMC)} cidades…", flush=True)
    for c in sorted(RMC):
        ca.coleta_cidade(UF, c, a.paralelo)

    def carrega(c):
        f = ca.PASTA / UF / f"{c}.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    # 0. unidades da RMC que so aparecem na consulta de outra cidade (coletar_amil.vizinhas)
    vizinhas = ca.vizinhas(UF)
    print(f"unidades da RMC achadas so na consulta de cidade vizinha: {len(vizinhas)}", flush=True)

    # 2. conferencia pela busca sem tipo
    tarefas = [(r, c) for r in redes for c in sorted(RMC) if c in muns[r]]
    print(f"busca sem tipo: {len(tarefas)} consultas…", flush=True)

    def sem_tipo(t):
        r, c = t
        return t, em_cache(f"{r}-{UF}-{c}-SEM_TIPO.html", lambda: consulta(r, muns[r][c]))

    so_sem_tipo, totais = {}, {}
    with ThreadPoolExecutor(a.paralelo) as ex:
        for (r, c), html in ex.map(sem_tipo, tarefas):
            totais[f"{r}-{c}"] = total(html)
            for k, u in ca.unidades(html).items():
                if u["cidade"] in RMC:
                    so_sem_tipo.setdefault((u["cidade"], k), (u, set()))[1].add(prod_de[r])
    acrescidas = []
    for (c, k), (u, prods) in so_sem_tipo.items():
        d = carrega(c)
        tem = {(x["cod"], x["end"]): x for x in (d or {}).get("unidades", [])}
        x = tem.get(k)
        faltam = prods - set(x["produtos"]) if x else prods
        if faltam:
            acrescidas.append({"cidade": c, "nome": u["nome"], "end": u["end"], "cnpj": u["cnpj"],
                               "produtos": sorted(faltam), "origem": "sem tipo", "_u": u, "_k": k})

    # 3. busca por nome
    t = (RAIZ / "comparativo" / "dados.js").read_text(encoding="utf-8")
    C = json.JSONDecoder().raw_decode(t, t.index("{", t.index("window.COMPARATIVO")))[0]
    alvos = []
    for c in sorted(RMC):
        for l in C["rede"].get(f"{UF}|{c}", []):
            if l.get("a"):
                continue
            nomes = [n for n in (l["n"], l.get("al"), l.get("nu")) if n]
            alvos.append({"cidade": c, "nome": l["n"], "outros": nomes[1:], "end": l.get("e") or "",
                          "origem": "comparativo sem Amil", "tem": ("Bradesco " if l.get("m") and
                          l["m"].strip("0") else "") + ("SulAmerica" if l.get("u") else "")})
    s = (RAIZ / "amil" / "index.html").read_text(encoding="utf-8")
    P = json.JSONDecoder().raw_decode(s, s.index("window.DADOS_UF=") + len("window.DADOS_UF="))[0][UF]
    coletados = set()
    for c in sorted(RMC):
        for u in (carrega(c) or {}).get("unidades", []):
            coletados.add(u["cnpj"])
    for p in P["prestadores"]:
        cids = {ca.sem_acento(x) for x in (p.get("cr") or p.get("cid") or [])} & RMC
        cnpj = re.sub(r"\D", "", p.get("c") or "")
        if cids and cnpj and cnpj not in coletados:
            alvos.append({"cidade": sorted(cids)[0], "nome": p["n"], "outros": [], "end": "",
                          "origem": "pagina da Amil", "cnpj": cnpj})
    pedidos = {}
    for al in alvos:
        al["termos"] = sorted({x for x in (termo(n, al["cidade"]) for n in [al["nome"]] + al["outros"]) if x})
        for te in al["termos"]:
            for r in redes:
                if al["cidade"] in muns[r]:
                    pedidos[(r, al["cidade"], te)] = None
    print(f"busca por nome: {len(alvos)} alvos, {len(pedidos)} consultas…", flush=True)

    def por_nome(k):
        r, c, te = k
        return k, em_cache(f"{r}-{UF}-{c}-NOME-{re.sub(r'[^A-Z0-9]+', '_', te)}.html",
                           lambda: consulta(r, muns[r][c], nome=te))

    achados_por = {}
    with ThreadPoolExecutor(a.paralelo) as ex:
        for n, ((r, c, te), html) in enumerate(ex.map(por_nome, list(pedidos)), 1):
            for k, u in ca.unidades(html).items():
                achados_por.setdefault((c, te), {}).setdefault(k, (u, set()))[1].add(prod_de[r])
            if n % 500 == 0:
                print(f"  {n}/{len(pedidos)} · {time.time() - inicio:.0f}s", flush=True)

    relatorio = []
    for al in alvos:
        toks = [mc.tokens(n) for n in [al["nome"]] + al["outros"]]
        ends = [re.sub(r" \((só|Amil|SulAm).*\)$", "", e.strip()) for e in re.split(r" / ", al["end"]) if e]
        achou = []
        for te in al["termos"]:
            for k, (u, prods) in achados_por.get((al["cidade"], te), {}).items():
                if u["cidade"] != al["cidade"]:
                    continue
                end_u = u["end"] + (" " + u["compl"] if u.get("compl") else "")
                nota = max(mc.parecido(tk, mc.tokens(u["nome"])) for tk in toks)
                mesmo_end = any(mc.mesmo_endereco(e, end_u) for e in ends)
                if (al.get("cnpj") and u["cnpj"] == al["cnpj"]) or (mesmo_end and nota >= 0.4) or nota >= 0.85:
                    achou.append({"nome": u["nome"], "end": end_u, "cnpj": u["cnpj"], "produtos": sorted(prods),
                                  "nota": round(nota, 2), "mesmo_end": mesmo_end, "_u": u, "_k": k})
        d = carrega(al["cidade"])
        tem = {(x["cod"], x["end"]): x for x in (d or {}).get("unidades", [])}
        for x in achou:
            y = tem.get(x["_k"])
            faltam = set(x["produtos"]) - set(y["produtos"]) if y else set(x["produtos"])
            x["na_coleta"] = bool(y)
            if faltam:
                acrescidas.append({"cidade": al["cidade"], "nome": x["nome"], "end": x["end"], "cnpj": x["cnpj"],
                                   "produtos": sorted(faltam), "origem": "nome", "_u": x["_u"], "_k": x["_k"]})
        relatorio.append(dict({k: v for k, v in al.items() if k != "outros"},
                              achados=[{k: v for k, v in x.items() if not k.startswith("_")} for x in achou]))

    # acrescenta o que so apareceu sem tipo ou pelo nome
    novas = 0
    for c in sorted({x["cidade"] for x in acrescidas}):
        d = carrega(c) or {"cidade": c, "uf": UF, "data": date.today().isoformat(), "fonte": ca.PAGINA,
                           "unidades": []}
        tem = {(x["cod"], x["end"]): x for x in d["unidades"]}
        for x in (x for x in acrescidas if x["cidade"] == c):
            y = tem.get(x["_k"])
            if not y:
                u = x["_u"]
                y = tem[x["_k"]] = dict(u, esp={"": list(u["esp"])}, produtos=[], tipos=[],
                                         achado=x["origem"])
                d["unidades"].append(y)
                novas += 1
            y["produtos"] += [p for p in x["produtos"] if p not in y["produtos"]]
        d["unidades"].sort(key=lambda u: (u["nome"], u["end"]))
        (ca.PASTA / UF / f"{c}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                                                   encoding="utf-8")

    resumo = []
    for c in sorted(RMC):
        d = carrega(c)
        if not d:
            continue
        agora = {(u["cod"], u["end"]) for u in d["unidades"]}
        velhas = antes.get(c, set())
        resumo.append({"cidade": c, "unidades": len(agora), "antes": len(velhas),
                       "novas": len(agora - velhas), "sairam": len(velhas - agora)})
        print(f"{c}: {len(agora)} unidades (antes {len(velhas)}; {len(agora - velhas)} novas, "
              f"{len(velhas - agora)} sairam)", flush=True)
    RELATORIO.write_text(json.dumps({
        "data": date.today().isoformat(), "cidades": resumo, "totais_sem_tipo": totais,
        "cidade_vizinha": [{"cidade": c, "nome": n, "end": e, "produtos": p} for c, n, e, p in vizinhas],
        "acrescidas": [{k: v for k, v in x.items() if not k.startswith("_")} for x in acrescidas],
        "procurados": relatorio}, ensure_ascii=False, indent=1), encoding="utf-8")
    ach = sum(1 for r in relatorio if r["achados"])
    print(f"\ncidade vizinha: {len(vizinhas)}; sem tipo: {sum(1 for x in acrescidas if x['origem'] == 'sem tipo')} acrescimos; "
          f"por nome: {ach} de {len(relatorio)} alvos com unidade parecida na Amil, "
          f"{sum(1 for x in acrescidas if x['origem'] == 'nome')} acrescimos; {novas} unidades novas; "
          f"{time.time() - inicio:.0f}s", flush=True)


if __name__ == "__main__":
    main()
