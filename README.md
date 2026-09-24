# Rede credenciada Amil e Bradesco Saúde

As duas consultas de rede num link só:
**https://dallalbacorretor-a11y.github.io/rede-amil-bradesco/**

| Página | O que abre |
|---|---|
| `/` | Início: escolha da operadora |
| `/amil/` | Rede credenciada Amil (Paraná, Santa Catarina e São Paulo) |
| `/bradesco/` | Rede referenciada Bradesco Saúde (todos os estados) |
| `/comparativo/` | Comparativo Amil × Bradesco: estabelecimentos lado a lado, cidade por cidade, com PDF |

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

## Comparativo

`comparativo/dados.js` é gerado por `ferramentas/montar_comparativo.py` a
partir das duas pastas: só estabelecimentos (médico pessoa física fica de
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
