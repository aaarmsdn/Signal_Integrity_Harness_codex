const colors = {
  community_llm_wiki: "#2364aa",
  community_signal_integrity: "#b9473d",
  community_power_integrity: "#2d7d59",
  community_package_pcb: "#b98224",
  community_verification_strategy: "#6b5ca5",
  community_knowledge_intake: "#267c8f",
  community_pdn: "#2d7d59",
  community_si_coupling: "#b9473d",
  community_toolchain: "#b98224",
  community_sources: "#6b5ca5",
  community_uncategorized: "#68737b"
};

let graphData;
let selectedId = null;

function emptyGraph() {
  return {
    schema_version: "0.1",
    generated_from: "empty_repo_checkout",
    nodes: [],
    links: [],
    documents: [],
    communities: []
  };
}

async function loadGraph() {
  if (window.SIPI_GRAPH_DATA) {
    graphData = window.SIPI_GRAPH_DATA;
  } else {
    try {
      const response = await fetch("../data/knowledge_graph.json");
      graphData = response.ok ? await response.json() : emptyGraph();
    } catch {
      graphData = emptyGraph();
    }
  }
  graphData.nodes ||= [];
  graphData.links ||= [];
  graphData.documents ||= [];
  graphData.communities ||= [];
  populateFilters();
  renderStats();
  renderInsights();
  renderGraph();
  renderDetails(graphData.nodes.find((node) => node.type === "concept") || graphData.nodes[0]);
}

function renderStats() {
  const conceptCount = graphData.nodes.filter((node) => node.type === "concept").length;
  const documentCount = graphData.nodes.filter((node) => node.type === "document").length;
  const strategyCount = graphData.documents.filter((doc) => doc.kind === "design_strategy").length;
  const stats = document.getElementById("stats");
  stats.innerHTML = `
    <div class="stat"><strong>${conceptCount}</strong><span>Concepts</span></div>
    <div class="stat"><strong>${graphData.links.length}</strong><span>Links</span></div>
    <div class="stat"><strong>${documentCount}</strong><span>Sources</span></div>
    <div class="stat"><strong>${strategyCount}</strong><span>Strategies</span></div>
  `;
}

function renderInsights() {
  const panel = document.getElementById("insights");
  const insights = graphData.insights || {};
  const isolated = insights.isolated_concepts || [];
  const bridges = insights.bridge_concepts || [];
  const sparse = insights.sparse_communities || [];
  const cards = [
    {
      title: "Knowledge Gaps",
      value: isolated.length,
      items: isolated.slice(0, 4).map((item) => item.label)
    },
    {
      title: "Bridge Concepts",
      value: bridges.length,
      items: bridges.slice(0, 4).map((item) => `${item.label} (${item.community_count})`)
    },
    {
      title: "Sparse Clusters",
      value: sparse.length,
      items: sparse.slice(0, 4).map((item) => `${item.community.replace(/^community_/, "")}: ${item.cohesion}`)
    }
  ];
  panel.innerHTML = `
    <h3>Graph Insights</h3>
    ${cards.map((card) => `
      <button class="insight-card" type="button" data-kind="${escapeHtml(card.title)}">
        <strong>${card.value}</strong>
        <span>${escapeHtml(card.title)}</span>
        ${card.items.length ? `<small>${card.items.map(escapeHtml).join(", ")}</small>` : "<small>No current items</small>"}
      </button>
    `).join("")}
  `;
}

function populateFilters() {
  const kindFilter = document.getElementById("kindFilter");
  const topicFilter = document.getElementById("topicFilter");
  const kinds = [...new Set(graphData.documents.map((doc) => doc.kind).filter(Boolean))].sort();
  const topics = [...new Set(graphData.documents.map((doc) => doc.topic).filter(Boolean))].sort();

  kindFilter.innerHTML = `<option value="">All</option>${kinds.map((kind) => `<option value="${escapeHtml(kind)}">${escapeHtml(kind)}</option>`).join("")}`;
  topicFilter.innerHTML = `<option value="">All</option>${topics.map((topic) => `<option value="${escapeHtml(topic)}">${escapeHtml(topic)}</option>`).join("")}`;
}

function communityIndex(id) {
  return Math.max(0, graphData.communities.findIndex((community) => community.id === id));
}

function layoutNodes(width, height) {
  const centerX = width / 2;
  const centerY = height / 2;
  const conceptNodes = graphData.nodes.filter((node) => node.type === "concept");
  const documentNodes = graphData.nodes.filter((node) => node.type === "document");
  const communities = [...new Set(conceptNodes.map((node) => node.community))];
  const radius = Math.max(150, Math.min(width, height) * 0.33);

  communities.forEach((communityId, communityPosition) => {
    const members = conceptNodes.filter((node) => node.community === communityId);
    const communityAngle = (Math.PI * 2 * communityPosition) / communities.length - Math.PI / 2;
    const communityX = centerX + Math.cos(communityAngle) * radius * 0.55;
    const communityY = centerY + Math.sin(communityAngle) * radius * 0.55;
    members.forEach((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, members.length) + communityAngle;
      const localRadius = 52 + members.length * 3;
      node.x = communityX + Math.cos(angle) * localRadius;
      node.y = communityY + Math.sin(angle) * localRadius;
    });
  });

  documentNodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, documentNodes.length) + Math.PI / 6;
    node.x = centerX + Math.cos(angle) * radius;
    node.y = centerY + Math.sin(angle) * radius;
  });
}

