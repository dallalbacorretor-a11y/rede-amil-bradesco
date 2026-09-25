"""Monta sulamerica/index.html: a rede da SulAmerica na mesma pagina da Bradesco.

A pagina e a da Bradesco (bradesco/index.html, trazida do rede-bradesco pela
sincronizacao) com os dados e os textos trocados: assim as melhorias feitas la
chegam aqui. Os dados vem de ferramentas/sulamerica/<UF>/<CIDADE>.json
(coletar_sulamerica.py), no mesmo formato dos dados da Bradesco:
  pr: [nome, cidade, bairro, [codigos], tipo, [especialidade, planos, ...],
       [[servico por plano]], laboratorio/imagem por plano, 0],
       [endereco, telefones, "", cnpj, cep]]
  tipo: 0 clinica, 1 hospital, 2 laboratorio, 3 medico, 4 centro de imagem.

Se o modelo mudar num ponto que esta troca espera, o script para com erro em
vez de publicar uma pagina com a marca errada.

Uso: python3 ferramentas/montar_sulamerica.py
"""
import json
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS_DIR = RAIZ / "ferramentas" / "sulamerica"
MODELO = RAIZ / "bradesco" / "index.html"
DESTINO = RAIZ / "sulamerica"
PORTAL = "https://portal.sulamericaseguros.com.br/rede-credenciada"
SITE = "https://dallalbacorretor-a11y.github.io/rede-amil-bradesco/sulamerica/"

PLANOS = [("classico100", "Clássico 100 Enfermaria", "Clássico 100"),
          ("especial100", "Especial 100", "Especial 100")]
# especialidades da SulAmerica que sao exame, nao consulta
LAB = {2820, 2110, 2120, 2121, 2823}
IMAGEM = {3121, 3320, 3620, 3420, 3220, 3920, 2020}
MATERNIDADE = {4540, 4550, 5740}
HOSPITAL_DIA = {6141}
ACENTO = {"CLINICA": "clínica", "MEDICA": "médica", "PEDIATRICA": "pediátrica", "CIRURGIA": "cirurgia",
          "ORTOPEDICO": "ortopédico", "OBSTETRICO": "obstétrico", "PEDIATRICO": "pediátrico",
          "PSIQUIATRIA": "psiquiatria", "OFTALMOLOGIA": "oftalmologia", "GINECOLOGIA": "ginecologia",
          "CARDIACA": "cardíaca", "TORACICA": "torácica", "PLASTICA": "plástica",
          "ONCOLOGICA": "oncológica", "ANALISE": "análise", "LABORATORIA": "laboratorial",
          "LABORATORIAL": "laboratorial", "DIAGNOSTICO": "diagnóstico", "RESSON": "resson.",
          "MAGNETICA": "magnética", "TOMO": "tomo", "COMPUTADORIZADA": "computadorizada",
          "OSSEA": "óssea", "ANATOMIA": "anatomia", "PATOLOGICA": "patológica", "GENETICA": "genética",
          "FONOAUDIOLOGIA": "fonoaudiologia", "NEUROLOGICA": "neurológica", "ORTOPEDICA": "ortopédica",
          "PELVICA": "pélvica", "URINARIO": "urinário", "RESPIRATORIA": "respiratória",
          "UROLOGICA": "urológica", "HEMATOLOGIA": "hematologia", "HEPATICO": "hepático",
          "MEDULA": "medula", "OSSEA,": "óssea,", "NUTRICIONAL": "nutricional", "IMUNOBIOLOGICOS": "imunobiológicos",
          "INFUSAO": "infusão", "TRAFEGO": "tráfego", "FAMILIA": "família", "ATENCAO": "atenção",
          "PRIMARIA": "primária", "ENDOSCOPIA": "endoscopia", "ENDOVASCULAR": "endovascular",
          "LINFATICA": "linfática", "CABECA": "cabeça", "PESCOCO": "pescoço", "MAO": "mão",
          "BUCO": "buco", "BARIATRICA": "bariátrica", "COLUNA": "coluna", "REABILITACAO": "reabilitação",
          "FISICA": "física", "OCUPACIONAL": "ocupacional", "INFANCIA": "infância", "ADOLESCENCIA": "adolescência",
          "VACINAS": "vacinas", "HOMEOPATIA": "homeopatia", "ACUPUNTURA": "acupuntura", "AVALIACAO": "avaliação",
          "PRONTO": "pronto", "SOC": "socorro", "SOCORRO": "socorro", "ESPECIALIZADO": "especializado",
          "HOSPITAL": "hospital", "HOSP": "hospital", "ESP": "especializado", "ESPEC": "especializado",
          "MATERNIDADE": "maternidade", "GERAL": "geral", "RETAGUARDA": "retaguarda", "DIA": "dia",
          "CARDIOVASC": "cardiovascular", "NEFRO": "nefro", "OTORRINOLARINGOLOGIA": "otorrinolaringologia",
          "TRAUMATOLOGIA": "traumatologia", "ORTOPEDIA": "ortopedia", "INFECTOLOGIA": "infectologia",
          "NEUROCIRURGIA": "neurocirurgia", "ONCOLOGIA": "oncologia", "PEDIATRIA": "pediatria",
          "PSICOLOGIA": "psicologia", "TRANSTORNOS": "transtornos", "DESENV": "desenv.",
          "ULTRASSONOGRAFIA": "ultrassonografia", "RADIOLOGIA": "radiologia", "DENSITOMETRIA": "densitometria",
          "ECOCARDIOGRAMA": "ecocardiograma", "ERGOMETRIA": "ergometria", "CITOPATOLOGIA": "citopatologia",
          "COLETA": "coleta", "DOMICILIAR": "domiciliar", "CHECK-UP": "check-up", "ANGIORRADIOLOGIA": "angiorradiologia"}


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").upper()


