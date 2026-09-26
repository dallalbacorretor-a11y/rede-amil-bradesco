"""Confere a coleta da Amil pelo nome: cada estabelecimento que o comparativo mostra sem Amil
e procurado na busca avancada, pelo nome, em todos os produtos, na cidade dele.

A coleta (ferramentas/amil, que vem do rede-amil) pergunta produto x praca x tipo de servico;
esta conferencia nao depende dela. O que a busca por nome trouxer com o mesmo nome ou no mesmo
endereco e nao estiver na coleta e falta dela; o que estiver na coleta e caso de pareamento do
comparativo. Usa o coletor do rede-amil (clone ao lado deste repositorio, ou --rede-amil).

Grava ferramentas/amil_conferencia.json.

Uso: python3 ferramentas/conferir_amil.py [--uf PR] [--cidades CURITIBA "SAO JOSE DOS PINHAIS"]
       (sem --cidades: Curitiba e a regiao metropolitana)
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import montar_comparativo as mc  # noqa: E402


def termo(nome, cidade):
    """A palavra mais longa que identifica o prestador (nem generica nem o nome da cidade)."""
    fora = set(mc.tokens(cidade)) | mc.GENERICAS
    pal = [p for p in re.sub(r"[^A-Z0-9 ]+", " ", mc.sem_acento(nome)).split()
           if len(p) >= 4 and not p.isdigit() and p not in mc.LIGACAO and p not in mc.JURIDICO]
    boas = [p for p in pal if mc.ABREV.get(p, p) not in fora] or pal
    return max(boas, key=len) if boas else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", default="PR")
    ap.add_argument("--cidades", nargs="*")
    ap.add_argument("--rede-amil", default=str(RAIZ.parent / "rede-amil"))
    ap.add_argument("--paralelo", type=int, default=6)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.rede_amil) / "ferramentas"))
    import coletar as ca  # noqa: E402  (o coletor do rede-amil)
    uf = a.uf.upper()
    cidades = [ca.sem_acento(c) for c in a.cidades] if a.cidades else (ca.RMC if uf == "PR" else [])
    cache = RAIZ / "ferramentas" / ".cache-amil-conferencia" / date.today().isoformat()
    cache.mkdir(parents=True, exist_ok=True)
    ca.inicia()
    redes = sorted({r for rs in ca.REDES[uf].values() for r in rs})
    prod_de = {r: p for p, rs in ca.REDES[uf].items() for r in rs}
    muns = {r: ca.municipios(r, uf) for r in redes}

    t = (RAIZ / "comparativo" / "dados.js").read_text(encoding="utf-8")
    C = json.JSONDecoder().raw_decode(t, t.index("{", t.index("window.COMPARATIVO")))[0]
    alvos = []
    for c in cidades:
        for l in C["rede"].get(f"{uf}|{c}", []):
            if not l.get("a"):
                nomes = [n for n in (l["n"], l.get("al"), l.get("nu")) if n]
                alvos.append({"cidade": c, "nome": l["n"], "outros": nomes[1:], "end": l.get("e") or "",
                              "tem": ("Bradesco " if (l.get("m") or "").strip("0") else "") +
                                     ("SulAmerica" if l.get("u") else "")})
    pedidos = set()
    for al in alvos:
        al["termos"] = sorted({x for x in (termo(n, al["cidade"]) for n in [al["nome"]] + al["outros"]) if x})
        pedidos |= {(r, al["cidade"], te) for te in al["termos"] for r in redes if al["cidade"] in muns[r]}
    print(f"{len(alvos)} alvos, {len(pedidos)} buscas por nome…", flush=True)

    def busca(k):
        r, c, te = k
        arq = cache / f"{r}-{uf}-{ca.arquivo(c)}-NOME-{ca.arquivo(te)}.html"
        if not arq.exists():
            arq.write_text(ca.resultado(r, uf, muns[r][c], nome=te) or "", encoding="utf-8")
        return k, ca.unidades(arq.read_text(encoding="utf-8"))
    achados = {}
    with ThreadPoolExecutor(a.paralelo) as ex:
        for (r, c, te), us in ex.map(busca, sorted(pedidos)):
            for k, u in us.items():
                achados.setdefault((c, te), {}).setdefault(k, (u, set()))[1].add(prod_de[r])

    coletado = {}
    for f in (RAIZ / "ferramentas" / "amil" / uf).glob("*.json"):
        for u in json.loads(f.read_text(encoding="utf-8"))["unidades"]:
            coletado[(u["cod"], u["end"])] = u
    saida, faltas = [], 0
    for al in alvos:
        toks = [mc.tokens(n) for n in [al["nome"]] + al["outros"]]
        ends = [re.sub(r" \((só|Amil|SulAm).*\)$", "", e.strip()) for e in re.split(r" / ", al["end"]) if e]
        achou = []
        for te in al["termos"]:
            for k, (u, prods) in achados.get((al["cidade"], te), {}).items():
                if u["cidade"] != al["cidade"]:
                    continue
                nota = max(mc.parecido(tk, mc.tokens(u["nome"])) for tk in toks)
                mesmo_end = any(mc.mesmo_endereco(e, u["end"] + " " + u.get("compl", "")) for e in ends)
                if (mesmo_end and nota >= 0.4) or nota >= 0.85:
                    y = coletado.get(k)
                    falta = sorted(prods - set(y["produtos"])) if y else sorted(prods)
                    faltas += bool(falta)
                    achou.append({"nome": u["nome"], "end": u["end"], "cnpj": u["cnpj"], "produtos": sorted(prods),
                                  "nota": round(nota, 2), "mesmo_end": mesmo_end, "na_coleta": bool(y),
                                  "falta_na_coleta": falta})
        saida.append(dict({k: v for k, v in al.items() if k != "outros"}, achados=achou))
    (RAIZ / "ferramentas" / "amil_conferencia.json").write_text(json.dumps(
        {"data": date.today().isoformat(), "uf": uf, "cidades": cidades, "procurados": saida},
        ensure_ascii=False, indent=1), encoding="utf-8")
    com = [s for s in saida if s["achados"]]
    print(f"{len(com)} de {len(alvos)} com unidade parecida na Amil; {faltas} com produto fora da coleta",
          flush=True)
    for s in com:
        for x in s["achados"]:
            print(f"  {s['cidade']} | {s['nome']} -> {x['nome']} | {x['end']} | nota {x['nota']} "
                  f"{'mesmo endereco' if x['mesmo_end'] else ''} | "
                  f"{'na coleta' if x['na_coleta'] else 'FORA DA COLETA'} {x['falta_na_coleta'] or ''}")


if __name__ == "__main__":
    main()
