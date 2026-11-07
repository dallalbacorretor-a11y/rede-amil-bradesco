# Rede credenciada Amil, Bradesco Saúde e SulAmérica

As consultas de rede num link só:
**https://dallalbacorretor-a11y.github.io/rede-amil-bradesco/**

| Página | O que abre |
|---|---|
| `/` | Início: escolha da operadora |
| `/amil/` | Rede credenciada Amil (Paraná, Santa Catarina e São Paulo) |
| `/bradesco/` | Rede referenciada Bradesco Saúde (todos os estados) |
| `/sulamerica/` | Rede referenciada SulAmérica Saúde, Clássico 100 Enfermaria e Especial 100 (Paraná, Santa Catarina e São Paulo) |
| `/comparativo/` | Comparativo Amil × Bradesco × SulAmérica: estabelecimentos lado a lado, cidade por cidade, com PDF |

Dentro de cada rede, uma barra fina no topo troca para a outra operadora ou
volta ao início. Ela some na impressão e no PDF.

## De onde vêm as redes

Cada rede continua sendo mantida no repositório dela:

- [rede-amil](https://github.com/dallalbacorretor-a11y/rede-amil) → pasta `amil/`
- [rede-bradesco](https://github.com/dallalbacorretor-a11y/rede-bradesco) → pasta `bradesco/`

**Não edite `amil/` nem `bradesco/` aqui**: a sincronização apaga e traz de
novo. Atualize o repositório de origem e, em até 3 horas, o workflow
**Sincronizar** traz a mudança para cá. Para puxar na hora: aba *Actions* →
*Sincronizar* → *Run workflow*.

A cópia é idêntica à original, com duas linhas a mais no `index.html`: o
`noindex` (fora dos buscadores) e a barra de troca (`operadoras.js`). Quem faz
isso é `ferramentas/sincronizar.sh`, que também roda na mão:

```sh
ferramentas/sincronizar.sh
```

## SulAmérica

A SulAmérica é coletada aqui mesmo, na busca oficial de rede referenciada:

```sh
python3 ferramentas/coletar_sulamerica.py --estados PR SC SP   # grava ferramentas/sulamerica/<UF>/<CIDADE>.json
python3 ferramentas/montar_sulamerica.py                       # monta sulamerica/index.html
```

A busca devolve os 50 registros mais próximos de um ponto; a coleta divide a
região em quadrados até cada consulta vir com menos de 40 (saturada, ela às
vezes volta com 48 ou 49), e refaz letra a letra o ponto que ainda vem cheio. O que o servidor da SulAmérica não entrega nem assim
fica em `ferramentas/sulamerica/_lacunas.json`.

## Comparativo

`comparativo/dados.js` é gerado por `ferramentas/montar_comparativo.py` a
partir das três pastas: só estabelecimentos (médico pessoa física fica de
fora), cruzados pelo nome dentro da mesma cidade. A mesma instituição com
nomes diferentes em cada operadora é unificada (abreviações expandidas,
"LTDA", "S/A" e palavras de ligação ignoradas); quando o nome difere, a
tela mostra também o nome da Bradesco. O workflow **Sincronizar** remonta o
comparativo sempre que uma das redes muda.

## Aviso importante

A rede credenciada é definida e alterada exclusivamente pela operadora. Cada
página é um retrato da consulta feita na data indicada nela.
**Confirme no portal da operadora antes de contratar.**

## Contato

Alan Vinicius Dall Alba — Mazza Broker
alan.vinicius@mazzabroker.com.br
