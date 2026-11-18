"""Resumo da rede Amil do Kit Corretor (kitcorretoramil.com.br): hospitais, pronto-socorros,
maternidades e laboratorios de cada plano, por estado.

O Kit Corretor e o material da Amil para corretores. O "Resumo da Rede" de cada linha (Linha
Selecionada, Linha Amil, Linha Amil Black) lista, por estado, cada hospital e laboratorio com
o que cada plano cobre nele (H hospital eletivo, PS pronto-socorro, M maternidade...). Nao tem
endereco nem CNPJ: so nome e cidade.

--baixar pergunta ao Kit (18 consultas) e grava ferramentas/amil_kit/bruto.json; sem ele, so
refaz ferramentas/amil_kit/resumo.json a partir do bruto. O montar_comparativo.py usa o
resumo para os planos dos hospitais e laboratorios da Amil.

Uso: python3 ferramentas/kit_amil.py [--baixar]
"""
import argparse
import json
import re
import subprocess
import time
import unicodedata
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "ferramentas" / "amil_kit"
AJAX = "https://kitcorretoramil.com.br/wp-admin/admin-ajax.php"
FONTE = "https://kitcorretoramil.com.br/linha-selecionada-pme/resumo-da-rede-pme/"
# linha -> (grupo da tabela -> produto pedido para os nomes das colunas)
LINHAS = {"Linha Selecionada": {"amil": "amil"},
          "Linha Amil": {"bronze": "bronze", "prata": "prata", "ouro": "ouro", "platinum": "platinum"},
          "Linha Amil Black": {"one_black": "one_black"}}
ESTADOS = {"PR": ("Sul", "Paraná"), "SC": ("Sul", "Santa Catarina"), "SP": ("Sudeste", "SP e Interior")}
# coluna do Kit -> produto da pagina (o que nao esta aqui e plano que a pagina nao tem:
# Prata II, Ouro II, S1500, Platinum R1/R2, Bronze SP...)
PLANO = {"Amil S380": "s380", "Amil S450": "s450", "Amil S750": "s750", "Amil S80": "s80",
         "Bronze PR": "bronze", "Prata": "prata", "Ouro": "ouro", "Platinum": "platinum",
         "Platinum Mais": "platmais", "Black I": "black", "Black II": "black", "S2500": "s2500",
         "S6500 Black": "s6500black"}
IMAGEM = re.compile(r"IMAGEM|RAIO|RADIOLOG|ULTRA|RESSONAN|TOMOGRAF|MAMOGRAF|DENSITO|ECOGRAF|NUCLEAR|"
                    r"DIAGNOSTICO POR")


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").upper()


def post(acao, corpo):
    r = subprocess.run(["curl", "-s", "-m", "90", "-X", "POST", f"{AJAX}?action={acao}",
                        "-H", "Content-Type: application/json", "-H", "Cache-Control: no-cache",
                        "--data", json.dumps(corpo, ensure_ascii=False), "-w", "\n%{http_code}"],
                       capture_output=True, text=True, check=True)
    texto, cod = r.stdout.rsplit("\n", 1)
    if cod != "200":
        raise RuntimeError(f"{acao}: HTTP {cod}")
    return json.loads(texto)


def baixar():
    bruto = {"data": date.today().isoformat(), "fonte": FONTE, "consultas": {}}
    for linha, grupos in LINHAS.items():
        for uf, (regiao, estado) in ESTADOS.items():
            cab = {}
            for prod in sorted(set(grupos.values())):
                cab[prod] = post("kc_get_planos_rede", {"produto": prod, "regiao": estado, "pf": "false",
                                                        "linhas_de_planos": linha}).get("data") or []
                time.sleep(1)
            for tipo in ("Hospitais", "Laboratórios"):
                dados = post("ktc_get_providers", {"pf": "false", "linha": linha, "regiao": regiao,
                                                   "estado": estado, "Tipo de Rede": tipo})
                bruto["consultas"][f"{linha}|{uf}|{tipo}"] = {"planos": cab, "dados": dados}
                print(linha, uf, tipo, {k: len(v) for k, v in dados.items() if isinstance(v, list)}, flush=True)
                time.sleep(1)
    PASTA.mkdir(parents=True, exist_ok=True)
    (PASTA / "bruto.json").write_text(json.dumps(bruto, ensure_ascii=False), encoding="utf-8")


def resumir():
    bruto = json.loads((PASTA / "bruto.json").read_text(encoding="utf-8"))
    itens = {}
    for chave, c in bruto["consultas"].items():
        linha, uf, tipo = chave.split("|")
        for grupo, prod in LINHAS[linha].items():
            # colunas: os planos do grupo na ordem do Kit (order_resumo_rede)
            planos = sorted((p["attributes"] for p in c["planos"].get(prod, [])
                             if p["attributes"].get("produto") == prod),
                            key=lambda a: a.get("order_resumo_rede") or 0)
            for r in c["dados"].get(grupo, []):
                valores = r[4:-1]
                if len(valores) != len(planos):
                    raise SystemExit(f"{chave} {grupo}: {len(valores)} colunas para {len(planos)} planos")
                cidade = sem_acento(r[3]).strip()
                k = (uf, cidade, sem_acento(r[0]).strip(), tipo)
                x = itens.setdefault(k, {"uf": uf, "cidade": cidade, "nome": " ".join(r[0].split()),
                                         "regiao": r[2], "tipo": tipo, "planos": {}})
                for p, bruto_v in zip(planos, valores):
                    # hospital: os servicos ("H - PS - M"); laboratorio: um tique (svg); X ou
                    # vazio: o plano nao tem
                    if not bruto_v or "fa-times" in bruto_v:
                        continue
                    x["planos"][p["plano"]] = re.sub(r"<[^>]+>", "", bruto_v).strip() or "sim"
    out = []
    for x in itens.values():
        prods = sorted({PLANO[p] for p in x["planos"] if p in PLANO})
        if x["uf"] == "SC":
            prods = ["s80sc" if p == "s80" else p for p in prods]
        if x["tipo"] == "Hospitais":
            t = 0
        else:
            t = 3 if IMAGEM.search(sem_acento(x["nome"])) else 2
        out.append(dict(x, produtos=prods, t=t))
    out.sort(key=lambda x: (x["uf"], x["cidade"], x["nome"]))
    (PASTA / "resumo.json").write_text(json.dumps({"data": bruto["data"], "fonte": bruto["fonte"],
                                                   "itens": out}, ensure_ascii=False, indent=0),
                                       encoding="utf-8")
    por = {}
    for x in out:
        por.setdefault((x["uf"], x["tipo"]), 0)
        por[(x["uf"], x["tipo"])] += 1
    print("resumo:", ", ".join(f"{uf} {t}: {n}" for (uf, t), n in sorted(por.items())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baixar", action="store_true")
    a = ap.parse_args()
    if a.baixar:
        baixar()
    resumir()


if __name__ == "__main__":
    main()