function renderGraph() {
  const svg = document.getElementById("graph");
  const width = svg.clientWidth || 900;
  const height = svg.clientHeight || 650;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  layoutNodes(width, height);

  const nodeById = new Map(graphData.nodes.map((node) => [node.id, node]));
  svg.innerHTML = "";

  const linkLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const labelLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const nodeLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svg.append(linkLayer, labelLayer, nodeLayer);

  const visible = visibleSet();
  graphData.links.forEach((link) => {
    const source = nodeById.get(link.source);
    const target = nodeById.get(link.target);
    if (!source || !target) return;

    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", source.x);
    line.setAttribute("y1", source.y);
    line.setAttribute("x2", target.x);
    line.setAttribute("y2", target.y);
    line.setAttribute("class", `link ${isVisibleLink(link, visible) ? "" : "faded"}`);
    linkLayer.appendChild(line);

    if (link.predicate !== "mentions") {
      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", (source.x + target.x) / 2);
      text.setAttribute("y", (source.y + target.y) / 2);
      text.setAttribute("class", `link-label ${isVisibleLink(link, visible) ? "" : "faded"}`);
      text.textContent = link.predicate;
      labelLayer.appendChild(text);
    }
  });

  graphData.nodes.forEach((node) => {
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("class", `node ${visible.has(node.id) ? "" : "faded"}`);
    group.setAttribute("transform", `translate(${node.x}, ${node.y})`);
    group.addEventListener("click", () => {
      selectedId = node.id;
      renderDetails(node);
      renderGraph();
    });

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("r", node.type === "document" ? 9 : 11 + Math.min(7, node.weight));
    circle.setAttribute("fill", colors[node.community] || colors.community_uncategorized);
    circle.setAttribute("stroke", selectedId === node.id ? "#111" : "#fff");
    circle.setAttribute("stroke-width", selectedId === node.id ? 3 : 1.5);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", 14);
    label.setAttribute("y", 4);
    label.textContent = node.label;

    group.append(circle, label);
    nodeLayer.appendChild(group);
  });
}

function visibleSet() {
  const query = document.getElementById("searchInput").value.trim().toLowerCase();
  const kind = document.getElementById("kindFilter").value;
  const topic = document.getElementById("topicFilter").value;
  if (!query && !selectedId && !kind && !topic) {
    const hiddenGeneratedDocs = new Set(
      graphData.documents.filter((doc) => doc.hidden_by_default).map((doc) => doc.id)
    );
    return new Set(graphData.nodes.filter((node) => !hiddenGeneratedDocs.has(node.id)).map((node) => node.id));
  }

  const visible = new Set();
  const matchingDocs = new Set(
    graphData.documents
      .filter((doc) => (!kind || doc.kind === kind) && (!topic || doc.topic === topic))
      .map((doc) => doc.id)
  );

  graphData.nodes.forEach((node) => {
    const text = [node.label, node.summary, ...(node.claims || [])].join(" ").toLowerCase();
    if (query && text.includes(query)) visible.add(node.id);
    if ((kind || topic) && matchingDocs.has(node.id)) visible.add(node.id);
  });
  if (selectedId) visible.add(selectedId);

  let expanded = true;
  while (expanded) {
    expanded = false;
    graphData.links.forEach((link) => {
      if (visible.has(link.source) && !visible.has(link.target)) {
        visible.add(link.target);
        expanded = true;
      }
      if (visible.has(link.target) && !visible.has(link.source)) {
        visible.add(link.source);
        expanded = true;
      }
    });
  }
  return visible;
}

function isVisibleLink(link, visible) {
  return visible.has(link.source) && visible.has(link.target);
}

function renderDetails(node) {
  const details = document.getElementById("details");
  if (!node) {
    details.innerHTML = "<p>No node selected.</p>";
    return;
  }

  const docs = (node.documents || [])
    .map((docId) => graphData.documents.find((doc) => doc.id === docId))
    .filter(Boolean);
  const related = graphData.links
    .filter((link) => link.source === node.id || link.target === node.id)
    .slice(0, 12);

  details.innerHTML = `
    <h2>${escapeHtml(node.label)}</h2>
    <p>${escapeHtml(node.summary || node.type || "")}</p>
    ${node.kind || node.topic || node.publisher ? `<h3>Metadata</h3><p>${escapeHtml([node.kind, node.topic, node.publisher].filter(Boolean).join(" / "))}</p>` : ""}
    ${node.community ? `<h3>Community</h3><p>${escapeHtml(node.community.replace(/^community_/, "").replaceAll("_", " "))}</p>` : ""}
    ${node.formula ? `<h3>Formula</h3><p>${escapeHtml(node.formula)}</p>` : ""}
    ${node.variables ? listSection("Variables", Object.entries(node.variables).map(([key, value]) => `${key}: ${value}`)) : ""}
    ${node.url ? `<h3>Source</h3><p><a href="${node.url}" target="_blank" rel="noreferrer">${escapeHtml(node.url)}</a></p>` : ""}
    ${listSection("Claims", node.claims || [])}
    ${listSection("Related", related.map((link) => `${labelFor(link.source)} ${link.predicate} ${labelFor(link.target)}`))}
    ${listSection("Documents", docs.map((doc) => `${doc.title} (${doc.kind})`))}
  `;
}

function labelFor(id) {
  return graphData.nodes.find((node) => node.id === id)?.label || id;
}

function listSection(title, items) {
  if (!items.length) return "";
  return `<h3>${title}</h3><ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

document.getElementById("searchInput").addEventListener("input", () => renderGraph());
document.getElementById("kindFilter").addEventListener("change", () => renderGraph());
document.getElementById("topicFilter").addEventListener("change", () => renderGraph());
window.addEventListener("resize", () => renderGraph());
loadGraph().catch((error) => {
  document.getElementById("details").innerHTML = `<p>${escapeHtml(error.message)}</p>`;
});
