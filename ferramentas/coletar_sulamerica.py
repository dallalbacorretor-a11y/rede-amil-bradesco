"""Coleta a rede referenciada da SulAmerica Saude na busca oficial.

https://portal.sulamericaseguros.com.br/rede-credenciada leva, para cada plano,
a busca de prestadores em rederef-saude.appspot.com. A busca por proximidade
devolve, para um ponto, um raio, uma categoria (pronto-socorro, hospital,
medico/clinica/centro diagnostico, hospital-dia) e uma especialidade, os 50
registros mais proximos: cada um com o codigo do prestador (CNPJ sem os
digitos verificadores, ou o registro do medico), nome, endereco com CEP,
bairro, municipio, coordenadas e telefones.

Varredura: para cada plano, categoria e especialidade, uma consulta cobrindo a
regiao inteira; quando vem cheia (50), a area e dividida em quatro e cada parte
e consultada de novo, ate cada consulta vir com menos de 50 (a parte esta
completa). Grava ferramentas/sulamerica/<UF>/<CIDADE>.json so das cidades
pedidas; as respostas ficam em ferramentas/.cache-sulamerica/ (fora do git)
para retomar.

Planos (PME; Empresarial e PME Mais tem a mesma rede):
  classico100  Classico 100 Enfermaria  produto 557, plano 69300
  especial100  Especial 100             produto 553, plano 17924

Uso:
  python3 ferramentas/coletar_sulamerica.py --rmc     # Curitiba e regiao metropolitana
"""
import argparse
import http.cookiejar
import json
import math
import queue
import re
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
PASTA = RAIZ / "ferramentas" / "sulamerica"
CACHE = RAIZ / "ferramentas" / ".cache-sulamerica"
BASE = "https://rederef-saude.appspot.com"
PORTAL = "https://portal.sulamericaseguros.com.br/rede-credenciada"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"

PLANOS = {
    "classico100": {"nome": "Clássico 100 Enfermaria", "produto": 557, "plano": 69300},
    "especial100": {"nome": "Especial 100", "produto": 553, "plano": 17924},
}
CATEGORIAS = {1: "PRONTO SOCORRO", 2: "HOSPITAL E MATERNIDADE", 3: "MEDICO, CLINICA, CENTRO DIAGNOSTICO",
              7: "HOSPITAL DIA"}
LIMITE = 50            # registros por consulta
MEIO_MINIMO = 0.15     # km: menor meia-largura de quadrado na divisao

RMC = ["ADRIANOPOLIS", "AGUDOS DO SUL", "ALMIRANTE TAMANDARE", "ARAUCARIA", "BALSA NOVA",
       "BOCAIUVA DO SUL", "CAMPINA GRANDE DO SUL", "CAMPO DO TENENTE", "CAMPO LARGO", "CAMPO MAGRO",
       "CERRO AZUL", "COLOMBO", "CONTENDA", "CURITIBA", "DOUTOR ULYSSES", "FAZENDA RIO GRANDE",
       "ITAPERUCU", "LAPA", "MANDIRITUBA", "PIEN", "PINHAIS", "PIRAQUARA", "QUATRO BARRAS",
       "QUITANDINHA", "RIO BRANCO DO SUL", "RIO NEGRO", "SAO JOSE DOS PINHAIS", "TIJUCAS DO SUL",
       "TUNAS DO PARANA"]
# quadrado que cobre Curitiba e a regiao metropolitana: centro e meia-largura (km)
REGIAO_RMC = (-25.35, -49.45, 90.0)

_trava = threading.Lock()


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").upper().strip()


def cnpj_completo(base12):
    """CNPJ com os digitos verificadores a partir dos 12 primeiros. O codigo que comeca com
    1000000 e interno da SulAmerica (prestador sem CNPJ no cadastro), nao CNPJ."""
    if not re.fullmatch(r"\d{12}", base12 or "") or base12.startswith("1000000"):
        return ""
    n = [int(c) for c in base12]
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        r = sum(a * b for a, b in zip(n, pesos)) % 11
        n.append(0 if r < 2 else 11 - r)
    return "".join(map(str, n))


