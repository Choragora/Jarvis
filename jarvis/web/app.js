"use strict";
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let state = null,
  socket = null,
  diagnostics = null;
const streaming = new Map();
const statusNames = {
  waiting: "À espera",
  running: "Em execução",
  completed: "Concluída",
  failed: "Falhou",
  cancelled: "Cancelada",
  unverified: "Por verificar",
  blocked: "Bloqueada",
};
const actionNames = {
  memory_save: "Guardar memória",
  memory_search: "Pesquisar memória",
  app_open: "Abrir aplicação",
  file_create: "Criar ficheiro",
  file_read: "Ler ficheiro",
  desktop_observe: "Observar desktop",
  screen_capture: "Capturar ecrã",
  routine_create: "Criar rotina",
  window_move: "Mover janela",
  window_focus: "Focar janela",
  window_read: "Ler janela",
  window_type: "Escrever na janela",
  workflow: "Executar rotina",
};
function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
function button(text, fn, cls = "secondary-button") {
  const b = el("button", text, cls);
  b.type = "button";
  b.addEventListener("click", () => Promise.resolve(fn()).catch(error));
  return b;
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $("#toast").classList.add("hidden"), 7000);
}
function error(e) {
  toast(e.message || String(e));
}
async function api(path, options = {}) {
  const response = await fetch("/api/" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    let d;
    try {
      d = await response.json();
    } catch {
      d = { detail: "O serviço local não respondeu." };
    }
    throw new Error(
      typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail),
    );
  }
  return response.json();
}
const post = (path, data = {}) =>
  api(path, { method: "POST", body: JSON.stringify(data) });