def legivel(desc):
    """'CLINICA MEDICA' -> 'Clínica médica' (a SulAmerica escreve em maiusculas sem acento)."""
    ps = [ACENTO.get(p, p.lower()) for p in re.sub(r"\s+", " ", desc.replace("\xa0", " ")).strip().split(" ")]
    t = " ".join(ps)
    return t[:1].upper() + t[1:]


def titulo(s):
    s = re.sub(r"\s+", " ", (s or "").strip())
    return " ".join(w if len(w) <= 2 and w.isupper() and w not in ("DE", "DA", "DO", "E") else w.capitalize()
                    for w in s.lower().split(" ")).replace(" De ", " de ").replace(" Da ", " da ") \
        .replace(" Do ", " do ").replace(" Dos ", " dos ").replace(" Das ", " das ").replace(" E ", " e ")


def tipo_de(u):
    cats = {c for cs in u["cats"].values() for c in cs}
    esps = {e for es in u["esp"].values() for e in es}
    if cats & {1, 2, 7}:
        return 1
    if u["pf"]:
        return 3
    if esps and esps <= LAB | IMAGEM:
        return 2 if esps & LAB else 4
    return 0


def servicos(u, plano):
    """H internacao, P.S pronto-socorro, M maternidade, HDIA hospital-dia, no plano."""
    cats = set(u["cats"].get(plano, []))
    esps = set(u["esp"].get(plano, []))
    s = []
    if 2 in cats and not (esps and esps <= HOSPITAL_DIA):
        s.append("H")
    if 1 in cats:
        s.append("P.S")
    if esps & MATERNIDADE:
        s.append("M")
    if 7 in cats or esps & HOSPITAL_DIA:
        s.append("HDIA")
    return "/".join(s)


def dados():
    nomes_esp = {int(k): legivel(v) for k, v in
                 json.loads((DADOS_DIR / "especialidades.json").read_text(encoding="utf-8")).items()}
    bradesco = ler_dados_bradesco()
    geo_brad = {(bradesco["uf"][c[0]], c[1]): g for c, g in zip(bradesco["cid"], bradesco["geo"])}
    ufs, cids, geo, bai, esp, nom, serv, pr, consulta = [], [], [], [], [], [], [""], [], {}
    idx = lambda lista, v: lista.index(v) if v in lista else (lista.append(v) or len(lista) - 1)
    datas = set()
    for arq in sorted(DADOS_DIR.glob("*/*.json")):
        d = json.loads(arq.read_text(encoding="utf-8"))
        if not d["unidades"]:
            continue
        uf, cidade = d["uf"], sem_acento(d["cidade"])
        iu = idx(ufs, uf)
        ic = len(cids)
        cids.append([iu, cidade])
        pts = [(u["lat"], u["lon"]) for u in d["unidades"] if u.get("lat")]
        geo.append(geo_brad.get((uf, cidade)) or
                   [round(sum(p[0] for p in pts) / len(pts), 4), round(sum(p[1] for p in pts) / len(pts), 4)])
        data = "/".join(reversed(d["data"].split("-")))
        consulta[str(ic)] = data
        datas.add(data)
        for u in d["unidades"]:
            t = tipo_de(u)
            sub = []
            todas = sorted({e for es in u["esp"].values() for e in es})
            for e in todas:
                mask = 0
                for b, (p, _, _) in enumerate(PLANOS):
                    if e in u["esp"].get(p, []):
                        mask |= 1 << b
                sub += [idx(esp, nomes_esp.get(e, str(e))), mask]
            blocos = 0
            if t == 1:
                blocos = [[idx(serv, servicos(u, p)) for p, _, _ in PLANOS]]
            exames = 0
            for b, (p, _, _) in enumerate(PLANOS):
                if set(u["esp"].get(p, [])) & (LAB | IMAGEM):
                    exames |= 1 << b
            end = titulo(u["end"]) + (", " + u["num"] if u.get("num") else "") + \
                (" " + titulo(u["compl"]) if u.get("compl") else "")
            fones = " · ".join(dict.fromkeys(u.get("tel") or []))[:80]
            pr.append([idx(nom, re.sub(r"\s+", " ", u["nome"]).strip()), ic, idx(bai, titulo(u.get("bairro"))),
                       [], t, sub, [blocos, exames, 0],
                       [end, fones, "", u.get("cnpj") or "", re.sub(r"\D", "", u.get("cep") or "")]])
    ds = sorted(datas, key=lambda x: x.split("/")[::-1])
    return {"ref": ds[-1] if ds else "", "fonte": "busca de rede referenciada da SulAmérica Saúde",
            "gerado": date.today().strftime("%d/%m/%Y"), "corretor": bradesco.get("corretor") or {},
            "logo": "", "logoBranca": "", "planos": [p[1] for p in PLANOS],
            "grupos": [{"rot": p[2], "bits": [b], "sub": None} for b, p in enumerate(PLANOS)],
            "hospRef": {}, "labRef": {}, "espFora": [], "uf": ufs, "cid": cids, "geo": geo, "bai": bai,
            "esp": esp, "nom": nom, "serv": serv, "pr": pr, "consulta": consulta}