class Sessao:
    """Um cookie de sessao por plano (a busca exige a pagina aberta antes)."""

    def __init__(self, plano):
        self.p = PLANOS[plano]
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.abre()

    def abre(self):
        q = urllib.parse.urlencode({"login": "publico", "canal": 1, "tipoProduto": "M",
                                    "produto": self.p["produto"], "plano": self.p["plano"]})
        self.pede("/rederef/buscaPrestadores?" + q, json_=False)

    def pede(self, caminho, json_=True):
        req = urllib.request.Request(BASE + caminho, headers={
            "User-Agent": UA, "Accept": "application/json, text/javascript, */*",
            "X-Requested-With": "XMLHttpRequest", "captcha-token": ""})
        for tentativa in range(6):
            try:
                with self.op.open(req, timeout=90) as r:
                    t = r.read().decode("utf-8", "replace")
                if not json_:
                    return t
                if t.lstrip().startswith("<"):         # sessao expirada: abre de novo
                    with _trava:
                        self.abre()
                    raise ConnectionError("sessao expirada")
                return json.loads(t)
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                # erro 500 que se repete e da consulta, nao da rede: tres tentativas bastam
                if tentativa == 5 or isinstance(e, urllib.error.HTTPError) and e.code >= 500 and tentativa == 2:
                    raise
                time.sleep(2 ** tentativa)

    def especialidades(self, categoria):
        q = urllib.parse.urlencode({"canal": 1, "produto": self.p["produto"], "plano": self.p["plano"],
                                    "categoria": categoria, "prefixoEmpresa": "", "empresa": "",
                                    "procedimento": "", "tipoProduto": "M"})
        return self.pede("/common/especialidade/listar?" + q) or []

    def busca(self, categoria, especialidade, lat, lon, raio_km):
        q = urllib.parse.urlencode({
            "canal": 1, "latitude": round(lat, 6), "longitude": round(lon, 6), "categoria": categoria,
            "produto": self.p["produto"], "plano": self.p["plano"], "nome": "", "qualificacoes": "",
            "prefixoEmpresa": "", "empresa": "", "especialidade": especialidade, "procedimento": "",
            "tipoPesquisaProcedimento": "", "raio": int(raio_km * 1000), "programas": "", "ciCode": "",
            "elegivelPortaEntrada": "false"})
        return self.pede("/proximidade/prestador/buscar?" + q) or []