function view(name) {
  $$(".view").forEach((v) =>
    v.classList.toggle("active", v.id === "view-" + name),
  );
  $$(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === name),
  );
  const nav = $('.nav-item[data-view="' + name + '"]');
  $("#page-name").textContent = nav?.textContent.trim() || name;
  if (name === "diagnostics") refreshDiagnostics().catch(error);
  if (name === "memory") refreshNotes().catch(error);
  if (name === "routines") refreshRoutines().catch(error);
  if (name === "screens") refreshDesktop().catch(error);
  if (name === "settings") refreshDevices().catch(error);
}
$$("[data-view]").forEach((b) =>
  b.addEventListener("click", () => {
    document.body.classList.remove("menu-open");
    view(b.dataset.view);
  }),
);
function setStatus(status) {
  const names = {
    ready: [
      "Estou aqui para ajudar.",
      "Escreva um pedido ou ative o microfone para começar.",
      "DISPONÍVEL",
    ],
    listening: [
      "Estou a ouvir.",
      "Com auscultadores, pode interromper-me enquanto falo.",
      "A OUVIR",
    ],
    thinking: [
      "A tratar do seu pedido.",
      "As ações só são concluídas depois de verificadas.",
      "A INTERPRETAR",
    ],
    speaking: [
      "Aqui está a minha resposta.",
      "Reprodução SAPI em curso no Windows.",
      "A FALAR",
    ],
    paused: [
      "Ao seu comando. Em pausa.",
      "Nenhuma nova ação será iniciada até retomar.",
      "EM PAUSA",
    ],
    error: [
      "Precisamos de um pequeno ajuste.",
      "Consulte o erro na conversa ou abra o diagnóstico.",
      "COM ERRO",
    ],
  };
  const s = names[status] || names.ready;
  $("#orb").className = "orb " + status;
  $("#assistant-status").textContent = s[0];
  $("#assistant-hint").textContent = s[1];
  $("#status-caption").textContent = s[2];
}
function addMessage(message) {
  if ($("#messages .empty-message")) $("#messages").replaceChildren();
  const article = el("div", undefined, "message " + message.role);
  article.dataset.message = message.id;
  article.append(
    el(
      "span",
      message.role === "user"
        ? "VOCÊ"
        : message.role === "error"
          ? "DIAGNÓSTICO"
          : "JARVIS",
      "role",
    ),
    el("span", message.text, "message-text"),
  );
  $("#messages").append(article);
  $("#messages").scrollTop = $("#messages").scrollHeight;
  return article;
}
function renderTasks(tasks) {
  $("#tasks").replaceChildren();
  $("#task-count").textContent = tasks.length;
  if (!tasks.length) {
    const empty = el("div", undefined, "task-empty");
    empty.append(el("span", "◇"), el("div", "Sem tarefas por agora."));
    $("#tasks").append(empty);
    return;
  }
  for (const task of tasks.slice(0, 8)) {
    const card = el("div", undefined, "task");
    card.append(
      el("strong", actionNames[task.action] || task.action),
      el("small", statusNames[task.status] || task.status),
    );
    if (["running", "waiting"].includes(task.status))
      card.append(
        button("Cancelar", () => post("tasks/" + task.id + "/cancel")),
      );
    if (task.result) {
      try {
        const result =
          typeof task.result === "string"
            ? JSON.parse(task.result)
            : task.result;
        if (result?.error) card.append(el("small", " · " + result.error));
      } catch {}
    }
    $("#tasks").append(card);
  }
}
function renderAccount(codex) {
  const connected = codex?.account?.type === "chatgpt";
  $("#codex-label").textContent = connected ? "Conta ligada" : "Por configurar";
  $("#account-detail").textContent = connected
    ? "ChatGPT · " +
      (codex.account.planType || "Plano não indicado") +
      " · " +
      codex.version
    : "Conta por ligar · " + (codex?.version || "Codex ainda não iniciado");
  const select = $("#codex-model");
  const chosen = state?.settings.codex_model || "";
  select.replaceChildren(new Option("Predefinido do catálogo", ""));
  for (const m of codex?.models || []) {
    const verified = codex.verified_models?.includes(m.model);
    select.add(
      new Option(
        m.displayName + (verified ? " · verificado" : " · por testar"),
        m.model,
      ),
    );
  }
  select.value = chosen;
}
async function refreshState() {
  state = await api("state");
  $("#note-count").textContent = state.notes.length;
  $("#stt-label").textContent = state.audio.loaded
    ? "Modelo preparado"
    : "Não preparado";
  $("#messages").replaceChildren();
  if (!state.messages.length) {
    const e = el("div", "O seu próximo pedido começa aqui.", "empty-message");
    e.append(
      el("small", "Experimente guardar uma nota ou preparar o seu dia."),
    );
    $("#messages").append(e);
  } else state.messages.forEach(addMessage);
  renderTasks(state.tasks);
  renderAccount(state.codex);
  fillSettings();
  $("#resume").classList.toggle("hidden", !state.stopped);
  $("#resume-header").classList.toggle("hidden", !state.stopped);
  setStatus(state.stopped ? "paused" : "ready");
}
function fillSettings() {
  const s = state.settings;
  $("#stt-model").value = s.stt_model;
  $("#stt-device").value = s.stt_device;
  $("#endpoint-ms").value = s.endpoint_ms;
  $("#headphones").checked = s.headphones_confirmed;
  $("#speech-enabled").checked = s.speech_enabled;
  $("#desktop-actions").checked = s.desktop_actions;
  $("#screen-capture").checked = s.screen_capture;
  $("#screen-send").checked = s.screen_send;
  $("#reduce-motion").checked = s.reduce_motion;
  $("#allowed-folders").value = s.allowed_folders.join("\n");
  $("#excluded-titles").value = s.excluded_titles.join("\n");
  $("#hidden-regions").value = JSON.stringify(s.hidden_regions);
  $("#tts-provider").value = s.tts_provider;
  $("#online-costs").checked = s.online_costs_accepted;
  $("#fish-model").value = s.fish_model || "";
  $("#fish-voice").value = s.fish_voice || "";
  $("#openai-model").value = s.openai_audio_model || "";
  $("#openai-voice").value = s.openai_voice || "";
  $("#brain-provider").value = s.brain_provider;
  $("#local-model").value = s.local_model || "";
  document.body.classList.toggle("reduced-motion", s.reduce_motion);
}
async function refreshDevices() {
  const [devices, voices] = await Promise.all([
    api("audio/devices"),
    api("audio/voices"),
  ]);
  $("#microphone").replaceChildren(new Option("Predefinido do sistema", ""));
  for (const d of devices.devices)
    if (d.inputs > 0) $("#microphone").add(new Option(d.name, String(d.id)));
  $("#microphone").value =
    state.settings.microphone === null ? "" : String(state.settings.microphone);
  $("#sapi-voice").replaceChildren(
    new Option("Automática · preferir pt-PT", ""),
  );
  for (const v of voices.voices) $("#sapi-voice").add(new Option(v.name, v.id));
  $("#sapi-voice").value = state.settings.sapi_voice || "";
  $("#audio-details").textContent = [devices.error, voices.error]
    .filter(Boolean)
    .join(" · ");
}
$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const settings = {
      ...state.settings,
      stt_model: $("#stt-model").value,
      stt_device: $("#stt-device").value,
      endpoint_ms: Number($("#endpoint-ms").value),
      microphone:
        $("#microphone").value === "" ? null : Number($("#microphone").value),
      sapi_voice: $("#sapi-voice").value || null,
      headphones_confirmed: $("#headphones").checked,
      speech_enabled: $("#speech-enabled").checked,
      tts_provider: $("#tts-provider").value,
      online_costs_accepted: $("#online-costs").checked,
      fish_model: $("#fish-model").value || null,
      fish_voice: $("#fish-voice").value || null,
      openai_audio_model: $("#openai-model").value || null,
      openai_voice: $("#openai-voice").value || null,
      brain_provider: $("#brain-provider").value,
      local_model: $("#local-model").value || null,
      desktop_actions: $("#desktop-actions").checked,
      screen_capture: $("#screen-capture").checked,
      screen_send: $("#screen-send").checked,
      reduce_motion: $("#reduce-motion").checked,
      allowed_folders: $("#allowed-folders")
        .value.split("\n")
        .map((x) => x.trim())
        .filter(Boolean),
      excluded_titles: $("#excluded-titles")
        .value.split("\n")
        .map((x) => x.trim())
        .filter(Boolean),
      hidden_regions: JSON.parse($("#hidden-regions").value || "[]"),
    };
    await api("settings", { method: "PUT", body: JSON.stringify(settings) });
    state.settings = settings;
    document.body.classList.toggle("reduced-motion", settings.reduce_motion);
    $("#saved-status").textContent = "Guardado no seu PC.";
    toast(
      "Definições guardadas. Microfone desligado para aplicar a configuração.",
    );
  } catch (e) {
    error(e);
  }
});
$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#chat-input").value.trim();
  if (!text) return;
  $("#chat-input").value = "";
  try {
    await post("chat", { text });
  } catch (e) {
    error(e);
  }
});
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("#chat-form").requestSubmit();
  }
});
$$("[data-prompt]").forEach((b) =>
  b.addEventListener("click", () => {
    $("#chat-input").value = b.dataset.prompt;
    $("#chat-form").requestSubmit();
  }),
);
$("#stop").addEventListener("click", () => post("stop").catch(error));
$("#resume").addEventListener("click", async () => {
  await post("resume");
  $("#resume").classList.add("hidden");
  $("#resume-header").classList.add("hidden");
  setStatus("ready");
});
$("#menu").addEventListener("click", () =>
  document.body.classList.toggle("menu-open"),
);
$("#compact").addEventListener("click", () => {
  const compact = document.body.classList.toggle("compact");
  if (window.pywebview?.api) window.pywebview.api.compact(compact);
});
$("#resume-header").addEventListener("click", () => $("#resume").click());
$("#auxiliary").addEventListener("click", () => {
  if (window.pywebview?.api) window.pywebview.api.auxiliary();
  else toast("O painel auxiliar está disponível na aplicação desktop Windows.");
});
let pttStarting = null,
  pttActive = false;