def ler_dados_bradesco():
    html = MODELO.read_text(encoding="utf-8")
    i = html.index("const DADOS = ") + len("const DADOS = ")
    return json.JSONDecoder().raw_decode(html, i)[0]


def troca(html, velho, novo, regex=False, minimo=1):
    n = len(re.findall(velho, html, flags=re.S)) if regex else html.count(velho)
    if n < minimo:
        raise SystemExit(f"o modelo mudou: nao achei {velho[:70]!r}")
    return re.sub(velho, lambda m: novo, html, flags=re.S) if regex else html.replace(velho, novo)


COMO_LER = """<div class="corpo">
    <div>
      <h3>Uma linha por prestador</h3>
      <p>O ✔ à direita diz em quais planos ele está. Sob o nome vêm o bairro, a cidade, as
        especialidades, o endereço e o telefone. As etiquetas dizem o que mais ele faz:
        <b>internação</b>, <b>pronto-socorro</b>, <b>maternidade</b>, <b>hospital-dia</b> e
        <b>exames</b>.</p>
    </div>
    <div>
      <h3>Clássico 100 e Especial 100</h3>
      <p>Os dois planos da SulAmérica Saúde (PME; Empresarial e PME Mais têm a mesma rede).
        Clique em um ou nos dois: <b>atende a qualquer um</b> mostra quem está em pelo menos um;
        <b>atende a todos</b>, só a rede dos dois. A aba <b>Entre planos</b> mostra o que muda
        de um para o outro.</p>
    </div>
    <div>
      <h3>As cinco categorias</h3>
      <p><b>Hospitais</b> são quem interna, tem pronto-socorro ou hospital-dia na rede.
        <b>Médicos</b> são pessoa física. <b>Laboratórios</b> fazem análises clínicas ou
        patologia; <b>centros de imagem</b>, exames de imagem; o resto é <b>clínica</b>. A
        separação usa a categoria e as especialidades que a própria SulAmérica informa.</p>
    </div>
    <div>
      <h3>De onde vem</h3>
      <p>Da busca de rede referenciada do site da SulAmérica Saúde, plano a plano, categoria a
        categoria e especialidade a especialidade, cobrindo a cidade inteira.</p>
    </div>
    <div>
      <h3>Antes de fechar</h3>
      <p>A rede é definida e alterada só pela operadora. <b>Confirme no
        <a href="PORTAL" target="_blank" rel="noopener">portal da SulAmérica Saúde</a> antes
        de contratar.</b></p>
    </div>
  </div>
</details>""".replace("PORTAL", PORTAL)

RODAPE = """<footer>
  <span class="selo-rodape" id="seloRod">Mazza Broker</span>
  <b>Versão sempre atualizada:</b>
  <a href="SITE" style="color:var(--ouro)">SITE_TXT</a><br>
  <span id="fonteDetalhe"></span><br>
  Gerado em <span id="ger"></span> · <span id="rodCorr"></span><br>
  A classificação em hospital, laboratório, imagem e clínica segue a categoria e as especialidades
  informadas pela SulAmérica.
  <b>A rede é definida e alterada exclusivamente pela operadora. Confirme no
  <a href="PORTAL" target="_blank" rel="noopener" style="color:var(--ouro)">portal da SulAmérica
  Saúde</a> antes de contratar.</b>
</footer>""".replace("SITE_TXT", SITE.replace("https://", "").rstrip("/")).replace("SITE", SITE) \
    .replace("PORTAL", PORTAL)


