/* Iteration 3.5 viewer: vanilla JS, talks only to the real API. */
const form = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const uploadBtn = document.getElementById("upload-btn");
const statusEl = document.getElementById("upload-status");
const metaEl = document.getElementById("file-meta");
const tbody = document.querySelector("#measure-table tbody");
const activityEl = document.getElementById("activity");
const fileNameEl = document.getElementById("file-name");
const PLACEHOLDER_ROW = '<tr><td colspan="7" class="muted">No data yet.</td></tr>';
const FILE_PROMPT = "No file selected (.kml or .zip)";

fileInput.addEventListener("change", () => {
  fileNameEl.textContent = fileInput.files[0] ? fileInput.files[0].name : FILE_PROMPT;
});

window.addEventListener("resize", () => map.invalidateSize());

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

function shortCrs(value) {
  if (value == null || value === "") return "—";
  const text = String(value);
  return text.length <= 24 ? text : "Custom CRS";
}

function metaRow(label, value) {
  const text = value == null || value === "" ? "—" : String(value);
  const row = document.createElement("div");
  row.className = "meta-row";
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = text;
  dd.title = text;
  row.appendChild(dt);
  row.appendChild(dd);
  return row;
}

function renderMeta(info) {
  metaEl.innerHTML = "";
  const grid = document.createElement("dl");
  grid.className = "meta-grid";
  if (!info || typeof info !== "object") {
    grid.appendChild(metaRow("Status", "No file uploaded yet."));
  } else {
    const order = ["id", "filename", "status", "feature_count", "crs"];
    for (const key of order) {
      if (key in info) grid.appendChild(metaRow(key, info[key]));
    }
    for (const key of Object.keys(info)) {
      if (!order.includes(key)) grid.appendChild(metaRow(key, info[key]));
    }
  }
  metaEl.appendChild(grid);
}

function renderTable(features) {
  tbody.innerHTML = "";
  if (!Array.isArray(features) || features.length === 0) {
    tbody.innerHTML = PLACEHOLDER_ROW;
    return;
  }
  for (const f of features) {
    const [mType, mValue, mUnit] = fmtMeasurement(f.measurement);
    const tr = document.createElement("tr");
    const cells = [
      [f.feature_index, null],
      [f.geometry_type ?? "—", null],
      [shortCrs(f.crs), f.crs == null ? null : String(f.crs)],
      [f.projected_crs == null ? "null" : shortCrs(f.projected_crs),
       f.projected_crs == null ? null : String(f.projected_crs)],
      [mType === "—" ? "null" : mType, null],
      [mValue, null],
      [mUnit, null],
    ];
    for (const [display, full] of cells) {
      const td = document.createElement("td");
      td.textContent = display;
      td.title = full ?? String(display);
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

function isRenderableGeometry(g) {
  return (
    g &&
    typeof g.type === "string" &&
    Array.isArray(g.coordinates) &&
    g.coordinates.length > 0
  );
}

function renderMap(features) {
  if (geoLayer) {
    map.removeLayer(geoLayer);
    geoLayer = null;
  }
  if (!Array.isArray(features) || features.length === 0) return 0;
  const renderable = features.filter((f) => isRenderableGeometry(f.display_geometry || f.geometry));
  const skipped = features.length - renderable.length;
  const gj = {
    type: "FeatureCollection",
    features: renderable.map((f) => ({
      type: "Feature",
      geometry: f.display_geometry || f.geometry,
      properties: { ...f.properties, _index: f.feature_index, _type: f.geometry_type },
    })),
  };
  try {
    const layer = L.geoJSON(gj, {
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
    });
    layer.addTo(map);
    geoLayer = layer;
  } catch (err) {
    log("MAP", "render", "error", String(err && err.message ? err.message : err));
    return -1;
  }
  if (geoLayer.getBounds().isValid()) map.fitBounds(geoLayer.getBounds().pad(0.2));
  map.invalidateSize();
  return skipped;
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
    setStatus("Select a .kml or .zip file first.", "err");
    return;
  }
  // Clear stale results so a failed upload never looks successful.
  renderMeta(null);
  tbody.innerHTML = PLACEHOLDER_ROW;
  if (geoLayer) {
    map.removeLayer(geoLayer);
    geoLayer = null;
  }
  uploadBtn.disabled = true;
  setStatus(`Uploading ${file.name} ...`, "loading");
  try {
    const fd = new FormData();
    fd.append("file", file, file.name);
    const uploaded = await fetchJson("POST", "/api/files/", { method: "POST", body: fd });
    setStatus(`Uploaded. file_id=${uploaded.id}`, "ok");
    const info = await fetchJson("GET", `/api/files/${uploaded.id}/`);
    renderMeta(info);
    const meas = await fetchJson("GET", `/api/files/${uploaded.id}/measurements/`);
    renderTable(meas.features);
    const skipped = renderMap(meas.features);
    if (skipped === -1) {
      setStatus(`Done with map error. ${meas.features.length} features listed; map render failed.`, "err");
    } else if (skipped > 0) {
      setStatus(`Done. ${meas.features.length} features shown, ${skipped} without usable map geometry.`, "ok");
    } else {
      setStatus(`Done. ${meas.features.length} features shown.`, "ok");
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, "err");
    log("ERROR", "", "", String(err.message));
  } finally {
    uploadBtn.disabled = false;
  }
});
