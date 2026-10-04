// Futsal RFFM — SPA sin dependencias. Rutas por hash:
//   #/  #/jornadas/:n  #/tabla  #/goleadores  #/partido/:id  #/yo
const $view = document.getElementById("view");
const memo = new Map();
let CONFIG = null;

// ---------- utilidades ----------------------------------------------------
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

async function api(path, { fresh = false } = {}) {
  if (!fresh && memo.has(path)) return memo.get(path);
  const p = fetch(`/api${path}`).then(async (r) => {
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.detail || `Error ${r.status}`);
    }
    return r.json();
  });
  memo.set(path, p);
  p.catch(() => memo.delete(path));
  return p;
}

const DAYS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const parseDate = (iso) => (iso ? new Date(iso + "T12:00:00") : null);
function fmtDay(iso, { long = false } = {}) {
  const d = parseDate(iso);
  if (!d) return "Fecha por confirmar";
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}${long ? " " + d.getFullYear() : ""}`;
}
function daysUntil(iso) {
  const d = parseDate(iso);
  if (!d) return null;
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  return Math.round((d - today) / 86400000);
}
function countdown(iso) {
  const n = daysUntil(iso);
  if (n == null || n < 0) return "";
  const txt = n === 0 ? "Hoy" : n === 1 ? "Mañana" : `En ${n} días`;
  return `<span class="countdown">${txt}</span>`;
}
const mapsUrl = (venue) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(venue + ", Comunidad de Madrid")}`;
const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

