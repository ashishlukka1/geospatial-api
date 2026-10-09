/* Iteration 3.5 viewer: vanilla JS, talks only to the real API. */
const form = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const statusEl = document.getElementById("upload-status");
const metaEl = document.getElementById("file-meta");
const tbody = document.querySelector("#measure-table tbody");
const activityEl = document.getElementById("activity");

const map = L.map("map").setView([20.59, 78.96], 5);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);
let geoLayer = null;

function log(method, url, status, extra = "") {
  const li = document.createElement("li");
  li.textContent = `${method} ${url} -> ${status}${extra ? " " + extra : ""}`;
  activityEl.prepend(li);
}

function setStatus(text, cls = "") {
  statusEl.textContent = text;
  statusEl.className = `status ${cls}`;
}

function fmtMeasurement(m) {
  if (!m) return ["—", "—", "—"];
  return [m.type ?? "—", m.value ?? "—", m.unit ?? "—"];
}

function renderTable(features) {
  tbody.innerHTML = "";
  for (const f of features) {
    const [mType, mValue, mUnit] = fmtMeasurement(f.measurement);
    const tr = document.createElement("tr");
    const cells = [
      f.feature_index,
      f.geometry_type ?? "—",
      f.crs ?? "—",
      f.projected_crs ?? "null",
      mType === "—" ? "null" : mType,
      mValue,
      mUnit,
    ];
    for (const c of cells) {
      const td = document.createElement("td");
      td.textContent = c;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function popupHtml(f) {
  const [mType, mValue, mUnit] = fmtMeasurement(f.measurement);
  const props = Object.entries(f.properties || {})
    .map(([k, v]) => `${k}: ${v ?? "null"}`)
    .join("<br>");
  return `<b>#${f.feature_index} ${f.geometry_type ?? ""}</b><br>${props}<br>measurement: ${mType} ${mValue} ${mUnit}`;
}

function renderMap(features) {
  if (geoLayer) map.removeLayer(geoLayer);
  const gj = {
    type: "FeatureCollection",
    features: features
      .filter((f) => f.geometry)
      .map((f) => ({
        type: "Feature",
        geometry: f.geometry,
        properties: { ...f.properties, _index: f.feature_index, _type: f.geometry_type },
      })),
  };
  geoLayer = L.geoJSON(gj, {
    style: (feat) =>
      feat.geometry.type.includes("Polygon")
        ? { color: "blue", weight: 2 }
        : { color: "orange", weight: 3 },
    pointToLayer: (feat, latlng) =>
      L.circleMarker(latlng, { radius: 6, color: "red", fillOpacity: 0.9 }),
    onEachFeature: (feat, layer) => {
      const orig = features.find((f) => f.feature_index === feat.properties._index);
      if (orig) layer.bindPopup(popupHtml(orig));
    },
  }).addTo(map);
  if (geoLayer.getBounds().isValid()) map.fitBounds(geoLayer.getBounds().pad(0.2));
}

async function fetchJson(method, url, body) {
  const res = await fetch(url, body);
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  log(method, url, res.status);
  if (!res.ok) throw new Error((data && data.detail) || `HTTP ${res.status}`);
  return data;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) {
    setStatus("Select a .kml file first.", "err");
    return;
  }
  setStatus(`Uploading ${file.name} ...`, "loading");
  try {
    const fd = new FormData();
    fd.append("file", file, file.name);
    const uploaded = await fetchJson("POST", "/api/files/", { method: "POST", body: fd });
    setStatus(`Uploaded. file_id=${uploaded.id}`, "ok");
    const info = await fetchJson("GET", `/api/files/${uploaded.id}/`);
    metaEl.textContent = JSON.stringify(info, null, 2);
    const meas = await fetchJson("GET", `/api/files/${uploaded.id}/measurements/`);
    renderTable(meas.features);
    renderMap(meas.features);
    setStatus(`Done. ${meas.features.length} features shown.`, "ok");
  } catch (err) {
    setStatus(`Error: ${err.message}`, "err");
    log("ERROR", "", "", String(err.message));
  }
});