def pagina(D):
    html = MODELO.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in html else "\n"
    html = html.replace("\r\n", "\n")
    i = html.index("const DADOS = ")
    j = html.index("\n", i)
    html = html[:i] + "@@DADOS@@" + html[j:]
    html = troca(html, r"<title>.*?</title>", "<title>Rede SulAmérica por Cidade</title>", regex=True)
    # sem logo da operadora (o CSS do logo sobrepoe o "hidden" e mostraria imagem quebrada)
    html = troca(html, r'<img class="logo-op" id="logoOp"[^>]*>\n?', "", regex=True)
    # o azul-marinho da SulAmerica no cabecalho; laranja e azul para os dois planos
    html = troca(html, "/* o cabecalho usa o vinho da Bradesco, que e a cor da marca deles */",
                 "/* o cabecalho usa o azul-marinho da SulAmerica */")
    html = troca(html, "--topo:#8b0633;", "--topo:#0b2d5c;")
    html = troca(html, "--topo-fraco:#e9c2ce;", "--topo-fraco:#c8d6ec;")
    html = troca(html, "--topo:#6b0427;", "--topo:#0a2347;")
    html = troca(html, "--topo-fraco:#e0aebe;", "--topo-fraco:#b9c9e2;")
    html = troca(html, "--p0:#a3123c; --p1:#b0552a;", "--p0:#c2560c; --p1:#1d5089;")
    html = troca(html, "--p0-bg:#fbecf0; --p1-bg:#fbefe8;", "--p0-bg:#fbefe6; --p1-bg:#eaf0f9;")
    html = troca(html, "--p0:#f08aa6; --p1:#e5a071;", "--p0:#e8a06b; --p1:#8fb6e8;")
    html = troca(html, "--p0-bg:#2a1520; --p1-bg:#2a1c14;", "--p0-bg:#2a1c14; --p1-bg:#14202f;")
    html = troca(html, r'<div class="corpo">.*?</details>', COMO_LER, regex=True)
    html = troca(html, r"<footer>.*?</footer>", RODAPE, regex=True)
    html = troca(html, r"const PORTAL = '[^']*';", f"const PORTAL = '{PORTAL}';", regex=True)
    # fontes: toda cidade vem da busca oficial; nao ha buscador nem listas em PDF
    html = troca(html, "    '<b>Consultas</b> · Brasil · buscador ' + esc(DADOS.ref),\n"
                       "    linha('Internação', HREF),\n    linha('Exames', LREF)\n", "")
    html = troca(html, r"det\.push\('<b>Fontes:</b> ' \+ esc\(DADOS\.fonte\).*?\);\n",
                 "det.push('<b>Planos:</b> ' + esc(PRODUTOS.join(' e ')) + ' (PME).');\n", regex=True)
    html = troca(html, r"det\.push\('Cobertura: as listas.*?\);\n",
                 "det.push('Cobertura: ' + CID.length.toLocaleString('pt-BR') + ' cidades.');\n", regex=True)
    html = troca(html, "consultas, exames, internação e pronto-socorro, com endereço e telefone), conferida contra as ' +\n"
                       "      'listas abaixo: quem está nelas e não aparece na busca, nem pelo nome, continua marcado.');",
                 "consultas, exames, internação e pronto-socorro, com endereço e telefone).');")
    html = troca(html, "https://www.bradescoseguros.com.br/clientes/produtos/plano-saude/consulta-de-rede-referenciada/",
                 PORTAL, minimo=0)
    html = troca(html, 'data-operadora="bradesco"', 'data-operadora="sulamerica"', minimo=0)
    html = html.replace("Bradesco Saúde", "SulAmérica Saúde").replace("Bradesco", "SulAmérica")
    html = html.replace("@@DADOS@@", "const DADOS = " + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";")
    return html.replace("\n", nl)


def main():
    D = dados()
    DESTINO.mkdir(exist_ok=True)
    (DESTINO / "index.html").write_text(pagina(D), encoding="utf-8", newline="")
    # o gerador de PDF e as fontes vem da pagina da Bradesco
    for f in ("pdf-rede.js", "pdfmake.min.js", "fontes-pdf.js"):
        shutil.copyfile(RAIZ / "bradesco" / f, DESTINO / f)
    print(f"sulamerica/index.html: {len(D['pr'])} prestadores em {len(D['cid'])} cidades, "
          f"{(DESTINO / 'index.html').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
