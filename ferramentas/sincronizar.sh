#!/usr/bin/env bash
# Traz o site de cada operadora do repositorio de origem para a pasta dela.
#
# Os repositorios rede-amil e rede-bradesco continuam sendo onde cada rede e
# atualizada; este aqui so junta os dois sob um link. Por isso a copia e
# sempre inteira (apaga e traz de novo) e a unica mudanca feita nela e a
# barra de troca de operadora, acrescentada no fim do index.html.
#
# Uso: ferramentas/sincronizar.sh
#   ORIGEM_AMIL / ORIGEM_BRADESCO trocam a origem (ex.: um clone local).
set -euo pipefail

raiz="$(cd "$(dirname "$0")/.." && pwd)"
origem_amil="${ORIGEM_AMIL:-https://github.com/dallalbacorretor-a11y/rede-amil.git}"
origem_bradesco="${ORIGEM_BRADESCO:-https://github.com/dallalbacorretor-a11y/rede-bradesco.git}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

traz() {
  local operadora="$1" origem="$2"
  local destino="$raiz/$operadora"

  git clone --quiet --depth 1 --branch main "$origem" "$tmp/$operadora"

  rm -rf "$destino"
  mkdir -p "$destino"
  git -C "$tmp/$operadora" archive HEAD | tar -x -C "$destino"
  # o que e do repositorio de origem, e nao do site, fica la
  rm -rf "$destino/README.md" "$destino/.gitignore" "$destino/robots.txt" "$destino/.github"

  python3 - "$destino/index.html" "$operadora" <<'PY'
import re, sys

caminho, operadora = sys.argv[1], sys.argv[2]
# newline="" deixa as quebras de linha como vieram (a Bradesco usa CRLF)
with open(caminho, encoding="utf-8", newline="") as f:
    html = f.read()
nl = "\r\n" if "\r\n" in html else "\n"

# fora dos buscadores, como o resto deste site
robots = '<meta name="robots" content="noindex, nofollow">'
if robots not in html:
    html = re.sub(r'(<meta charset="utf-8">)', lambda m: m.group(1) + nl + robots,
                  html, count=1, flags=re.I)

# a barra entra no fim; so conta o </body> que fecha o arquivo, nunca um que
# esteja dentro de algum texto do JavaScript
barra = f'<script src="../operadoras.js" data-operadora="{operadora}"></script>' + nl
if "operadoras.js" not in html:
    fim = re.search(r"</body>\s*(</html>\s*)?$", html, flags=re.I)
    if fim:
        html = html[: fim.start()] + barra + html[fim.start():]
    else:
        html = html.rstrip("\r\n") + nl + barra

with open(caminho, "w", encoding="utf-8", newline="") as f:
    f.write(html)
PY

  echo "$operadora: $(git -C "$tmp/$operadora" log -1 --format='%h %s')"
}

traz amil "$origem_amil"
traz bradesco "$origem_bradesco"
