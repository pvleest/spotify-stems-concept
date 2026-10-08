/* Stems concept player. One AudioContext, sample-aligned buffers. */
(function () {
  "use strict";

  const STEMS = [
    { id: "vocals", name: "Lead vocal", detail: "Synthesized melody", color: "#1DB954", icon: "mic" },
    { id: "backing", name: "Backing vocals", detail: "Chorus only", color: "#7DDFB3", icon: "backs" },
    { id: "drums", name: "Drums", detail: "Kick, snare, hats", color: "#F6C945", icon: "drums" },
    { id: "bass", name: "Bass", detail: "Low end", color: "#6AA6FF", icon: "bass" },
    { id: "guitar", name: "Guitar", detail: "Plucked chords", color: "#FF8A6A", icon: "guitar" },
    { id: "keys", name: "Keys", detail: "Soft pad", color: "#C9A6FF", icon: "keys" }
  ];

  const app = document.getElementById("app");
  const playBtn = document.getElementById("play");
  const playIcon = document.getElementById("playIcon");
  const seek = document.getElementById("seek");
  const curEl = document.getElementById("cur");
  const durEl = document.getElementById("dur");
  const loadLabel = document.getElementById("loadLabel");
  const mixLine = document.getElementById("mixLine");
  const stemsBtn = document.getElementById("stemsBtn");
  const backBtn = document.getElementById("backBtn");
  const restartBtn = document.getElementById("restart");
  const mixer = document.getElementById("mixer");

  const ICONS = {
    mic: '<path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M6 11a6 6 0 0 0 12 0" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 17v3" stroke="currentColor" stroke-width="1.8"/>',
    backs: '<path d="M9 4a2.4 2.4 0 0 0-2.4 2.4v4.2a2.4 2.4 0 0 0 4.8 0V6.4A2.4 2.4 0 0 0 9 4z"/><path d="M15 6.2a2 2 0 0 1 2 2v2.2a2 2 0 0 1-4 0" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4.8 11.2a4.4 4.4 0 0 0 8.4 0" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    drums: '<ellipse cx="12" cy="14" rx="7" ry="3.2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M5 14V10.5C5 9 8 8 12 8s7 1 7 2.5V14" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M15 7l3-3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    bass: '<path d="M5 16c2.2-6 4-8 7-8s4 2 5.2 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="17.2" cy="13.2" r="1.3"/>',
    guitar: '<path d="M15 4l2 2-6.5 6.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="8.2" cy="15.2" r="3.1" fill="none" stroke="currentColor" stroke-width="1.7"/>',
    keys: '<rect x="4" y="6" width="16" height="12" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 6v7M12 6v7M16 6v7" stroke="currentColor" stroke-width="1.6"/>'
  };

  const PLAY_PATH = "M8 5v14l11-7z";
  const PAUSE_PATH = "M6 5h4v14H6zM14 5h4v14h-4z";

  let ctx = null;
  let master = null;
  let ready = false;
  let playing = false;
  let offset = 0;
  let startedAt = 0;
  let duration = 71;
  let token = 0;
  let scrubbing = false;
  let raf = 0;
  const meterData = new Uint8Array(256);

  STEMS.forEach(function (s) {
    s.mute = false;
    s.solo = false;
    s.volume = 1;
    s.peaks = new Array(96).fill(0.15);
  });

  function icon(name) {
    return '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">' + ICONS[name] + "</svg>";
  }

  function fmt(t) {
    if (!Number.isFinite(t) || t < 0) t = 0;
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return m + ":" + String(s).padStart(2, "0");
  }

  function paintRange(input, color) {
    const pct = ((input.value - input.min) / (input.max - input.min)) * 100;
    input.style.setProperty("--track", "linear-gradient(to right, " + (color || "#fff") + " " + pct + "%, #4d4d4d " + pct + "%)");
  }

  function anySolo() {
    return STEMS.some(function (s) { return s.solo; });
  }

  function audible(s) {
    if (s.mute || s.volume <= 0.001) return false;
    if (anySolo() && !s.solo) return false;
    return true;
  }

  function targetGain(s) {
    return audible(s) ? s.volume : 0;
  }

  function buildMixer() {
    mixer.innerHTML =
      '<article class="intro-card">' +
      '<p class="kicker">Shared by the artist</p>' +
      '<h2>Six stems. One playhead.</h2>' +
      '<p>Mira Ellison chose which parts of Glass Garden you can open. Mute a stem, solo it, or ride its volume. The song never drifts out of time.</p>' +
      '<p class="hint">Try soloing Backing vocals. They only sing on the chorus.</p>' +
      '<div class="stem-names"><span>Lead vocal</span><span>Backing vocals</span><span>Drums</span><span>Bass</span><span>Guitar</span><span>Keys</span></div>' +
      '<div class="intro-actions"><button class="stems-btn" id="openStems" type="button">Open multitrack</button></div>' +
      "</article>" +
      '<div class="stem-tools">' +
      '<div class="stem-head"><div><h2>Multitrack</h2><p class="byline">Stems made available by the artist</p></div>' +
      '<button class="linkish" id="resetMix" type="button">Reset mix</button></div>' +
      '<div class="stem-list" id="stemList"></div></div>';

    const list = document.getElementById("stemList");
    list.innerHTML = STEMS.map(function (s) {
      return (
        '<article class="stem" data-id="' + s.id + '" style="--c:' + s.color + '">' +
        '<div class="orb">' + icon(s.icon) + '</div>' +
        '<div class="nameblock"><div class="text"><h3>' + s.name + '</h3><p class="detail">' + s.detail +
        ' <span class="meters" aria-hidden="true"><i></i><i></i><i></i></span></p></div>' +
        '<div class="pills">' +
        '<button class="pill mute" type="button" aria-pressed="false" aria-label="Mute ' + s.name + '">Mute</button>' +
        '<button class="pill solo" type="button" aria-pressed="false" aria-label="Solo ' + s.name + '">Solo</button>' +
        "</div></div>" +
        '<canvas class="wave" width="600" height="72" aria-label="' + s.name + ' waveform"></canvas>' +
        '<label class="fader"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>' +
        '<input type="range" min="0" max="100" value="100" aria-label="' + s.name + ' volume"></label>' +
        "</article>"
      );
    }).join("");

    document.getElementById("openStems").addEventListener("click", function () { setStemsOpen(true); });
    document.getElementById("resetMix").addEventListener("click", resetMix);

    STEMS.forEach(function (s) {
      const card = list.querySelector('[data-id="' + s.id + '"]');
      s.card = card;
      s.canvas = card.querySelector("canvas");
      s.vol = card.querySelector("input");
      s.muteBtn = card.querySelector(".mute");
      s.soloBtn = card.querySelector(".solo");
      s.bars = card.querySelectorAll(".meters i");
      s.muteBtn.addEventListener("click", function () {
        s.mute = !s.mute;
        if (s.mute) s.solo = false;
        refreshMix();
      });
      s.soloBtn.addEventListener("click", function () {
        s.solo = !s.solo;
        if (s.solo) s.mute = false;
        refreshMix();
      });
      s.vol.addEventListener("input", function () {
        s.volume = Number(s.vol.value) / 100;
        paintRange(s.vol, s.color);
        applyGain(s, true);
        updateMixLine();
        paintCard(s);
      });
      s.canvas.addEventListener("pointerdown", function (ev) {
        if (!ready) return;
        const rect = s.canvas.getBoundingClientRect();
        const ratio = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
        seekTo(ratio * duration);
      });
      paintRange(s.vol, s.color);
    });
  }

  function setStemsOpen(open) {
    app.classList.toggle("stems-open", open);
    stemsBtn.setAttribute("aria-pressed", open ? "true" : "false");
    backBtn.disabled = !open;
    if (open && location.hash !== "#stems") history.replaceState(null, "", "#stems");
    if (!open && location.hash === "#stems") history.replaceState(null, "", location.pathname + location.search);
    requestAnimationFrame(drawAll);
  }

  function resetMix() {
    STEMS.forEach(function (s) {
      s.mute = false;
      s.solo = false;
      s.volume = 1;
      s.vol.value = 100;
      paintRange(s.vol, s.color);
      applyGain(s, true);
    });
    refreshMix();
  }

  function updateMixLine() {
    const solos = STEMS.filter(function (s) { return s.solo; }).map(function (s) { return s.name; });
    const mutes = STEMS.filter(function (s) { return s.mute; }).map(function (s) { return s.name; });
    if (solos.length) mixLine.textContent = "Solo · " + solos.join(", ");
    else if (mutes.length) mixLine.textContent = "Muted · " + mutes.join(", ");
    else if (STEMS.some(function (s) { return Math.abs(s.volume - 1) > 0.01; })) mixLine.textContent = "Custom mix";
    else mixLine.textContent = "Artist mix";
  }

  function paintCard(s) {
    s.muteBtn.setAttribute("aria-pressed", s.mute ? "true" : "false");
    s.soloBtn.setAttribute("aria-pressed", s.solo ? "true" : "false");
    s.card.classList.toggle("is-silent", !audible(s));
    s.card.classList.toggle("is-solo", s.solo);
  }

  function refreshMix() {
    STEMS.forEach(function (s) {
      paintCard(s);
      applyGain(s, true);
    });
    updateMixLine();
    drawAll();
  }

  function roundRect(c, x, y, w, h, r) {
    const radius = Math.min(r, w / 2, h / 2);
    c.beginPath();
    c.moveTo(x + radius, y);
    c.arcTo(x + w, y, x + w, y + h, radius);
    c.arcTo(x + w, y + h, x, y + h, radius);
    c.arcTo(x, y + h, x, y, radius);
    c.arcTo(x, y, x + w, y, radius);
    c.closePath();
  }

  function drawStem(s) {
    const canvas = s.canvas;
    if (!canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, canvas.clientWidth);
    const h = Math.max(1, canvas.clientHeight);
    if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
    }
    const c = canvas.getContext("2d");
    c.clearRect(0, 0, canvas.width, canvas.height);
    const peaks = s.peaks;
    const n = peaks.length;
    const gap = 1.6 * dpr;
    const bw = Math.max(1, (canvas.width - gap * (n - 1)) / n);
    const progress = duration ? currentTime() / duration : 0;
    const silent = !audible(s);
    for (let i = 0; i < n; i++) {
      const bh = Math.max(2 * dpr, peaks[i] * (canvas.height - 2 * dpr));
      const x = i * (bw + gap);
      const y = (canvas.height - bh) / 2;
      const played = (i + 0.5) / n <= progress;
      c.fillStyle = silent ? "rgba(255,255,255,0.18)" : played ? s.color : "rgba(255,255,255,0.28)";
      roundRect(c, x, y, bw, bh, bw / 2);
      c.fill();
    }
  }

  function drawAll() {
    STEMS.forEach(drawStem);
  }

  function currentTime() {
    if (!playing || !ctx) return offset;
    const t = offset + (ctx.currentTime - startedAt);
    return Math.min(duration, Math.max(0, t));
  }

  function applyGain(s, smooth) {
    if (!s.gainNode || !ctx) return;
    const g = targetGain(s);
    const param = s.gainNode.gain;
    const now = ctx.currentTime;
    param.cancelScheduledValues(now);
    if (smooth) {
      param.setValueAtTime(param.value, now);
      param.linearRampToValueAtTime(g, now + 0.03);
    } else {
      param.setValueAtTime(g, now);
    }
  }

  function ensureGraph() {
    if (ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.95;
    master.connect(ctx.destination);
    STEMS.forEach(function (s) {
      s.gainNode = ctx.createGain();
      s.gainNode.gain.value = targetGain(s);
      s.analyser = ctx.createAnalyser();
      s.analyser.fftSize = 256;
      s.analyser.smoothingTimeConstant = 0.8;
      s.gainNode.connect(s.analyser);
      s.analyser.connect(master);
    });
  }

  function stopSources() {
    token += 1;
    STEMS.forEach(function (s) {
      if (!s.source) return;
      try { s.source.stop(); } catch (err) { /* already stopped */ }
      try { s.source.disconnect(); } catch (err) { /* already disconnected */ }
      s.source = null;
    });
  }

  function startSources() {
    const my = ++token;
    const when = ctx.currentTime + 0.05;
    const off = Math.min(Math.max(0, offset), Math.max(0, duration - 0.03));
    offset = off;
    STEMS.forEach(function (s) {
      const src = ctx.createBufferSource();
      src.buffer = s.buffer;
      src.connect(s.gainNode);
      applyGain(s, false);
      src.start(when, off);
      src.onended = function () {
        if (my !== token || !playing) return;
        if (currentTime() >= duration - 0.12) {
          playing = false;
          offset = 0;
          app.classList.remove("playing");
          setPlayIcon(false);
        }
      };
      s.source = src;
    });
    startedAt = when;
    playing = true;
    app.classList.add("playing");
    setPlayIcon(true);
  }

  function setPlayIcon(isPlaying) {
    playIcon.innerHTML = '<path d="' + (isPlaying ? PAUSE_PATH : PLAY_PATH) + '"/>';
    playBtn.setAttribute("aria-label", isPlaying ? "Pause" : "Play");
  }

  function play() {
    if (!ready) return;
    if (ctx.state === "suspended") ctx.resume();
    if (offset >= duration - 0.05) offset = 0;
    stopSources();
    startSources();
  }

  function pause() {
    if (!playing) return;
    offset = currentTime();
    playing = false;
    stopSources();
    app.classList.remove("playing");
    setPlayIcon(false);
  }

  function toggle() {
    if (!ready) return;
    if (ctx.state === "suspended") ctx.resume();
    if (playing) pause();
    else play();
  }

  function seekTo(t) {
    offset = Math.min(duration, Math.max(0, t));
    if (playing) {
      stopSources();
      startSources();
    }
    updateClock();
  }

  function updateClock() {
    const t = currentTime();
    curEl.textContent = fmt(t);
    if (!scrubbing && duration) {
      seek.value = String(Math.round((t / duration) * 1000));
      paintRange(seek, "#fff");
    }
    if (playing && t >= duration - 0.05) {
      pause();
      offset = 0;
      seek.value = "0";
      paintRange(seek, "#fff");
      curEl.textContent = fmt(0);
    }
  }

  function updateMeters() {
    if (!playing) {
      STEMS.forEach(function (s) {
        s.bars.forEach(function (bar) { bar.style.transform = "scaleY(0.15)"; });
      });
      return;
    }
    STEMS.forEach(function (s) {
      if (!s.analyser) return;
      s.analyser.getByteTimeDomainData(meterData);
      let sum = 0;
      for (let i = 0; i < meterData.length; i += 4) {
        const v = (meterData[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / (meterData.length / 4));
      const level = audible(s) ? Math.min(1, rms * 4.2) : 0.08;
      s.bars.forEach(function (bar, idx) {
        const wobble = 0.55 + 0.45 * Math.abs(Math.sin(performance.now() / 140 + idx));
        bar.style.transform = "scaleY(" + Math.max(0.12, level * wobble).toFixed(3) + ")";
      });
    });
  }

  function frame() {
    updateClock();
    updateMeters();
    if (playing || scrubbing) drawAll();
    raf = requestAnimationFrame(frame);
  }

  async function load() {
    ensureGraph();
    try {
      const peaksRes = await fetch("audio/peaks.json");
      if (peaksRes.ok) {
        const peaks = await peaksRes.json();
        duration = peaks.duration || duration;
        durEl.textContent = fmt(duration);
        STEMS.forEach(function (s) {
          if (peaks.stems && peaks.stems[s.id]) s.peaks = peaks.stems[s.id];
        });
        drawAll();
      }
    } catch (err) {
      /* peaks are optional; waveforms fill in after decode */
    }

    for (let i = 0; i < STEMS.length; i++) {
      const s = STEMS[i];
      loadLabel.textContent = "Loading " + (i + 1) + " / " + STEMS.length;
      const res = await fetch("audio/" + s.id + ".mp3");
      if (!res.ok) throw new Error("Missing " + s.id);
      const raw = await res.arrayBuffer();
      s.buffer = await ctx.decodeAudioData(raw.slice(0));
    }
    const lengths = STEMS.map(function (s) { return s.buffer.duration; });
    duration = Math.min.apply(null, lengths);
    durEl.textContent = fmt(duration);
    ready = true;
    playBtn.disabled = false;
    seek.disabled = false;
    restartBtn.disabled = false;
    loadLabel.textContent = "";
    loadLabel.hidden = true;
    paintRange(seek, "#fff");
    drawAll();
    if (location.search.indexOf("autotest=1") !== -1) runSelfTest();
  }

  async function runSelfTest() {
    const log = [];
    window.__stemsErrors = window.__stemsErrors || [];
    try {
      const resumed = await Promise.race([
        ctx.resume().then(function () { return ctx.state; }),
        new Promise(function (r) { setTimeout(function () { r("timeout"); }, 1500); })
      ]);
      log.push("resume=" + resumed + " state=" + ctx.state);
      play();
      await new Promise(function (r) { setTimeout(r, 350); });
      log.push("state=" + ctx.state);
      log.push("playing=" + playing);
      log.push("t=" + currentTime().toFixed(3));
      seekTo(12);
      await new Promise(function (r) { setTimeout(r, 250); });
      log.push("afterSeek=" + currentTime().toFixed(3));
      STEMS[0].mute = true;
      refreshMix();
      log.push("muteTarget=" + targetGain(STEMS[0]).toFixed(2));
      STEMS[5].solo = true;
      refreshMix();
      log.push("soloKeys=" + targetGain(STEMS[5]).toFixed(2) + " vocals=" + targetGain(STEMS[0]).toFixed(2));
      resetMix();
      log.push("reset=" + targetGain(STEMS[0]).toFixed(2));
      const aligned = STEMS.every(function (s) {
        return Math.abs(s.buffer.duration - STEMS[0].buffer.duration) < 0.02;
      });
      log.push("aligned=" + aligned);
      log.push("channels=" + STEMS.map(function (s) { return s.buffer.numberOfChannels; }).join(","));
      pause();
      log.push("paused=" + (!playing));
    } catch (err) {
      log.push("ERR " + err.message);
    }
    log.push("errors=" + window.__stemsErrors.length);
    const pre = document.createElement("pre");
    pre.id = "selftest";
    pre.hidden = true;
    pre.textContent = log.join("\n");
    document.body.appendChild(pre);
  }

  window.addEventListener("error", function (ev) {
    window.__stemsErrors = window.__stemsErrors || [];
    window.__stemsErrors.push(String(ev.message));
  });

  playBtn.addEventListener("click", toggle);
  stemsBtn.addEventListener("click", function () { setStemsOpen(!app.classList.contains("stems-open")); });
  backBtn.addEventListener("click", function () { setStemsOpen(false); });
  restartBtn.addEventListener("click", function () { seekTo(0); });

  seek.addEventListener("pointerdown", function () { scrubbing = true; });
  seek.addEventListener("pointerup", function () { scrubbing = false; });
  seek.addEventListener("input", function () {
    const t = (Number(seek.value) / 1000) * duration;
    curEl.textContent = fmt(t);
    paintRange(seek, "#fff");
    if (ready) seekTo(t);
  });
  seek.addEventListener("change", function () { scrubbing = false; });

  window.addEventListener("keydown", function (ev) {
    if (ev.code !== "Space") return;
    if (ev.target && ev.target.closest && ev.target.closest("input, button, a")) return;
    ev.preventDefault();
    toggle();
  });

  window.addEventListener("resize", drawAll);
  if (location.hash === "#stems") setStemsOpen(true);

  buildMixer();
  paintRange(seek, "#fff");
  raf = requestAnimationFrame(frame);
  load().catch(function (err) {
    loadLabel.textContent = "Could not load audio";
    console.error(err);
  });
})();