function crest(team, size = "") {
  const cls = `crest ${size ? "crest--" + size : ""}`;
  if (!team.crest) return `<span class="${cls} crest-ph">${esc(initials(team.short))}</span>`;
  return `<img class="${cls}" src="${esc(team.crest)}" alt="" loading="lazy" referrerpolicy="no-referrer"
    onerror="this.outerHTML='<span class=&quot;${cls} crest-ph&quot;>${esc(initials(team.short))}</span>'">`;
}
const chip = (r) => (r ? `<span class="chip-result ${r}" title="${{ G: "Victoria", E: "Empate", P: "Derrota" }[r]}">${r}</span>` : "");
const formChips = (form) => `<div class="form">${form.map(chip).join("")}</div>`;
const prettyPerson = (name) => {
  // "SANCHEZ NEGRO, ADRIAN" -> "Adrián Sánchez"  (sin tildes: la RFFM no las trae)
  if (!name) return "";
  const [last, first] = name.split(",").map((s) => s.trim());
  const cap = (s) => (s || "").toLowerCase().replace(/(^|[\s\-'])(\p{L})/gu, (m, a, b) => a + b.toUpperCase());
  return first ? `${cap(first)} ${cap(last)}` : cap(last);
};
const skeleton = (n = 3) => Array.from({ length: n }, () => '<div class="skeleton"></div>').join("");
function errorBox(err) {
  return `<div class="error card"><b>No se han podido cargar los datos</b>${esc(err.message)}<br>
    <button class="btn" onclick="location.reload()">Reintentar</button></div>`;
}

// ---------- componentes ---------------------------------------------------
function fixtureCard(m, { label, teamId } = {}) {
  const played = m.status === "played";
  const center = played
    ? `<div class="fixture__score num">${m.score.home}<span class="sep">–</span>${m.score.away}</div>
       <div class="fixture__day">${fmtDay(m.date)}</div>`
    : `<div class="fixture__when num">${esc(m.time || "--:--")}</div>
       <div class="fixture__day">${fmtDay(m.date)}</div>${countdown(m.date)}`;
  const side = (t) => `<div class="fixture__team ${t.mine ? "mine" : ""}">${crest(t, "md")}<span>${esc(t.short)}</span></div>`;
  const res = teamId && m.result ? chip(m.result) : "";
  return `
  <article class="card fixture">
    <a class="fixture__link" href="#/partido/${m.id}" aria-label="Ver partido">
      <div class="fixture__meta"><span class="tag">${esc(label || "")}</span><span>Jornada ${m.jornada} ${res}</span></div>
      <div class="fixture__teams">${side(m.home)}<div class="fixture__center">${center}</div>${side(m.away)}</div>
    </a>
    ${m.venue ? `<div class="fixture__venue"><span>${esc(m.venue)}</span><a href="${mapsUrl(m.venue)}" target="_blank" rel="noopener">Cómo llegar</a></div>` : ""}
  </article>`;
}

function matchRow(m, { showDate = false, hideDate = false, teamId = null, result = null, note = "" } = {}) {
  result = result || (teamId ? m.result : null);
  const played = m.status === "played";
  const homeWin = played && m.score.home > m.score.away;
  const awayWin = played && m.score.away > m.score.home;
  const mine = m.home.mine || m.away.mine;
  const side = (t, cls, win) =>
    `<div class="match__side ${cls} ${win ? "win" : ""} ${t.mine ? "is-mine" : ""}">
      ${cls === "home" ? `<span class="name">${esc(t.short)}</span>${crest(t)}` : `${crest(t)}<span class="name">${esc(t.short)}</span>`}
    </div>`;
  const mid = played
    ? `<div class="match__score num">${m.score.home} – ${m.score.away}</div>`
    : `<div class="match__time num">${esc(m.time || "—")}</div>`;
  const date = !hideDate && (showDate || !played) ? `<div class="match__date">${fmtDay(m.date)}</div>` : "";
  return `<a class="match ${mine && !teamId && !result ? "mine" : ""}" href="#/partido/${m.id}">
    ${side(m.home, "home", homeWin)}
    <div class="match__mid">${mid}${date}</div>
    ${side(m.away, "away", awayWin)}
    ${result ? `<span class="match__res">${chip(result)}</span>` : ""}
    ${note ? `<div class="match__note">${esc(note)}</div>` : ""}
  </a>`;
}

function standingsTable(rows, { full = false, only = null } = {}) {
  const list = only ? rows.filter((r) => only.includes(r.pos)) : rows;
  return `<table class="table ${full ? "full" : ""}">
    <thead><tr>
      <th>#</th><th class="team">Equipo</th><th>PJ</th><th class="opt">G</th><th class="opt">E</th><th class="opt">P</th>
      <th class="opt">GF</th><th class="opt">GC</th><th>DG</th><th>PTS</th>
    </tr></thead>
    <tbody>${list
      .map(
        (r) => `<tr class="${r.team.mine ? "mine" : ""}">
        <td class="pos">${r.zone ? `<i style="background:${esc(r.zone)}"></i>` : ""}${r.pos}</td>
        <td class="team"><div>${crest(r.team)}<span>${esc(r.team.short)}</span></div></td>
        <td>${r.played}</td><td class="opt">${r.won}</td><td class="opt">${r.drawn}</td><td class="opt">${r.lost}</td>
        <td class="opt">${r.gf}</td><td class="opt">${r.ga}</td>
        <td class="gd ${r.gd > 0 ? "pos-gd" : r.gd < 0 ? "neg-gd" : ""}">${r.gd > 0 ? "+" : ""}${r.gd}</td>
        <td class="pts">${r.points}</td>
      </tr>`
      )
      .join("")}</tbody></table>`;
}

// ---------- vistas ----------------------------------------------------------
async function viewHome() {
  $view.innerHTML = skeleton(3);
  const t = await api(`/team/${CONFIG.myTeam}`);
  const s = t.standing;
  let around = null;
  if (s) {
    const lo = Math.max(1, Math.min(s.pos - 2, t.totalTeams - 4));
    around = [lo, lo + 1, lo + 2, lo + 3, lo + 4];
  }
  const standings = s ? await api("/standings") : null;
  const rest = t.matches.filter((m) => m.status === "scheduled" && (!t.next || m.id !== t.next.id));
  const played = t.matches.filter((m) => m.status === "played").reverse();

  $view.innerHTML = `
    <section class="card hero">
      ${crest(t.team, "lg")}
      <div>
        <h1 class="hero__name">${esc(t.team.short)}</h1>
        <div class="hero__stats">
          ${s ? `<div class="hero__stat hero__pos"><b class="num">${s.pos}º</b><span>de ${t.totalTeams}</span></div>
                 <div class="hero__stat"><b class="num">${s.points}</b><span>puntos</span></div>
                 <div class="hero__stat"><b class="num">${s.won}-${s.drawn}-${s.lost}</b><span>G-E-P</span></div>` : ""}
        </div>
        ${t.form.length ? `<div style="margin-top:10px">${formChips(t.form)}</div>` : ""}
      </div>
    </section>

    ${t.next ? `<div class="section"><h2>Próximo partido</h2></div>${fixtureCard(t.next, { label: t.next.isHome ? "En casa" : "Fuera" })}` : ""}
    ${t.last ? `<div class="section"><h2>Último resultado</h2><a href="#/partido/${t.last.id}">Ver acta</a></div>${fixtureCard(t.last, { label: t.last.isHome ? "En casa" : "Fuera", teamId: t.team.id })}` : ""}

    ${standings && around ? `<div class="section"><h2>Clasificación · J${standings.round}</h2><a href="#/tabla">Completa</a></div>
      <div class="card">${standingsTable(standings.rows, { only: around })}</div>` : ""}

    ${played.length ? `<div class="section"><h2>Resultados</h2></div>
      <div class="card matches">${played.map((m) => matchRow(m, { showDate: true, teamId: t.team.id })).join("")}</div>` : ""}

    ${rest.length ? `<div class="section"><h2>Calendario</h2></div>
      <div class="card matches">${rest.map((m) => matchRow(m, { teamId: t.team.id })).join("")}</div>` : ""}
  `;
}

async function viewRounds(n) {
  $view.innerHTML = skeleton(4);
  const cal = await api("/calendar");
  const num = Number(n) || cal.currentRound;
  const round = cal.rounds.find((r) => r.number === num) || cal.rounds[0];
  const done = (r) => r.matches.every((m) => m.status === "played");

  // agrupar por día
  const groups = [];
  for (const m of round.matches) {
    const key = m.date || "zz";
    let g = groups.find((x) => x.key === key);
    if (!g) groups.push((g = { key, items: [] }));
    g.items.push(m);
  }

  $view.innerHTML = `
    <nav class="rounds" id="rounds">
      ${cal.rounds
        .map((r) => {
          const d = parseDate(r.date);
          return `<a href="#/jornadas/${r.number}" class="${r.number === round.number ? "active" : ""} ${done(r) ? "done" : ""}">
            ${r.number}<small>${d ? `${d.getDate()}/${d.getMonth() + 1}` : ""}</small></a>`;
        })
        .join("")}
    </nav>
    <div class="round-head"><h1>Jornada ${round.number}</h1><span>${round.date ? fmtDay(round.date, { long: true }) : ""}</span></div>
    <div class="card matches">
      ${groups.map((g) => `<div class="daygroup">${g.key === "zz" ? "Sin fecha" : fmtDay(g.key)}</div>${g.items.map((m) => matchRow(m, { hideDate: true })).join("")}`).join("")}
    </div>`;
  document.querySelector("#rounds a.active")?.scrollIntoView({ inline: "center", block: "nearest" });
}

let tableFull = false;
async function viewTable() {
  $view.innerHTML = skeleton(4);
  const st = await api("/standings");
  const render = () => {
    $view.innerHTML = `
      <div class="table-tools">
        <h1>Clasificación</h1>
        <div class="seg" role="group" aria-label="Columnas">
          <button data-full="0" class="${tableFull ? "" : "on"}">Corta</button>
          <button data-full="1" class="${tableFull ? "on" : ""}">Completa</button>
        </div>
      </div>
      <p class="muted" style="margin:-4px 0 10px;font-size:13px">Tras la jornada ${st.round}${st.roundDate ? " · " + fmtDay(st.roundDate) : ""}</p>
      <div class="card">${standingsTable(st.rows, { full: tableFull })}</div>
      ${st.rows.length ? `<div class="legend">${st.zones.length
        ? st.zones.map((z) => `<span><i style="background:${esc(z.color)}"></i>${esc(z.label || "")}</span>`).join("")
        : [...new Set(st.rows.filter((r) => r.zone).map((r) => r.zone))].length
          ? `<span><i style="background:#55FFFE"></i>Ascenso</span><span><i style="background:#FF491C"></i>Descenso</span>` : ""}</div>` : ""}
      <h2 class="section" style="display:block"><span style="font:700 15px var(--display);text-transform:uppercase;letter-spacing:.08em;color:var(--muted)">Racha</span></h2>
      <div class="card">${st.rows
        .map((r) => `<div class="match" style="grid-template-columns:28px 1fr auto"><span class="num muted">${r.pos}</span>
          <div class="match__side ${r.team.mine ? "is-mine" : ""}">${crest(r.team)}<span class="name">${esc(r.team.short)}</span></div>${formChips(r.form.slice(-5))}</div>`)
        .join("")}</div>`;
    $view.querySelectorAll(".seg button").forEach((b) =>
      b.addEventListener("click", () => {
        tableFull = b.dataset.full === "1";
        render();
      })
    );
  };
  render();
}

let scorersFilter = "all";
async function viewScorers() {
  $view.innerHTML = skeleton(4);
  const list = await api("/scorers");
  const render = () => {
    const rows = scorersFilter === "mine" ? list.filter((s) => s.team.mine) : list;
    let rank = 0, prev = null;
    $view.innerHTML = `
      <div class="table-tools">
        <h1>Goleadores</h1>
        <div class="seg">
          <button data-f="all" class="${scorersFilter === "all" ? "on" : ""}">Todos</button>
          <button data-f="mine" class="${scorersFilter === "mine" ? "on" : ""}">Mi equipo</button>
        </div>
      </div>
      <div class="card">${rows.length
        ? rows.map((s, i) => {
            if (s.goals !== prev) { rank = i + 1; prev = s.goals; }
            return `<div class="scorer ${s.me ? "mine" : ""} ${rank === 1 ? "top" : ""}">
              <span class="scorer__rank">${rank}</span>${crest(s.team)}
              <div><div class="scorer__name">${esc(prettyPerson(s.name))}</div><div class="scorer__team">${esc(s.team.short)} · ${s.played} PJ${s.penalties ? ` · ${s.penalties} de penalti` : ""}</div></div>
              <div class="scorer__goals"><b>${s.goals}</b><small>${s.perGame.toFixed(2)}/p</small></div>
            </div>`;
          }).join("")
        : '<div class="empty">Sin goles todavía</div>'}</div>`;
    $view.querySelectorAll(".seg button").forEach((b) =>
      b.addEventListener("click", () => { scorersFilter = b.dataset.f; render(); })
    );
  };
  render();
}

const GOAL_SVG = `<svg class="ico-goal" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="currentColor" opacity=".9"/><path d="M12 7l3.8 2.8-1.5 4.4H9.7L8.2 9.8z" fill="var(--surface)"/></svg>`;
async function viewMatch(id) {
  $view.innerHTML = skeleton(3);
  let a;
  try {
    a = await api(`/match/${id}`);
  } catch (e) {
    // Partido aún sin acta: mostramos lo que dice el calendario
    const cal = await api("/calendar");
    const m = cal.rounds.flatMap((r) => r.matches).find((x) => x.id === id);
    if (!m) throw e;
    $view.innerHTML = `<button class="back" onclick="history.back()">← Volver</button>${fixtureCard(m, { label: "Pendiente" })}
      <p class="empty">El acta estará disponible cuando se juegue el partido.</p>`;
    return;
  }
  const meId = CONFIG.myPlayer;
  const evRow = (e) => {
    const ico = e.type === "goal" ? GOAL_SVG : `<span class="ico-card ${e.type}"></span>`;
    const who = `<span class="lbl ${e.playerId === meId ? "me" : ""}">${esc(prettyPerson(e.player))}${e.ownGoal ? " (p.p.)" : ""}</span>`;
    const home = e.side === "home" ? `<div class="ev__who home">${who}${ico}</div>` : "<div></div>";
    const away = e.side === "away" ? `<div class="ev__who">${ico}${who}</div>` : "<div></div>";
    return `<div class="ev">${home}<div class="ev__min">${e.minute != null ? e.minute + "'" : ""}</div>${away}</div>`;
  };
  let events = "";
  let halfDone = false;
  for (const e of a.events) {
    if (!halfDone && e.minute != null && e.minute > 20) {
      events += `<div class="half">Descanso</div>`;
      halfDone = true;
    }
    events += evRow(e);
  }
  const lineup = (side, team) => {
    const l = a.lineups[side];
    const p = (x) => `<div class="player ${x.starter ? "starter" : ""} ${x.me ? "me" : ""}">
      <span class="dorsal">${x.number ?? ""}</span><span>${esc(prettyPerson(x.name))}${x.goalkeeper ? '<span class="badge">POR</span>' : ""}${x.captain ? '<span class="badge">C</span>' : ""}</span></div>`;
    const starters = l.players.filter((x) => x.starter), bench = l.players.filter((x) => !x.starter);
    return `<div class="lineup"><h3>${esc(team.short)}</h3>
      ${starters.map(p).join("")}
      ${bench.length ? `<div class="bench">${bench.map(p).join("")}</div>` : ""}
      ${l.coach ? `<div class="staff">Entrenador: ${esc(prettyPerson(l.coach))}</div>` : ""}</div>`;
  };
  const center = a.score
    ? `<div class="fixture__score num">${a.score.home}<span class="sep">–</span>${a.score.away}</div>`
    : `<div class="fixture__when num">${esc(a.time || "--:--")}</div>`;
  const side = (t) => `<div class="fixture__team ${t.mine ? "mine" : ""}">${crest(t, "md")}<span>${esc(t.short)}</span></div>`;

  $view.innerHTML = `
    <button class="back" onclick="history.length > 1 ? history.back() : (location.hash = '#/')">← Volver</button>
    <section class="card scoreboard">
      <div class="fixture__meta"><span class="tag">${a.live ? "En juego" : a.suspended ? "Suspendido" : a.closed ? "Final" : a.score ? "Acta abierta" : "Pendiente"}</span><span>Jornada ${a.jornada ?? ""}</span></div>
      <div class="fixture__teams">${side(a.home)}<div class="fixture__center">${center}<div class="fixture__day">${fmtDay(a.date)}${a.time ? " · " + esc(a.time) : ""}</div></div>${side(a.away)}</div>
      ${a.penalties ? `<p class="muted">Penaltis: ${a.penalties.home} – ${a.penalties.away}</p>` : ""}
      ${!a.score && !a.live ? `<div style="margin-top:8px">${countdown(a.date)}</div>` : ""}
    </section>
    ${!a.score && !a.live && !a.events.length ? `<p class="empty">Las alineaciones y los goles aparecerán aquí cuando se cierre el acta.</p>` : ""}

    ${a.events.length ? `<div class="section"><h2>Partido</h2></div><div class="card timeline">${events}</div>` : ""}

    ${a.lineups.home.players.length || a.lineups.away.players.length
      ? `<div class="section"><h2>Alineaciones</h2></div><div class="card lineups">${lineup("home", a.home)}${lineup("away", a.away)}</div>` : ""}

    <div class="section"><h2>Datos</h2></div>
    <dl class="card info-list">
      ${a.venue ? `<div><dt>Pabellón</dt><dd><a href="${mapsUrl(a.venue)}" target="_blank" rel="noopener" style="color:var(--accent)">${esc(a.venue)}</a></dd></div>` : ""}
      ${a.referees.map((r) => `<div><dt>${esc(r.role)}</dt><dd>${esc(prettyPerson(r.name))}</dd></div>`).join("")}
    </dl>`;
}

async function viewMe() {
  if (!CONFIG.myPlayer) {
    $view.innerHTML = `<div class="empty card">Configura <code>MI_JUGADOR</code> en el .env para ver tus números.</div>`;
    return;
  }
  $view.innerHTML = skeleton(3);
  const me = await api("/me");
  const t = me.totals;
  const last = me.games[0];
  const nums = [...new Set(me.games.map((g) => g.number).filter(Boolean))];
  const avg = t.gkGames ? (t.conceded / t.gkGames).toFixed(1) : "–";
  const stat = (v, l, hl = false) => `<div class="card stat ${hl ? "hl" : ""}"><b class="num">${v}</b><span>${l}</span></div>`;
  $view.innerHTML = `
    <section class="card me-head">
      <div class="me-num">${nums[0] ?? "–"}</div>
      <div><h1>${esc(prettyPerson(me.name) || "Mis números")}</h1>
      <p>${last && last.goalkeeper ? "Portero · " : ""}${esc(last ? (last.match.home.mine ? last.match.home.short : last.match.away.short) : "")}</p></div>
    </section>
    <div class="section"><h2>Temporada</h2></div>
    <div class="stats">
      ${stat(t.called, "Convocatorias")}
      ${stat(t.starts, "Titular", true)}
      ${stat(`${t.wins}-${t.draws}-${t.losses}`, "G-E-P")}
      ${t.gkGames ? stat(t.conceded, "Encajados") + stat(avg, "Por partido") + stat(t.cleanSheets, "Porterías a 0", true) : ""}
      ${stat(t.goals, "Goles")}
      ${stat(t.yellow, "Amarillas")}
      ${stat(t.red, "Rojas")}
    </div>
    ${t.gkGames ? `<p class="note">Goles encajados contados en los partidos que empezaste de titular (el acta no indica minutos jugados).</p>` : ""}
    ${me.games.length ? `<div class="section"><h2>Partido a partido</h2></div>
      <div class="card matches">${me.games
        .map((g) => {
          const extra = [
            g.starter ? "Titular" : "Suplente",
            g.conceded != null ? `${g.conceded} encajado${g.conceded === 1 ? "" : "s"}` : "",
            g.goals ? `${g.goals} gol${g.goals > 1 ? "es" : ""}` : "",
            ...g.cards.map((c) => ({ yellow: "Amarilla", red: "Roja", second_yellow: "Doble amarilla" })[c]),
          ].filter(Boolean).join(" · ");
          return matchRow(g.match, { showDate: true, result: g.result, note: extra });
        })
        .join("")}</div>` : '<div class="empty">Aún no apareces en ningún acta.</div>'}`;
}

// ---------- router ----------------------------------------------------------
const routes = [
  [/^#?\/?$/, "inicio", viewHome],
  [/^#\/jornadas(?:\/(\d+))?$/, "jornadas", viewRounds],
  [/^#\/tabla$/, "tabla", viewTable],
  [/^#\/goleadores$/, "goleadores", viewScorers],
  [/^#\/partido\/(\d+)$/, null, viewMatch],
  [/^#\/yo$/, "yo", viewMe],
];

async function route() {
  const hash = location.hash || "#/";
  for (const [re, tab, fn] of routes) {
    const m = hash.match(re);
    if (!m) continue;
    if (tab) document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
    window.scrollTo({ top: 0 });
    try {
      await fn(m[1]);
    } catch (err) {
      console.error(err);
      $view.innerHTML = errorBox(err);
    }
    return;
  }
  location.hash = "#/";
}

document.getElementById("refresh").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.classList.add("spin");
  try {
    await fetch("/api/refresh", { method: "POST" });
    memo.clear();
    await route();
  } finally {
    btn.classList.remove("spin");
  }
});

async function init() {
  try {
    CONFIG = await api("/config");
  } catch (e) {
    $view.innerHTML = errorBox(e);
    return;
  }
  if (!CONFIG.myPlayer) document.getElementById("tab-yo").classList.add("hidden");
  api("/calendar")
    .then((c) => {
      document.getElementById("comp").textContent = c.competition || "Competición";
      document.getElementById("group").textContent = c.group || "";
    })
    .catch(() => {});
  window.addEventListener("hashchange", route);
  route();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
}
init();