$("#ptt").addEventListener("pointerdown", (e) => {
  e.preventDefault();
  $("#ptt").setPointerCapture(e.pointerId);
  pttActive = true;
  $("#ptt").classList.add("active");
  pttStarting = post("audio/start", { mode: "ptt" })
    .then(() => setStatus("listening"))
    .catch((e) => {
      pttActive = false;
      error(e);
    });
});
async function finishPTT() {
  if (!pttActive) return;
  pttActive = false;
  $("#ptt").classList.remove("active");
  await pttStarting;
  await post("audio/finish").catch(error);
}
$("#ptt").addEventListener("pointerup", finishPTT);
$("#ptt").addEventListener("pointercancel", finishPTT);
$("#listen").addEventListener("click", async () => {
  try {
    if (state.audio.listening) {
      await post("audio/stop");
      state.audio.listening = false;
    } else {
      await post("audio/start", { mode: "hands_free" });
      state.audio.listening = true;
    }
    $("#listen").textContent = state.audio.listening
      ? "Desligar microfone"
      : "Ativar mãos livres";
  } catch (e) {
    error(e);
  }
});
$("#prepare-audio").addEventListener("click", async () => {
  toast(
    "A preparar o modelo selecionado. Guarde alterações antes de preparar.",
  );
  try {
    await post("audio/prepare");
    $("#stt-label").textContent = "Modelo preparado";
    toast("Reconhecimento local preparado.");
  } catch (e) {
    error(e);
  }
});
$("#test-voice").addEventListener("click", () =>
  post("audio/test", {
    provider: $("#tts-provider").value,
    sapi_voice: $("#sapi-voice").value || null,
  })
    .then((result) =>
      toast(
        result.voice
          ? "Teste enviado à voz " +
              result.voice.name +
              ". Confirme se ouviu a frase. A seleção só fica guardada em Guardar definições."
          : "Teste enviado ao fornecedor configurado. Confirme se ouviu a frase.",
      ),
    )
    .catch(error),
);
$("#connect").addEventListener("click", () =>
  post("codex/connect")
    .then((c) => {
      state.codex = c;
      renderAccount(c);
      toast(
        c.account ? "Estado da conta atualizado." : "Conclua o login ChatGPT.",
      );
    })
    .catch(error),
);
$("#login").addEventListener("click", async () => {
  try {
    const result = await post("codex/login");
    if (result.authUrl) {
      const link = $("#login-link");
      const url = new URL(result.authUrl);
      if (!["http:", "https:"].includes(url.protocol))
        throw new Error("URL de autenticação inválido.");
      link.href = url.href;
      link.classList.remove("hidden");
      window.open(url.href, "_blank", "noopener");
      toast(
        "Conclua o login no browser. O estado será atualizado após confirmação do Codex.",
      );
    }
  } catch (e) {
    error(e);
  }
});
$("#cancel-login").addEventListener("click", () =>
  post("codex/login/cancel")
    .then(() => {
      $("#login-link").classList.add("hidden");
      toast("Login cancelado.");
    })
    .catch(error),
);
$("#logout").addEventListener("click", () =>
  post("codex/logout")
    .then(() => {
      state.codex = {};
      renderAccount({});
      toast("Sessão terminada. A memória local foi preservada.");
    })
    .catch(error),
);
$("#test-codex").addEventListener("click", () => {
  post("chat", { text: "Responde apenas: Ligação ao Codex verificada." })
    .then(() => view("conversation"))
    .catch(error);
});
async function refreshDesktop() {
  const data = await api("desktop");
  $("#monitor-summary").replaceChildren();
  $("#screens").replaceChildren();
  $("#windows").replaceChildren();
  if (!data.monitors.length) {
    $("#monitor-summary").append(
      el(
        "div",
        data.error || "Nenhum monitor detetado.",
        "monitor-unavailable",
      ),
    );
    $("#screens").append(el("p", data.error || "Nenhum monitor detetado."));
  }
  for (const m of data.monitors) {
    const name = state.settings.monitor_names[m.id] || "Ecrã " + m.number;
    const mini = el("div", undefined, "monitor-mini");
    const box = el("div", undefined, "monitor-box");
    box.append(el("b", name), el("span", m.width + " × " + m.height));
    mini.append(box, el("small", m.primary ? "PRINCIPAL" : m.dpi + " DPI"));
    $("#monitor-summary").append(mini);
    const card = el("div", undefined, "panel");
    card.append(
      el("h3", name),
      el(
        "p",
        m.width +
          " × " +
          m.height +
          " · " +
          m.dpi +
          " DPI · posição " +
          m.left +
          ", " +
          m.top,
      ),
    );
    const label = el("input");
    label.value = state.settings.monitor_names[m.id] || "";
    label.placeholder = "Dar um nome a este ecrã";
    card.append(
      label,
      button("Guardar nome", async () => {
        state.settings.monitor_names[m.id] = label.value;
        await api("settings", {
          method: "PUT",
          body: JSON.stringify(state.settings),
        });
        await refreshDesktop();
      }),
    );
    const preview = el("img", undefined, "screen-preview hidden");
    preview.alt = "Captura local com regiões ocultas aplicadas";
    card.append(preview);
    let capture = null;
    const row = el("div", undefined, "button-row");
    row.append(
      button("Capturar agora", async () => {
        const r = await post("capture", { monitor_id: m.id });
        if (r.status !== "completed")
          throw new Error(r.error || "Captura falhou.");
        capture = r.observed_result;
        preview.src = "/api/captures/" + capture.file;
        preview.classList.remove("hidden");
        toast("Captura guardada localmente; não foi enviada.");
      }),
      button("Anexar e perguntar", async () => {
        if (!capture) throw new Error("Capture o ecrã primeiro.");
        const question = window.prompt(
          "O que quer perguntar sobre esta captura?",
        );
        if (!question) return;
        await post("chat", { text: question, captures: [capture.file] });
        view("conversation");
      }),
    );
    card.append(row);
    $("#screens").append(card);
  }
  for (const w of data.windows) {
    const item = el("div", undefined, "task");
    item.append(
      el("strong", w.title),
      el(
        "small",
        "ID " +
          w.id +
          " · " +
          (w.minimized ? "minimizada" : w.foreground ? "em foco" : "visível") +
          " · " +
          w.bounds.join(", "),
      ),
    );
    $("#windows").append(item);
  }
}
$("#refresh-screens").addEventListener("click", () =>
  refreshDesktop().catch(error),
);
function showNote(note) {
  $("#dialog-title").textContent = note.title;
  $("#dialog-body").textContent = note.body;
  $("#dialog-source").textContent =
    "Fonte: " + note.source + " · ID " + note.id;
  $("#note-dialog").showModal();
}
async function refreshNotes() {
  const notes = await api(
    "notes?q=" + encodeURIComponent($("#note-search").value),
  );
  $("#notes").replaceChildren();
  $("#note-count").textContent = notes.length;
  for (const note of notes) {
    const card = el("article", undefined, "note");
    card.append(
      el("h3", note.title),
      el("p", note.body.slice(0, 600)),
      el(
        "small",
        "Fonte: " +
          note.source +
          " · " +
          new Date(note.updated).toLocaleString("pt-PT"),
      ),
    );
    const row = el("div", undefined, "button-row");
    row.append(
      button("Abrir", () => showNote(note)),
      button("Editar", async () => {
        const body = window.prompt("Corrigir nota:", note.body);
        if (body === null) return;
        await api("notes/" + note.id, {
          method: "PUT",
          body: JSON.stringify({ title: note.title, body }),
        });
        await refreshNotes();
      }),
      button("Apagar", async () => {
        if (!window.confirm("Apagar esta memória local?")) return;
        await api("notes/" + note.id, { method: "DELETE" });
        await refreshNotes();
      }),
    );
    card.append(row);
    $("#notes").append(card);
  }
  if (!notes.length)
    $("#notes").append(el("p", "Ainda não há notas para esta pesquisa."));
  await renderGraph();
}
$("#note-search").addEventListener("input", () => {
  clearTimeout(refreshNotes.timer);
  refreshNotes.timer = setTimeout(() => refreshNotes().catch(error), 200);
});
$("#note-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await post("notes", {
      title: $("#note-title").value,
      body: $("#note-body").value,
    });
    e.target.reset();
    await refreshNotes();
    toast("Nota guardada e indexada.");
  } catch (e) {
    error(e);
  }
});
$("#export").addEventListener("click", async () =>
  download("jarvis-memoria.json", await api("export")),
);
function download(name, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = el("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function renderGraph() {
  const graph = await api("graph");
  const svg = $("#galaxy");
  svg.replaceChildren();
  const ns = "http://www.w3.org/2000/svg";
  const positions = new Map();
  graph.nodes.forEach((n, i) => {
    const angle = i * 2.399963;
    const r = Math.min(210, 35 + 26 * Math.sqrt(i));
    positions.set(n.id, [300 + Math.cos(angle) * r, 250 + Math.sin(angle) * r]);
  });
  for (const l of graph.links) {
    const a = positions.get(l.source),
      b = positions.get(l.target);
    if (!a || !b) continue;
    const line = document.createElementNS(ns, "line");
    for (const [k, v] of Object.entries({
      x1: a[0],
      y1: a[1],
      x2: b[0],
      y2: b[1],
      class: "galaxy-link",
    }))
      line.setAttribute(k, v);
    svg.append(line);
  }
  for (const n of graph.nodes) {
    const [x, y] = positions.get(n.id);
    const g = document.createElementNS(ns, "g");
    g.setAttribute("class", "galaxy-node");
    g.setAttribute("role", "button");
    g.setAttribute("tabindex", "0");
    g.setAttribute("aria-label", n.title);
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", x);
    c.setAttribute("cy", y);
    c.setAttribute("r", "6");
    const text = document.createElementNS(ns, "text");
    text.setAttribute("x", x + 11);
    text.setAttribute("y", y + 4);
    text.textContent = n.title.slice(0, 23);
    g.append(c, text);
    g.addEventListener("click", () => showNote(n));
    g.addEventListener("keydown", (e) => {
      if (e.key === "Enter") showNote(n);
    });
    svg.append(g);
  }
  $("#galaxy-caption").textContent = graph.nodes.length
    ? graph.nodes.length +
      " notas · " +
      graph.links.length +
      " relações explícitas"
    : "As suas notas aparecem aqui quando forem guardadas.";
}
async function refreshRoutines() {
  const routines = await api("routines");
  $("#routines").replaceChildren();
  for (const r of routines) {
    const card = el("div", undefined, "note");
    const days = JSON.parse(r.weekdays)
      .map((i) => ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"][i])
      .join(", ");
    card.append(
      el("h3", r.name),
      el(
        "p",
        String(r.hour).padStart(2, "0") +
          ":" +
          String(r.minute).padStart(2, "0") +
          " · " +
          days +
          " · " +
          (r.enabled ? "Ativa" : "Em pausa"),
      ),
      el(
        "small",
        "Próxima execução: " +
          new Date(r.next_run).toLocaleString("pt-PT", {
            timeZone: "Europe/Lisbon",
          }),
      ),
    );
    const row = el("div", undefined, "button-row");
    row.append(
      button("Editar", () => editRoutine(r)),
      button(r.enabled ? "Pausar" : "Ativar", async () => {
        await post("routines/" + r.id + "/toggle");
        await refreshRoutines();
      }),
      button("Apagar", async () => {
        await api("routines/" + r.id, { method: "DELETE" });
        await refreshRoutines();
      }),
    );
    card.append(row);
    $("#routines").append(card);
  }
  if (!routines.length)
    $("#routines").append(el("p", "Ainda não criou rotinas."));
}
$("#routine-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const [hour, minute] = f.get("time").split(":").map(Number);
  try {
    const arguments_ = {
      name: f.get("name"),
      hour,
      minute,
      weekdays:
        f.get("days") === "custom"
          ? editingWeekdays
          : f.get("days") === "daily"
            ? [0, 1, 2, 3, 4, 5, 6]
            : [0, 1, 2, 3, 4],
      applications: f.getAll("app").filter(Boolean),
    };
    if (editingRoutine) {
      await api("routines/" + editingRoutine, {
        method: "PUT",
        body: JSON.stringify(arguments_),
      });
      resetRoutine();
      await refreshRoutines();
      toast("Rotina atualizada.");
      return;
    }
    await post("actions", {
      action: "routine_create",
      arguments: arguments_,
    });
    toast("Pedido de rotina registado.");
    setTimeout(() => refreshRoutines().catch(error), 300);
  } catch (e) {
    error(e);
  }
});
let editingRoutine = null,
  editingWeekdays = [];
function resetRoutine() {
  editingRoutine = null;
  $("#routine-form").reset();
  $("#routine-form .primary-button").textContent = "Criar rotina";
  $("#cancel-routine-edit").classList.add("hidden");
}
function editRoutine(r) {
  editingRoutine = r.id;
  editingWeekdays = JSON.parse(r.weekdays);
  const form = $("#routine-form");
  form.elements.name.value = r.name;
  form.elements.time.value =
    String(r.hour).padStart(2, "0") + ":" + String(r.minute).padStart(2, "0");
  if (![...form.elements.days.options].some((o) => o.value === "custom"))
    form.elements.days.add(new Option("Dias desta rotina", "custom"));
  form.elements.days.value = "custom";
  const apps = JSON.parse(r.steps)
    .filter((s) => s.action === "app_open")
    .map((s) => s.arguments.application);
  for (const o of form.elements.app.options)
    o.selected = apps.length ? apps.includes(o.value) : o.value === "";
  $("#routine-form .primary-button").textContent = "Guardar alterações";
  $("#cancel-routine-edit").classList.remove("hidden");
  form.scrollIntoView({ behavior: "smooth" });
}
const cancelRoutine = button(
  "Cancelar edição",
  resetRoutine,
  "secondary-button hidden",
);
cancelRoutine.id = "cancel-routine-edit";
$("#routine-form").append(cancelRoutine);
$('#routine-form select[name="app"]').multiple = true;
async function refreshDiagnostics() {
  diagnostics = await api("diagnostics");
  $("#diagnostics").textContent = JSON.stringify(diagnostics, null, 2);
  $("#diag-summary").replaceChildren();
  for (const [number, label] of [
    [diagnostics.logical_cores, "processadores lógicos"],
    [diagnostics.ram_gb + " GB", "RAM do equipamento"],
    [diagnostics.process_memory_mb + " MB", "memória do Jarvis"],
  ]) {
    const card = el("div", undefined, "panel");
    card.append(el("strong", String(number)), el("p", label));
    $("#diag-summary").append(card);
  }
}
$("#refresh-diag").addEventListener("click", () =>
  refreshDiagnostics().catch(error),
);
$("#copy-diag").addEventListener("click", () =>
  navigator.clipboard
    .writeText(JSON.stringify(diagnostics, null, 2))
    .then(() => toast("Diagnóstico copiado."))
    .catch(error),
);
function setup() {
  const steps = [
    [
      "01",
      "Conta e modelo",
      "Ligue a conta ChatGPT e faça um pedido real. Só uma resposta concluída verifica o acesso ao modelo.",
      "Ligar e testar",
      () => view("settings"),
    ],
    [
      "02",
      "Microfone e voz",
      "Selecione o microfone, prepare o modelo e teste uma voz SAPI. Disponibilidade pt-PT depende das vozes acessíveis.",
      "Preparar voz",
      () => view("settings"),
    ],
    [
      "03",
      "Os seus dois monitores",
      "Atualize a disposição, atribua nomes e teste capturas redigidas antes de permitir ações.",
      "Identificar ecrãs",
      () => view("screens"),
    ],
    [
      "04",
      "Primeira ação verificada",
      "Guarde uma memória e confirme que surge na pesquisa. O controlo Windows permanece pendente até um teste local.",
      "Testar memória",
      async () => {
        await post("chat", {
          text: "Lembra-te de que prefiro respostas curtas em português de Portugal.",
        });
        view("conversation");
      },
    ],
  ];
  $("#setup-checks").replaceChildren();
  for (const [number, title, description, label, fn] of steps) {
    const card = el("div", undefined, "panel setup-step");
    card.append(
      el("span", number, "setup-number"),
      el("h3", title),
      el("p", description),
      button(label, fn),
    );
    $("#setup-checks").append(card);
  }
}
const benchmarkPrompts = [
  "Jarvis, estás a ouvir-me?",
  "Lembra-te de que prefiro respostas curtas em português de Portugal.",
  "O que te pedi para recordar?",
  "Abre a calculadora.",
  "Pára.",
  "Jarvis, que horas são em Lisboa?",
  "Diz uma frase curta em português de Portugal.",
  "Interrompa esta resposta enquanto o Jarvis fala.",
  "Diga uma frase com uma pausa intermédia.",
  "Repita um pedido com ruído ambiente moderado.",
  "Lista as janelas.",
  "O que está aberto em cada ecrã?",
  "Abre o Bloco de Notas.",
  "Move a janela de teste para o monitor esquerdo.",
  "Move a janela de teste para o monitor direito.",
  "Leia texto de uma janela de teste identificada.",
  "Capture um ecrã com uma região oculta.",
  "Compare duas capturas anexadas explicitamente.",
  "Faça uma pergunta enquanto uma tarefa decorre.",
  "Desligue e volte a ligar o microfone.",
  "Teste o fim de turno com uma pausa de 300 ms.",
  "Teste o fim de turno com uma pausa de 500 ms.",
  "Cancele uma tarefa em execução.",
  "Guarde uma nota com uma fonte.",
  "Pesquise essa nota imediatamente.",
  "Crie um lembrete local para uma hora escolhida.",
  "Pause a rotina criada.",
  "Teste sem rede: guarde e consulte uma nota.",
  "Prima Ctrl + Alt + Backspace durante uma resposta.",
  "Retome e faça um novo pedido.",
];
let benchmarkIndex = -1;
const observations = [];
$("#benchmark-next").addEventListener("click", () => {
  benchmarkIndex++;
  $("#benchmark-prompt").textContent =
    benchmarkIndex < 30
      ? benchmarkIndex + 1 + "/30 · " + benchmarkPrompts[benchmarkIndex]
      : "Teste guiado concluído. Exporte as observações e o diagnóstico; não são medições acústicas automáticas.";
});
for (const [id, passed] of [
  ["benchmark-pass", true],
  ["benchmark-fail", false],
])
  $("#" + id).addEventListener("click", () => {
    if (benchmarkIndex < 0 || benchmarkIndex >= 30) return;
    observations.push({
      turn: benchmarkIndex + 1,
      prompt: benchmarkPrompts[benchmarkIndex],
      passed,
      reported_by: "user",
      at: new Date().toISOString(),
      notes: window.prompt("Observação opcional:") || "",
    });
    $("#benchmark-next").click();
  });
$("#benchmark-export").addEventListener("click", async () =>
  download("jarvis-teste-local.json", {
    observations,
    diagnostics: await api("diagnostics"),
    methodology:
      "Observações declaradas pelo utilizador; sem medição acústica automática.",
  }),
);
function connectEvents() {
  socket = new WebSocket(
    (location.protocol === "https:" ? "wss:" : "ws:") +
      "//" +
      location.host +
      "/api/events",
  );
  socket.onopen = () => {
    $("#connection").replaceChildren(
      el("span", undefined, "dot"),
      document.createTextNode("Ligado ao seu PC"),
    );
  };
  socket.onclose = () => {
    $("#connection").textContent = "A restabelecer ligação";
    setTimeout(() => {
      connectEvents();
      refreshState().catch(error);
    }, 2000);
  };
  socket.onmessage = async (e) => {
    const event = JSON.parse(e.data);
    if (event.type === "message") {
      if (event.turn_id && streaming.has(event.turn_id)) {
        streaming.get(event.turn_id).remove();
        streaming.delete(event.turn_id);
      }
      addMessage(event.message);
    } else if (event.type === "delta") {
      let article = streaming.get(event.turn_id);
      if (!article) {
        article = addMessage({
          id: event.turn_id,
          role: "assistant",
          text: "",
        });
        streaming.set(event.turn_id, article);
      }
      article.querySelector(".message-text").textContent += event.text;
      $("#messages").scrollTop = $("#messages").scrollHeight;
    } else if (event.type === "state") setStatus(event.state);
    else if (event.type === "stopped") {
      setStatus("paused");
      $("#resume").classList.remove("hidden");
      $("#resume-header").classList.remove("hidden");
      toast(event.message);
    } else if (event.type === "transcript") {
      $("#partial").textContent =
        event.text || (event.final ? "À espera da sua voz…" : "A transcrever…");
    } else if (event.type === "error") {
      addMessage({
        id: crypto.randomUUID(),
        role: "error",
        text: event.message,
      });
      toast(event.message);
    } else if (event.type === "playback")
      setStatus(event.playing ? "speaking" : "ready");
    else if (event.type === "audio_level")
      $("#orb").style.setProperty("--audio-level", String(event.level));
    else if (event.type === "task") {
      const s = await api("state");
      state.tasks = s.tasks;
      renderTasks(s.tasks);
    } else if (event.type === "audio") {
      if (event.message) toast(event.message);
      if (event.status === "listening") setStatus("listening");
      if (event.microphone !== undefined) {
        state.audio.listening = event.microphone;
        $("#listen").textContent = event.microphone
          ? "Desligar microfone"
          : "Ativar mãos livres";
        if (!event.microphone)
          $("#partial").textContent = "Microfone desligado";
      }
    } else if (event.type === "login") {
      if (event.success) {
        const c = await post("codex/connect");
        state.codex = c;
        renderAccount(c);
        $("#login-link").classList.add("hidden");
        toast("Login confirmado pelo Codex.");
      } else toast(event.error || "Login não concluído.");
    } else if (event.type === "reminder") toast(event.message);
    else if (event.type === "capture_sent")
      toast(
        "Captura anexada ao pedido Codex. A compreensão só fica verificada pela resposta.",
      );
  };
}
async function boot() {
  try {
    const token = location.hash.slice(1);
    if (token) {
      await post("session", { token });
      history.replaceState(null, "", location.pathname);
    }
    await refreshState();
    setup();
    connectEvents();
    await refreshDesktop();
  } catch (e) {
    $("#connection").textContent = "Sessão não disponível";
    error(e);
    $("#assistant-hint").textContent =
      "Abra a aplicação através de INICIAR_JARVIS.bat para iniciar uma sessão autenticada.";
  }
}
function optionalVoicePanel() {
  const panel = el("div", undefined, "panel form-stack");
  panel.append(el("h3", "Raciocínio offline opcional"));
  const brain = el("select");
  brain.id = "brain-provider";
  brain.add(new Option("Codex · plano ChatGPT", "codex"));
  brain.add(new Option("Ollama · modelo instalado no PC", "ollama"));
  const brainLabel = el("label", "Inteligência");
  brainLabel.append(brain);
  panel.append(brainLabel);
  const local = el("input");
  local.id = "local-model";
  const localLabel = el("label", "Nome de um modelo já instalado no Ollama");
  localLabel.append(local);
  panel.append(localLabel);
  const catalogue = el("pre");
  panel.append(
    button("Procurar modelos locais", async () => {
      catalogue.textContent = JSON.stringify(
        await post("providers/ollama/catalog"),
        null,
        2,
      );
    }),
    catalogue,
    el(
      "p",
      "Não descarrega modelos. O modo Ollama conversa e usa memória local; ferramentas complexas e imagens deste perfil ainda não estão validadas.",
      "help",
    ),
  );
  panel.append(
    el("h3", "Voz online opcional"),
    el(
      "p",
      "Desligada por omissão. Consulte o preço na conta do fornecedor antes de aceitar custos. As chaves são introduzidas apenas nos scripts CONFIGURAR_FISH.bat / CONFIGURAR_OPENAI.bat, com entrada oculta.",
      "help",
    ),
  );
  const provider = el("select");
  provider.id = "tts-provider";
  for (const [name, value] of [
    ["Windows SAPI · local", "sapi"],
    ["Fish Audio · API separada", "fish"],
    ["OpenAI · síntese API separada", "openai"],
  ])
    provider.add(new Option(name, value));
  const label = el("label", "Fornecedor de síntese");
  label.append(provider);
  panel.append(label);
  const consent = el("label", undefined, "check");
  const check = el("input");
  check.type = "checkbox";
  check.id = "online-costs";
  consent.append(
    check,
    document.createTextNode("Aceito os custos API da voz online selecionada."),
  );
  panel.append(consent);
  for (const [id, name] of [
    ["fish-model", "Modelo Fish Audio com acesso confirmado na sua conta"],
    ["fish-voice", "ID da voz Fish Audio"],
    ["openai-model", "Modelo OpenAI de síntese da sua conta API"],
    ["openai-voice", "Voz OpenAI oficialmente suportada pelo modelo"],
  ]) {
    const label = el("label", name);
    const input = el("input");
    input.id = id;
    label.append(input);
    panel.append(label);
  }
  const result = el("pre");
  panel.append(
    button("Consultar saldo e vozes Fish", async () => {
      result.textContent = "A consultar a API…";
      try {
        const data = await post("providers/fish/catalog");
        result.textContent = JSON.stringify(data, null, 2);
      } catch (e) {
        result.textContent = e.message;
      }
    }),
    result,
  );
  panel.append(
    el(
      "p",
      "STT e raciocínio mantêm os seus próprios componentes. Esta opção implementa síntese em streaming; não implementa Realtime nem uma voz privada da aplicação ChatGPT.",
      "help",
    ),
  );
  $("#settings-form").insertBefore(panel, $(".settings-save"));
}
optionalVoicePanel();
boot();
