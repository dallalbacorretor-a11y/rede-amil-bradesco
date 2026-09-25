/* Barra de troca de operadora, no topo de cada rede.
   Entra no fim do index.html de cada pasta (ferramentas/sincronizar.sh) e se
   poe antes de tudo no <body>. As cores sao fixas: a barra fica sempre escura,
   em cima do cabecalho navy da Amil, do vinho da Bradesco e do azul da SulAmerica,
   nos dois temas. */
(function () {
  var OPERADORAS = [
    { id: "amil", nome: "Amil" },
    { id: "bradesco", nome: "Bradesco", longo: " Saúde" },
    { id: "sulamerica", nome: "SulAmérica", longo: " Saúde" },
    { id: "comparativo", nome: "Comparativo" }
  ];
  var eu = document.currentScript;
  var atual = eu && eu.getAttribute("data-operadora");

  var css =
    ".mzop{display:flex;align-items:center;justify-content:space-between;gap:12px;" +
    "padding:6px 24px;background:#060d18;border-bottom:1px solid rgba(255,255,255,.08);" +
    "font:500 12.5px/1.2 'IBM Plex Sans',-apple-system,'Segoe UI',sans-serif;" +
    "-webkit-font-smoothing:antialiased}" +
    ".mzop a{color:rgba(255,255,255,.72);text-decoration:none}" +
    ".mzop-inicio{display:inline-flex;align-items:center;gap:7px;padding:5px 2px;white-space:nowrap}" +
    ".mzop-inicio:hover{color:#fff}" +
    ".mzop-inicio b{font-weight:600;color:#d6b155;letter-spacing:.02em}" +
    ".mzop-troca{display:flex;padding:3px;border-radius:999px;background:rgba(255,255,255,.09)}" +
    ".mzop-troca a{padding:5px 14px;border-radius:999px;letter-spacing:.03em;white-space:nowrap;" +
    "transition:background .15s,color .15s}" +
    ".mzop-troca a:hover{background:rgba(255,255,255,.1);color:#fff}" +
    ".mzop-troca a[aria-current=page]{background:#d6b155;color:#0a0f17;font-weight:600}" +
    ".mzop a:focus-visible{outline:2px solid #d6b155;outline-offset:2px}" +
    "@media (max-width:560px){.mzop{padding:6px 12px;gap:8px}.mzop-longo{display:none}" +
    ".mzop-troca a{padding:5px 9px}}" +
    "@media (max-width:400px){.mzop-inicio b{display:none}}" +
    "@media print{.mzop{display:none!important}}";

  var estilo = document.createElement("style");
  estilo.textContent = css;
  document.head.appendChild(estilo);

  var barra = document.createElement("nav");
  barra.className = "mzop";
  barra.setAttribute("aria-label", "Trocar de operadora");

  var inicio = document.createElement("a");
  inicio.className = "mzop-inicio";
  inicio.href = "../";
  inicio.innerHTML = '<span aria-hidden="true">←</span><b>Mazza Broker</b>' +
    '<span class="mzop-longo">· Redes credenciadas</span>';
  barra.appendChild(inicio);

  var troca = document.createElement("div");
  troca.className = "mzop-troca";
  OPERADORAS.forEach(function (op) {
    var a = document.createElement("a");
    a.href = "../" + op.id + "/";
    a.textContent = op.nome;
    if (op.longo) {
      var l = document.createElement("span");
      l.className = "mzop-longo";
      l.textContent = op.longo;
      a.appendChild(l);
    }
    if (op.id === atual) a.setAttribute("aria-current", "page");
    troca.appendChild(a);
  });
  barra.appendChild(troca);

  document.body.insertBefore(barra, document.body.firstChild);
})();
