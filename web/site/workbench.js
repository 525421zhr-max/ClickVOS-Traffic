"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const colors = ["#00d2ff", "#ff5c5c", "#8fff5c", "#c36eff", "#ffbe46", "#4696ff"];
  const labels = {vehicle:"车辆", pedestrian:"行人", non_motorized:"非机动车"};
  const state = {service:"", key:"", connected:false, busy:false, task:null, objects:[], selected:null,
    frame:0, corrections:[], draft:false, image:null, imageUrl:null, frameRequest:0};
  const canvas = $("annotation-canvas"), context = canvas.getContext("2d");
  const storageKey = "clickvos-service-v1";
  let connection = {};
  try { connection = JSON.parse(sessionStorage.getItem(storageKey) || "{}"); } catch {}
  const fragment = location.hash.slice(1).split("?");
  const parameters = new URLSearchParams(fragment[1] || "");
  if (parameters.has("service") && parameters.has("key")) {
    connection = {service:parameters.get("service"), key:parameters.get("key")};
    history.replaceState(null, "", "#workbench");
  }

  function route() {
    const active = location.hash.startsWith("#workbench");
    document.body.dataset.view = active ? "workbench" : "project";
    $("workbench").hidden = !active;
    $("workbench-entry").textContent = active ? "返回项目介绍" : "开始标注";
    $("workbench-entry").href = active ? "#main" : "#workbench";
  }
  window.addEventListener("hashchange", route);
  route();

  function message(text, error = false) {
    $("workspace-status").textContent = text;
    $("workspace-status").dataset.state = error ? "error" : "normal";
  }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.body instanceof File ? 120000 : 30000);
    try {
      const response = await fetch(state.service + path, {...options, signal:controller.signal,
        headers:{Authorization:"Bearer " + state.key, ...options.headers}});
      if (!response.ok) {
        if (response.status === 401) {
          state.connected = false;
          $("connection-panel").hidden = false;
          $("connection-toggle").textContent = "重新连接推理服务";
          $("connection-toggle").setAttribute("aria-expanded", "true");
        }
        let detail;
        try { detail = (await response.json()).detail; } catch {}
        throw Error(typeof detail === "string" ? detail : `服务返回 ${response.status}，请检查连接后重试。`);
      }
      return response;
    } catch (error) {
      if (error.name === "AbortError" || error instanceof TypeError) {
        state.connected = false;
        throw Error("无法连接推理服务。请确认 GPU 电脑和服务正在运行，再重新连接。");
      }
      throw error;
    } finally { clearTimeout(timeout); }
  }
  const json = async (path, body) => (await request(path, body === undefined ? {} : {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)})).json();
  async function waitJob(initial) {
    for (let i = 0; i < 1200; i++) {
      const job = await json("/api/jobs/" + initial.job_id);
      if (job.status === "succeeded") return job.result;
      if (job.status === "failed") throw Error(job.error);
      await new Promise(resolve => setTimeout(resolve, 750));
    }
    throw Error("任务运行时间超过预期，请检查服务日志后重新连接。");
  }
  async function act(text, work) {
    if (state.busy) return;
    state.busy = true; message(text); renderControls();
    try { await work(); } catch (error) {
      message(error.message, true);
      if (!state.connected) {
        $("connection-panel").hidden = false;
        $("connection-toggle").textContent = "重新连接推理服务";
        $("connection-toggle").setAttribute("aria-expanded", "true");
      }
    }
    finally { state.busy = false; renderControls(); }
  }
  async function connect() {
    const service = $("service-url").value.trim().replace(/\/$/, "");
    const url = new URL(service);
    if (url.protocol !== "https:" && !(url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname))) {
      throw Error("远程推理服务需要 HTTPS 地址，本机服务可使用 localhost。");
    }
    state.service = url.origin;
    state.key = $("access-code").value.trim();
    if (!state.key) throw Error("请输入访问码，或在本机打开连接入口。");
    const status = await json("/api/status");
    if (!status.ready) throw Error("服务已连接，但 GPU 或模型还未就绪，请联系服务提供者。");
    state.connected = true;
    sessionStorage.setItem(storageKey, JSON.stringify({service:state.service, key:state.key}));
    $("connection-panel").hidden = true;
    $("connection-toggle").textContent = "推理服务已连接";
    $("connection-toggle").setAttribute("aria-expanded", "false");
    message("推理服务已连接。请选择交通视频，开始标注。");
  }
  $("connection-form").addEventListener("submit", event => {
    event.preventDefault(); act("正在连接推理服务…", connect);
  });
  $("connection-toggle").addEventListener("click", () => {
    $("connection-panel").hidden = !$("connection-panel").hidden;
    $("connection-toggle").setAttribute("aria-expanded", String(!$("connection-panel").hidden));
  });

  function selectedTarget() { return state.objects.find(target => target.object_id === state.selected); }
  function positive() { return document.querySelector('input[name="point-mode"]:checked').value === "positive"; }
  function setTask(task) {
    state.task = task;
    state.objects = task.objects;
    if (!state.objects.some(target => target.object_id === state.selected)) state.selected = state.objects[0]?.object_id ?? null;
    $("frame-slider").max = task.frame_count - 1;
    $("video-info").textContent = `${task.width} × ${task.height} · ${task.frame_count} 帧`;
    $("canvas-empty").hidden = true; $("canvas-stage").hidden = false;
    renderTargets();
    $("result-summary").textContent = task.has_result
      ? `${state.objects.length} 个目标 · ${task.frame_count} 帧 · ${task.correction_count} 次中间帧修正。${task.pending ? "首帧提示尚未传播，请先重新传播。" : "请检查掩码后导出。"}`
      : "为每个目标至少添加一个正点，然后运行视频分割。";
    $("anomaly-summary").textContent = task.has_result ? `异常复核（${task.anomaly_count}）` : "异常复核";
    $("anomaly-list").replaceChildren();
    if (task.anomalies?.length) {
      for (const anomaly of task.anomalies.slice(0, 30)) {
        const button = document.createElement("button");
        button.className = "quiet-button anomaly-button";
        const index = Number(anomaly.frame_index ?? 0);
        button.textContent = `查看第 ${index} 帧${anomaly.object_id ? " · 目标 " + anomaly.object_id : ""}`;
        button.addEventListener("click", () => act("正在载入异常帧…", () => changeFrame(index)));
        $("anomaly-list").append(button);
      }
    } else $("anomaly-list").textContent = task.has_result ? "当前报告未发现异常。仍请逐帧复核目标与边界。" : "传播完成后，可定位需要复核的帧。";
    renderControls();
  }
  function renderTargets() {
    $("target-count").textContent = state.objects.length + " 个目标";
    $("target-list").replaceChildren();
    state.objects.forEach((target, index) => {
      const button = document.createElement("button");
      button.className = "target-option"; button.type = "button";
      button.setAttribute("aria-pressed", String(target.object_id === state.selected));
      const marker = document.createElement("span"); marker.className = "target-color"; marker.style.background = colors[index % colors.length];
      const title = document.createElement("span"); title.textContent = `${labels[target.category]} ${target.object_id}`;
      const count = document.createElement("small"); count.textContent = `${target.points.filter(point => point.positive).length} 正 / ${target.points.filter(point => !point.positive).length} 负`;
      button.append(marker, title, count);
      button.addEventListener("click", () => {
        if (state.busy) return;
        if (state.corrections.length && state.selected !== target.object_id) { message("请先应用或撤销当前目标的修正点，再切换目标。", true); return; }
        state.selected = target.object_id; renderTargets(); renderControls(); draw();
      });
      $("target-list").append(button);
    });
  }
  function renderControls() {
    const ready = state.connected && !state.busy, task = state.task, hasResult = task?.has_result;
    $("video-upload").disabled = !ready || Boolean(task);
    $("reset-video").disabled = !ready || !task;
    $("add-target").disabled = !ready || !task || hasResult || state.objects.length >= 20;
    $("delete-target").disabled = !ready || !state.selected || hasResult;
    $("undo-point").disabled = !ready || !state.selected || (state.frame === 0 ? (hasResult ? !task.undo_available : !selectedTarget()?.points.length) : !state.corrections.length);
    $("run-segmentation").disabled = !ready || !task || !state.objects.length || state.objects.some(target => !target.points.some(point => point.positive));
    $("run-segmentation").textContent = hasResult ? "用首帧提示重新传播" : "运行视频分割";
    $("preview-frame").disabled = !ready || !hasResult || state.frame !== 0;
    $("apply-correction").disabled = !ready || !hasResult || task.pending || state.frame === 0 || !state.corrections.length;
    $("export-bundle").disabled = !ready || !hasResult || task.pending || Boolean(state.corrections.length);
    $("frame-slider").disabled = !ready || !hasResult || task.pending || Boolean(state.corrections.length);
    $("show-mask").disabled = !ready || !hasResult;
    $("coordinate-submit").disabled = !ready || !task || !state.selected;
    document.querySelectorAll(".anomaly-button").forEach(button => { button.disabled = !ready || task.pending || Boolean(state.corrections.length); });
    $("point-x").max = task ? task.width - 1 : 0;
    $("point-y").max = task ? task.height - 1 : 0;
    $("canvas-guidance").textContent = state.frame > 0
      ? `正在复核第 ${state.frame} 帧。为当前目标补点后，点击“从当前帧修正并传播”。${state.corrections.length ? "已有 " + state.corrections.length + " 个待应用修正点。" : ""}`
      : task?.pending ? "首帧提示已修改。当前整段结果来自上次传播；先预览，再重新传播或撤销补点。"
      : hasResult ? "点击补充首帧提示，可先预览一帧，再决定是否重新传播。" : "先新建目标。正点选择目标，负点排除不需要的区域。";
  }
  function draw() {
    if (!state.image || !state.task) return;
    canvas.width = state.task.width; canvas.height = state.task.height;
    context.drawImage(state.image, 0, 0, canvas.width, canvas.height);
    const targets = state.frame === 0 ? state.objects : [{object_id:state.selected, points:state.corrections}];
    for (const target of targets) {
      const index = state.objects.findIndex(item => item.object_id === target.object_id);
      for (const point of target.points) {
        const radius = Math.max(5, canvas.width / 140);
        context.beginPath(); context.arc(point.x, point.y, radius, 0, Math.PI * 2);
        context.fillStyle = point.positive ? colors[Math.max(index, 0) % colors.length] : "#ff3344";
        context.fill(); context.strokeStyle = "#fff"; context.lineWidth = 2; context.stroke();
        context.font = `${radius * 1.8}px sans-serif`; context.textAlign = "center"; context.textBaseline = "middle";
        context.fillStyle = "#132b28"; context.fillText(point.positive ? "+" : "−", point.x, point.y + .5);
      }
    }
  }
  async function loadFrame() {
    if (!state.task) return;
    const id = ++state.frameRequest;
    const query = state.draft && state.frame === 0 ? "?draft=true" : $("show-mask").checked ? "?overlay=true" : "";
    const blob = await (await request(`/api/tasks/${state.task.id}/frame/${state.frame}${query}`)).blob();
    const url = URL.createObjectURL(blob), image = new Image();
    try { image.src = url; await image.decode(); } catch (error) { URL.revokeObjectURL(url); throw error; }
    if (id !== state.frameRequest) { URL.revokeObjectURL(url); return; }
    if (state.imageUrl) URL.revokeObjectURL(state.imageUrl);
    state.image = image; state.imageUrl = url; draw();
  }
  async function changeFrame(index) {
    state.frame = index; state.corrections = []; state.draft = false;
    $("frame-slider").value = index; $("frame-number").value = index;
    await loadFrame(); renderControls(); message(`已载入第 ${index} 帧，可继续复核与修正。`);
  }
  $("video-upload").addEventListener("change", () => act("正在上传与抽帧…", async () => {
    const file = $("video-upload").files[0]; if (!file) return;
    $("video-upload").value = "";
    if (file.size > 50 * 1024 * 1024) throw Error("视频超过 50 MiB，请裁剪后重新上传。");
    const initial = await (await request("/api/tasks", {method:"POST", body:file, headers:{"Content-Type":"application/octet-stream"}})).json();
    state.frame = 0; state.corrections = []; state.draft = false; $("show-mask").checked = false;
    setTask(await waitJob(initial)); await loadFrame();
    message("视频已准备。新建目标，然后在画面上添加正点。");
  }));
  $("reset-video").addEventListener("click", () => {
    if (state.busy) return;
    state.task = null; state.objects = []; state.selected = null; state.corrections = []; state.frame = 0; state.draft = false;
    state.frameRequest++; state.image = null; if (state.imageUrl) URL.revokeObjectURL(state.imageUrl); state.imageUrl = null;
    $("video-upload").value = ""; $("canvas-stage").hidden = true; $("canvas-empty").hidden = false;
    $("frame-slider").value = 0; $("frame-number").value = 0; $("show-mask").checked = false;
    $("video-info").textContent = "等待上传"; $("result-summary").textContent = "每个目标至少添加一个正点。";
    $("anomaly-summary").textContent = "异常复核"; $("anomaly-list").textContent = "传播完成后，可定位需要复核的帧。";
    renderTargets(); renderControls(); message("已清空当前画面，请选择新的视频。原任务保留在服务电脑上。");
  });
  $("add-target").addEventListener("click", () => {
    const id = state.objects.length ? Math.max(...state.objects.map(target => target.object_id)) + 1 : 1;
    state.objects.push({object_id:id, category:$("target-category").value, points:[]}); state.selected = id;
    renderTargets(); renderControls(); draw(); message(`已新建目标 ${id}，请在目标内部添加正点。`);
  });
  $("delete-target").addEventListener("click", () => {
    state.objects = state.objects.filter(target => target.object_id !== state.selected); state.selected = state.objects[0]?.object_id ?? null;
    renderTargets(); renderControls(); draw();
  });
  async function addPoint(x, y) {
    if (state.busy || !state.task) return;
    const target = selectedTarget();
    if (!target) { message("请先新建或选择一个目标。", true); return; }
    if (x < 0 || y < 0 || x >= state.task.width || y >= state.task.height) { message("提示点超出画面范围。", true); return; }
    const point = {x, y, positive:positive()};
    if (state.frame > 0) {
      if (state.corrections.length >= 128) { message("每次修正最多 128 个提示点。", true); return; }
      state.corrections.push(point); draw(); renderControls(); return;
    }
    if (target.points.length >= 128) { message("每个目标最多 128 个提示点。", true); return; }
    if (state.task.has_result) {
      await act("正在保存首帧补点…", async () => {
        setTask(await waitJob(await json(`/api/tasks/${state.task.id}/review`, {action:"add", object_id:target.object_id, point})));
        state.draft = false; await loadFrame(); message("补点已保存。先预览一帧，确认后重新传播。");
      });
    } else { target.points.push(point); renderTargets(); renderControls(); draw(); }
  }
  canvas.addEventListener("pointerdown", event => {
    if (event.button !== 0) return;
    const box = canvas.getBoundingClientRect();
    addPoint(Math.floor((event.clientX - box.left) * canvas.width / box.width), Math.floor((event.clientY - box.top) * canvas.height / box.height));
  });
  $("coordinate-form").addEventListener("submit", event => { event.preventDefault(); addPoint(Number($("point-x").value), Number($("point-y").value)); });
  $("undo-point").addEventListener("click", async () => {
    if (state.frame > 0) { state.corrections.pop(); draw(); renderControls(); return; }
    if (!state.task.has_result) { selectedTarget()?.points.pop(); renderTargets(); renderControls(); draw(); return; }
    await act("正在撤销首帧补点…", async () => {
      setTask(await waitJob(await json(`/api/tasks/${state.task.id}/review`, {action:"undo", object_id:state.selected})));
      state.draft = false; await loadFrame(); message("首帧补点已撤销。可更新预览再检查。");
    });
  });
  $("run-segmentation").addEventListener("click", () => act("正在运行 SAM2 视频分割，请等待 GPU 完成…", async () => {
    setTask(await waitJob(await json(`/api/tasks/${state.task.id}/run`, {objects:state.objects})));
    state.frame = 0; state.corrections = []; state.draft = false; $("show-mask").checked = true;
    $("frame-slider").value = 0; $("frame-number").value = 0; await loadFrame();
    message(`分割完成：${state.objects.length} 个目标、${state.task.frame_count} 帧。请复核掩码，必要时补点修正。`);
  }));
  $("preview-frame").addEventListener("click", () => act("正在生成单帧预览…", async () => {
    setTask(await waitJob(await json(`/api/tasks/${state.task.id}/review`, {action:"preview", object_id:state.selected})));
    state.draft = true; await loadFrame(); message("已更新首帧预览，整段视频仍保留上次结果。提示有改动时需重新传播后导出。");
  }));
  $("frame-slider").addEventListener("input", () => { $("frame-number").value = $("frame-slider").value; });
  $("frame-slider").addEventListener("change", () => act("正在载入视频帧…", () => changeFrame(Number($("frame-slider").value))));
  $("show-mask").addEventListener("change", () => act("正在切换画面…", async () => { state.draft = false; await loadFrame(); message("画面已更新。"); }));
  $("apply-correction").addEventListener("click", () => act("正在修正当前目标并向后传播…", async () => {
    setTask(await waitJob(await json(`/api/tasks/${state.task.id}/correct`, {object_id:state.selected, frame_index:state.frame, points:state.corrections})));
    state.corrections = []; state.draft = false; $("show-mask").checked = true; await loadFrame();
    message(`第 ${state.frame} 帧的目标修正已应用，可继续复核或下载标注包。`);
  }));
  $("export-bundle").addEventListener("click", () => act("正在打包并下载标注结果…", async () => {
    const result = await waitJob(await json(`/api/tasks/${state.task.id}/export`, {}));
    const blob = await (await request(result.download)).blob();
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = "ClickVOS-" + state.task.id + ".zip"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    message("标注包已下载，包含掩码、预览和复核记录。");
  }));
  async function initialize() {
    let defaultService = "";
    try { defaultService = (await (await fetch("service.json")).json()).service || ""; } catch {}
    if (["127.0.0.1", "localhost"].includes(location.hostname) && location.port === "7880") defaultService = location.origin;
    $("service-url").value = connection.service || defaultService;
    $("access-code").value = connection.key || "";
    renderControls();
    if (connection.key && connection.service) await act("正在连接推理服务…", connect);
  }
  initialize();
})();