class Cache:
    def __init__(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        self.arq = CACHE / "consultas.jsonl"
        self.d = {}
        if self.arq.exists():
            for linha in self.arq.open(encoding="utf-8"):
                try:
                    x = json.loads(linha)
                except ValueError:
                    continue
                self.d[x["k"]] = x["r"]
        self.f = self.arq.open("a", encoding="utf-8")

    def get(self, k):
        return self.d.get(k)

    def put(self, k, r):
        with _trava:
            self.d[k] = r
            self.f.write(json.dumps({"k": k, "r": r}, ensure_ascii=False) + "\n")
            self.f.flush()


def enxuto(x):
    """So o que interessa de um registro da busca."""
    e = x.get("endereco") or {}
    g = x.get("posicaoGeografica") or {}
    return {"local": x.get("codigoPrestadorLocal"), "cod": (x.get("codigoPrestador") or "").strip(),
            "nome": (x.get("nomeFantasia") or "").strip(),
            "end": (e.get("endereco") or "").strip(), "num": (e.get("numeroEndereco") or "").strip(),
            "compl": (e.get("complementoEndereco") or "").strip(), "cep": (e.get("cep") or "").strip(),
            "uf": (e.get("sigUf") or "").strip(), "cidade": sem_acento(e.get("municipio")),
            "bairro": (e.get("bairro") or "").strip(), "lat": g.get("latitude"), "lon": g.get("longitude"),
            "tel": [t.get("telefone") for t in x.get("telefones") or [] if t.get("telefone")],
            "esp": sorted({s.get("codigo") for s in x.get("especialidadesAtendidas") or [] if s.get("codigo")})}


def varre(sessao, cache, plano, categoria, esp, regiao):
    """Divide a regiao em quadrados ate cada consulta vir com menos de 50 registros."""
    lat0, lon0, meio0 = regiao
    registros, cheios = [], []
    fila = [(lat0, lon0, meio0)]
    consultas = 0
    while fila:
        lat, lon, meio = fila.pop()
        raio = meio * math.sqrt(2) + 0.05
        k = f"{plano}|{categoria}|{esp}|{lat:.5f}|{lon:.5f}|{raio:.3f}"
        r = cache.get(k)
        if r is None:
            try:
                r = [enxuto(x) for x in sessao.busca(categoria, esp, lat, lon, raio)]
            except urllib.error.HTTPError as e:
                # o servidor as vezes da erro 500 numa consulta grande: divide a area; no
                # menor quadrado, registra a falha e segue
                print(f"  erro {e.code} {plano} cat {categoria} esp {esp} em {lat:.4f},{lon:.4f} "
                      f"raio {raio:.1f} km", flush=True)
                if meio / 2 >= MEIO_MINIMO:
                    r = [None] * LIMITE        # como se viesse cheia: divide
                else:
                    cheios.append((lat, lon))
                    continue
            else:
                cache.put(k, r)
        consultas += 1
        if r and r[0] is None:
            r_ok = []
        else:
            r_ok = r
        registros += r_ok
        if len(r) >= LIMITE:
            if meio / 2 < MEIO_MINIMO:
                cheios.append((lat, lon))
                continue
            dlat = (meio / 2) / 111.0
            dlon = (meio / 2) / (111.0 * math.cos(math.radians(lat)))
            for sy in (-1, 1):
                for sx in (-1, 1):
                    fila.append((lat + sy * dlat, lon + sx * dlon, meio / 2))
    return registros, consultas, cheios


def coleta(cidades, uf, regiao, paralelo=6):
    cache = Cache()
    unidades = {}
    # uma sessao por consulta em paralelo: o servidor atende uma consulta por vez em
    # cada sessao
    livres = {plano: queue.Queue() for plano in PLANOS}
    for plano in PLANOS:
        for _ in range(paralelo):
            livres[plano].put(Sessao(plano))
    sessoes = {plano: livres[plano].queue[0] for plano in PLANOS}
    tarefas = []
    for plano, sessao in sessoes.items():
        for cat in CATEGORIAS:
            for e in sessao.especialidades(cat):
                tarefas.append((plano, cat, e["codigo"]))
    print(f"{len(tarefas)} combinacoes de plano, categoria e especialidade", flush=True)

    def uma(t):
        plano, cat, esp = t
        sessao = livres[plano].get()
        try:
            return t, varre(sessao, cache, plano, cat, esp, regiao)
        finally:
            livres[plano].put(sessao)
    total = 0
    with ThreadPoolExecutor(paralelo) as ex:
        for n, ((plano, cat, esp), (regs, consultas, cheios)) in enumerate(ex.map(uma, tarefas), 1):
            total += consultas
            if cheios:
                print(f"  ATENCAO {plano} cat {cat} esp {esp}: {len(cheios)} ponto(s) "
                      "ainda com 50 registros no menor quadrado", flush=True)
            for r in regs:
                if r["uf"] != uf or r["cidade"] not in cidades:
                    continue
                u = unidades.setdefault(r["local"], dict(r, esp={}, cats={}, produtos=[]))
                u["esp"].setdefault(plano, [])
                for c in r["esp"] or [esp]:
                    if c not in u["esp"][plano]:
                        u["esp"][plano].append(c)
                u["cats"].setdefault(plano, [])
                if cat not in u["cats"][plano]:
                    u["cats"][plano].append(cat)
                if plano not in u["produtos"]:
                    u["produtos"].append(plano)
            if n % 20 == 0 or n == len(tarefas):
                print(f"  {n}/{len(tarefas)} especialidades, {total} consultas", flush=True)
    # descricao das especialidades (para a pagina)
    nomes_esp = {}
    for cat in CATEGORIAS:
        for e in sessoes["especial100"].especialidades(cat):
            nomes_esp[e["codigo"]] = e["descricao"]
    hoje = date.today().isoformat()
    por_cidade = {}
    for u in unidades.values():
        u["cnpj"] = cnpj_completo(u["cod"])
        u["pf"] = not re.fullmatch(r"\d{12}", u["cod"])     # medico: codigo com o registro (CRM)
        por_cidade.setdefault(u["cidade"], []).append(u)
    PASTA.joinpath(uf).mkdir(parents=True, exist_ok=True)
    for cidade in cidades:
        lista = sorted(por_cidade.get(cidade, []), key=lambda u: (u["nome"], u["end"]))
        (PASTA / uf / f"{cidade}.json").write_text(json.dumps({
            "cidade": cidade, "uf": uf, "data": hoje, "fonte": PORTAL,
            "planos": {k: v["nome"] for k, v in PLANOS.items()}, "unidades": lista},
            ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{cidade}/{uf}: {len(lista)} unidades", flush=True)
    (PASTA / "especialidades.json").write_text(json.dumps(
        {str(k): v for k, v in sorted(nomes_esp.items())}, ensure_ascii=False, indent=0), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rmc", action="store_true", help="Curitiba e regiao metropolitana (PR)")
    ap.add_argument("--paralelo", type=int, default=6)
    a = ap.parse_args()
    if a.rmc:
        coleta(RMC, "PR", REGIAO_RMC, a.paralelo)


if __name__ == "__main__":
    main()
