(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = matchMedia("(hover: hover) and (pointer: fine)").matches;
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, t) => a + (b - a) * t;

  /* ---------- Hero title split ---------- */
  $$("[data-split]").forEach((word, wi) => {
    const text = word.textContent;
    word.textContent = "";
    [...text].forEach((ch, i) => {
      const s = document.createElement("span");
      s.className = "char";
      s.textContent = ch;
      s.style.transitionDelay = `${0.15 + wi * 0.35 + i * 0.07}s`;
      word.appendChild(s);
    });
  });

  /* ---------- Film leader countdown ---------- */
  const leader = $("#leader");
  const leaderNum = $("#leaderNum");
  const wedge = $("#leaderWedge");
  let started = false;

  function wedgePath(p) {
    const a = p * Math.PI * 2 - Math.PI / 2;
    const x = 100 + 140 * Math.cos(a);
    const y = 100 + 140 * Math.sin(a);
    const large = p > 0.5 ? 1 : 0;
    return `M100,100 L100,-40 A140,140 0 ${large} 1 ${x},${y} Z`;
  }

  function startFilm() {
    if (started) return;
    started = true;
    leader.classList.add("is-done");
    document.body.classList.remove("is-loading");
    requestAnimationFrame(() => document.body.classList.add("is-ready"));
  }

  const mobile = matchMedia("(max-width: 760px), (pointer: coarse)").matches;
  let seenIntro = false;
  try { seenIntro = localStorage.getItem("seenIntro") === "1"; localStorage.setItem("seenIntro", "1"); } catch {}

  if (reduced || mobile || seenIntro) {
    startFilm();
  } else {
    const per = 750;
    const t0 = performance.now();
    (function tick(now) {
      if (started) return;
      const t = now - t0;
      const idx = Math.floor(t / per);
      if (idx >= 3) return startFilm();
      leaderNum.textContent = 3 - idx;
      wedge.setAttribute("d", wedgePath((t % per) / per));
      requestAnimationFrame(tick);
    })(t0);
  }
  $("#leaderSkip").addEventListener("click", startFilm);
  leader.addEventListener("click", startFilm);
  addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === "Escape") startFilm(); });

  /* ---------- Film grain ---------- */
  const grain = $("#grain");
  const gctx = grain.getContext("2d");
  const tiles = [];
  for (let n = 0; n < 8; n++) {
    const c = document.createElement("canvas");
    c.width = c.height = 200;
    const cx = c.getContext("2d");
    const img = cx.createImageData(200, 200);
    for (let i = 0; i < img.data.length; i += 4) {
      const v = Math.random() * 255;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
    cx.putImageData(img, 0, 0);
    tiles.push(c);
  }
  function sizeGrain() {
    grain.width = Math.ceil(innerWidth / 2);
    grain.height = Math.ceil(innerHeight / 2);
  }
  sizeGrain();
  let gFrame = 0, gLast = 0;
  function drawGrain(now) {
    if (now - gLast > 1000 / 24) {
      gLast = now;
      gctx.fillStyle = gctx.createPattern(tiles[gFrame++ % tiles.length], "repeat");
      gctx.save();
      gctx.translate(Math.random() * 200, Math.random() * 200);
      gctx.fillRect(-200, -200, grain.width + 200, grain.height + 200);
      gctx.restore();
    }
  }

  /* ---------- Hero light: dust + anamorphic flare ---------- */
  const hl = $("#heroLight");
  const hctx = hl.getContext("2d");
  const dpr = Math.min(devicePixelRatio || 1, 2);
  let hw = 0, hh = 0;
  const dust = [];
  function sizeHero() {
    hw = hl.clientWidth; hh = hl.clientHeight;
    hl.width = hw * dpr; hl.height = hh * dpr;
    hctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    dust.length = 0;
    const count = Math.round((hw * hh) / 9000);
    for (let i = 0; i < count; i++) {
      dust.push({ x: Math.random() * hw, y: Math.random() * hh, r: Math.random() * 1.4 + 0.2, vx: (Math.random() - 0.5) * 0.15, vy: -Math.random() * 0.2 - 0.03, a: Math.random() * 0.6 + 0.1 });
    }
  }
  sizeHero();

  const mouse = { x: innerWidth / 2, y: innerHeight * 0.4, tx: innerWidth / 2, ty: innerHeight * 0.4 };
  let heroVisible = true;
  new IntersectionObserver(([e]) => (heroVisible = e.isIntersecting)).observe(hl);

  function drawHero(now) {
    if (!heroVisible) return;
    mouse.x = lerp(mouse.x, mouse.tx, 0.06);
    mouse.y = lerp(mouse.y, mouse.ty, 0.06);
    hctx.clearRect(0, 0, hw, hh);

    const pulse = Math.exp(-(now - lastKick) / 140);
    const flicker = 0.92 + Math.sin(now * 0.013) * 0.03 + Math.random() * 0.05 + pulse * 0.6;
    const g = hctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, Math.max(hw, hh) * 0.55);
    g.addColorStop(0, `rgba(255, 170, 110, ${0.22 * flicker})`);
    g.addColorStop(0.35, `rgba(255, 90, 31, ${0.07 * flicker})`);
    g.addColorStop(1, "rgba(0,0,0,0)");
    hctx.fillStyle = g;
    hctx.fillRect(0, 0, hw, hh);

    const streak = hctx.createLinearGradient(0, 0, hw, 0);
    const sx = mouse.x / hw;
    streak.addColorStop(clamp(sx - 0.5, 0, 1), "rgba(120,170,255,0)");
    streak.addColorStop(clamp(sx, 0, 1), `rgba(170,200,255,${0.35 * flicker})`);
    streak.addColorStop(clamp(sx + 0.5, 0, 1), "rgba(120,170,255,0)");
    hctx.fillStyle = streak;
    hctx.fillRect(0, mouse.y - 1, hw, 2);
    hctx.globalAlpha = 0.25;
    hctx.fillRect(0, mouse.y - 6, hw, 12);
    hctx.globalAlpha = 1;

    for (const p of dust) {
      p.x += p.vx; p.y += p.vy;
      if (p.y < -5) { p.y = hh + 5; p.x = Math.random() * hw; }
      if (p.x < -5) p.x = hw + 5; else if (p.x > hw + 5) p.x = -5;
      const d = Math.hypot(p.x - mouse.x, p.y - mouse.y);
      const lit = clamp(1 - d / 500, 0, 1);
      hctx.fillStyle = `rgba(255, 236, 210, ${p.a * (0.25 + lit)})`;
      hctx.beginPath();
      hctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      hctx.fill();
    }
  }

  /* ---------- Cursor ---------- */
  const cursor = $("#cursor");
  const cursorLabel = $("#cursorLabel");
  const cpos = { x: -100, y: -100, tx: -100, ty: -100 };
  addEventListener("pointermove", (e) => {
    cpos.tx = e.clientX; cpos.ty = e.clientY;
    mouse.tx = e.clientX; mouse.ty = e.clientY;
  });
  if (finePointer) {
    document.addEventListener("pointerover", (e) => {
      const t = e.target.closest("[data-cursor], a, button");
      if (t) {
        cursor.classList.add("is-active");
        cursorLabel.textContent = t.dataset.cursor || "";
      } else {
        cursor.classList.remove("is-active");
      }
    });
  }

  /* ---------- Scroll-driven systems ---------- */
  const tc = $("#timecode");
  const pad = (n) => String(n).padStart(2, "0");
  let lastY = scrollY, velocity = 0;

  const prologue = $("#prologueText");
  prologue.innerHTML = prologue.textContent.trim().split(/\s+/).map((w) => `<span class="w">${w}</span>`).join(" ");
  const words = $$(".w", prologue);

  const work = $("#companies");
  const track = $("#workTrack");
  const scenes = $$(".scene", track);
  const workBar = $("#workBar");
  const sceneNow = $("#sceneNow");
  $("#sceneTotal").textContent = pad(scenes.length);
  const isMobile = () => innerWidth <= 760;

  function onScroll() {
    const y = scrollY;

    const frames = Math.floor(y / 3);
    const ff = frames % 24, s = Math.floor(frames / 24);
    tc.textContent = `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}:${pad(ff)}`;

    const r = prologue.getBoundingClientRect();
    const p = clamp((innerHeight * 0.85 - r.top) / (r.height + innerHeight * 0.35), 0, 1);
    const lit = Math.floor(p * words.length);
    words.forEach((w, i) => w.classList.toggle("on", i < lit));

    if (!isMobile()) {
      const wr = work.getBoundingClientRect();
      const wp = clamp(-wr.top / (wr.height - innerHeight), 0, 1);
      const max = track.scrollWidth - innerWidth;
      track.style.transform = `translate3d(${-wp * max}px,0,0)`;
      workBar.style.width = `${wp * 100}%`;
      sceneNow.textContent = pad(Math.min(scenes.length, Math.floor(wp * scenes.length) + 1));
    }
  }
  addEventListener("scroll", onScroll, { passive: true });

  /* ---------- Reel indicator ---------- */
  const reelNum = $("#reelNum"), reelName = $("#reelName");
  const navLinks = $$(".hud__nav a");
  const reelIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const s = e.target;
      reelNum.textContent = `REEL ${s.dataset.reel}`;
      reelName.textContent = s.dataset.reelName.toUpperCase();
      navLinks.forEach((a) => a.classList.toggle("is-current", a.getAttribute("href") === `#${s.id}`));
    });
  }, { rootMargin: "-50% 0px -50% 0px" });
  $$("[data-reel]").forEach((s) => reelIO.observe(s));

  /* ---------- Credits reveal ---------- */
  const credIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add("in"); credIO.unobserve(e.target); }
    });
  }, { rootMargin: "0px 0px -10% 0px" });
  $$("#creditsRoll > *").forEach((el) => credIO.observe(el));

  /* ---------- Career list reveal ---------- */
  const roleIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const i = [...e.target.parentNode.children].indexOf(e.target);
      setTimeout(() => e.target.classList.add("in"), (i % 4) * 90);
      roleIO.unobserve(e.target);
    });
  }, { rootMargin: "0px 0px -8% 0px" });
  $$(".roles > li").forEach((li) => roleIO.observe(li));

  /* ---------- Role modal ---------- */
  const roleModal = $("#roleModal");
  const openRole = (li) => {
    const more = $(".role__more", li);
    $(".role-modal__meta", roleModal).textContent = `${$(".role__yr", li).textContent} · ${$(".role__loc", li).textContent}`;
    $(".role-modal__title", roleModal).textContent = $(".role__title", li).textContent;
    $(".role-modal__co", roleModal).textContent = $(".role__co", li).textContent;
    $(".role-modal__body", roleModal).innerHTML = [...more.children].filter((el) => el.tagName !== "UL").map((el) => el.outerHTML).join("");
    $(".role-modal__skills", roleModal).innerHTML = $("ul", more).innerHTML;
    roleModal.showModal();
  };
  $$(".roles > li").forEach((li) => {
    li.addEventListener("click", () => openRole(li));
    li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openRole(li); } });
  });
  $(".role-modal__close", roleModal).addEventListener("click", () => roleModal.close());
  roleModal.addEventListener("click", (e) => {
    const r = roleModal.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) roleModal.close();
  });

  /* ---------- Media: reveals + click-to-play ---------- */
  const fadeIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const i = [...e.target.parentNode.children].indexOf(e.target);
      setTimeout(() => e.target.classList.add("in"), (i % 3) * 120);
      fadeIO.unobserve(e.target);
    });
  }, { rootMargin: "0px 0px -8% 0px" });
  $$(".quote, .screening > *").forEach((el) => { el.classList.add("fade"); fadeIO.observe(el); });

  const yt = $("#ytPlayer");
  const playYT = () => {
    if (yt.querySelector("iframe")) return;
    const f = document.createElement("iframe");
    f.src = `https://www.youtube-nocookie.com/embed/${yt.dataset.yt}?autoplay=1&rel=0`;
    f.allow = "autoplay; encrypted-media; picture-in-picture";
    f.allowFullscreen = true;
    f.title = "Solana Breakpoint 2025 fireside with Luke Judges";
    yt.appendChild(f);
  };
  yt.addEventListener("click", playYT);
  yt.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); playYT(); } });

  /* ---------- Stats count-up ---------- */
  const statIO = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const el = e.target;
      const end = +el.dataset.count, pre = el.dataset.prefix || "", suf = el.dataset.suffix || "";
      const t0 = performance.now(), dur = 1600;
      (function step(now) {
        const p = clamp((now - t0) / dur, 0, 1);
        el.textContent = `${pre}${Math.round(end * (1 - Math.pow(1 - p, 3)))}${suf}`;
        if (p < 1) requestAnimationFrame(step);
      })(t0);
      statIO.unobserve(el);
    });
  }, { threshold: 0.6 });
  if (!reduced) $$("[data-count]").forEach((el) => statIO.observe(el));

  /* ---------- Filmstrip drag ---------- */
  const strip = $("#strip");
  let dragging = false, dragged = false, sx0 = 0, sl0 = 0, sv = 0, lastX = 0;
  strip.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse") return;
    dragging = true; dragged = false; sx0 = lastX = e.clientX; sl0 = strip.scrollLeft; sv = 0;
  });
  strip.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    strip.scrollLeft = sl0 - (e.clientX - sx0);
    if (!dragged && Math.abs(e.clientX - sx0) > 6) {
      dragged = true;
      strip.setPointerCapture(e.pointerId);
    }
    sv = e.clientX - lastX; lastX = e.clientX;
  });
  const endDrag = () => {
    if (!dragging) return;
    dragging = false;
    (function glide() {
      sv *= 0.94;
      strip.scrollLeft -= sv;
      if (Math.abs(sv) > 0.3) requestAnimationFrame(glide);
    })();
  };
  addEventListener("pointerup", endDrag);
  strip.addEventListener("pointercancel", endDrag);
  strip.addEventListener("click", (e) => { if (dragged) { e.preventDefault(); dragged = false; } }, true);
  strip.addEventListener("dragstart", (e) => e.preventDefault());

  /* ---------- Video modal ---------- */
  const videoModal = $("#videoModal");
  const videoPlayer = $(".video-modal__player", videoModal);
  strip.addEventListener("click", (e) => {
    const a = e.target.closest("a.frame");
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    const id = new URL(a.href).searchParams.get("v");
    if (!/youtube\.com$/.test(new URL(a.href).hostname) || !id) return;
    e.preventDefault();
    const title = $("h4", a).textContent;
    $(".role-modal__meta", videoModal).textContent = `${$(".frame__type", a).textContent} · ${$(".frame__yr", a).textContent}`;
    $(".role-modal__title", videoModal).textContent = title;
    $(".video-modal__link", videoModal).href = a.href;
    const f = document.createElement("iframe");
    f.src = `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0&playsinline=1`;
    f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
    f.allowFullscreen = true;
    f.title = `${title} with Luke Judges`;
    videoPlayer.replaceChildren(f);
    if (audio && soundOn) setSound(false);
    videoModal.showModal();
  });
  $(".role-modal__close", videoModal).addEventListener("click", () => videoModal.close());
  videoModal.addEventListener("click", (e) => {
    const r = videoModal.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) videoModal.close();
  });
  videoModal.addEventListener("close", () => videoPlayer.replaceChildren());

  /* ---------- Deep house soundtrack (opt-in) ---------- */
  const soundBtn = $("#soundToggle"), soundLabel = $("#soundLabel");
  const BPM = 122;
  let audio = null;
  let lastKick = -1e9;

  const PROGRESSION = [
    { bass: 33, chord: [57, 60, 64, 67, 71] }, // Am9
    { bass: 29, chord: [53, 57, 60, 64, 67] }, // Fmaj9
    { bass: 38, chord: [50, 53, 57, 60, 64] }, // Dm9
    { bass: 28, chord: [52, 55, 59, 62, 69] }, // Em7(add11)
  ];
  const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);

  function buildAudio() {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();

    const master = ctx.createGain();
    master.gain.value = 0;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14; comp.ratio.value = 4; comp.attack.value = 0.005; comp.release.value = 0.2;
    const club = ctx.createBiquadFilter();
    club.type = "lowpass"; club.frequency.value = 380; club.Q.value = 0.9;
    master.connect(club).connect(comp).connect(ctx.destination);

    // Everything except the kick pumps against it.
    const duck = ctx.createGain();
    duck.connect(master);

    const noise = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
    const nd = noise.getChannelData(0);
    for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1;

    const reverb = ctx.createConvolver();
    const irLen = ctx.sampleRate * 2.4;
    const ir = ctx.createBuffer(2, irLen, ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const d = ir.getChannelData(c);
      for (let i = 0; i < irLen; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / irLen, 3.2);
    }
    reverb.buffer = ir;
    const revGain = ctx.createGain(); revGain.gain.value = 0.32;
    reverb.connect(revGain).connect(duck);

    const env = (param, t, peak, decay, start = 0.0001) => {
      param.cancelScheduledValues(t);
      param.setValueAtTime(start, t);
      param.linearRampToValueAtTime(peak, t + 0.004);
      param.exponentialRampToValueAtTime(0.0001, t + decay);
    };
    const noiseSrc = (t, dur) => {
      const s = ctx.createBufferSource();
      s.buffer = noise;
      s.start(t, Math.random() * 0.5, dur + 0.05);
      return s;
    };

    function kick(t) {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.setValueAtTime(150, t);
      o.frequency.exponentialRampToValueAtTime(44, t + 0.12);
      env(g.gain, t, 1.1, 0.42);
      o.connect(g).connect(master);
      o.start(t); o.stop(t + 0.5);

      duck.gain.cancelScheduledValues(t);
      duck.gain.setValueAtTime(0.22, t);
      duck.gain.linearRampToValueAtTime(1, t + 0.24);

      const delay = Math.max(0, (t - ctx.currentTime) * 1000);
      setTimeout(() => (lastKick = performance.now()), delay);
    }

    function clap(t) {
      const s = noiseSrc(t, 0.3), bp = ctx.createBiquadFilter(), g = ctx.createGain();
      bp.type = "bandpass"; bp.frequency.value = 1300; bp.Q.value = 0.8;
      g.gain.setValueAtTime(0.0001, t);
      for (let k = 0; k < 3; k++) {
        g.gain.setValueAtTime(0.55, t + k * 0.011);
        g.gain.exponentialRampToValueAtTime(0.08, t + k * 0.011 + 0.009);
      }
      g.gain.setValueAtTime(0.5, t + 0.034);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.26);
      s.connect(bp).connect(g);
      g.connect(duck); g.connect(reverb);
    }

    function hat(t, open, vel) {
      const s = noiseSrc(t, open ? 0.22 : 0.05), hp = ctx.createBiquadFilter(), g = ctx.createGain();
      hp.type = "highpass"; hp.frequency.value = open ? 7200 : 9000;
      env(g.gain, t, (open ? 0.22 : 0.12) * vel, open ? 0.2 : 0.045);
      s.connect(hp).connect(g).connect(duck);
    }

    function bass(t, midi) {
      const o = ctx.createOscillator(), lp = ctx.createBiquadFilter(), g = ctx.createGain();
      o.type = "sawtooth"; o.frequency.value = mtof(midi);
      lp.type = "lowpass"; lp.Q.value = 7;
      lp.frequency.setValueAtTime(950, t);
      lp.frequency.exponentialRampToValueAtTime(180, t + 0.16);
      env(g.gain, t, 0.34, 0.24);
      o.connect(lp).connect(g).connect(duck);
      o.start(t); o.stop(t + 0.3);
    }

    function stab(t, notes, len) {
      const lp = ctx.createBiquadFilter(), g = ctx.createGain();
      lp.type = "lowpass"; lp.Q.value = 3;
      lp.frequency.setValueAtTime(3200, t);
      lp.frequency.exponentialRampToValueAtTime(650, t + len);
      env(g.gain, t, 0.085, len + 0.15);
      lp.connect(g);
      g.connect(duck); g.connect(reverb);
      notes.forEach((n) => {
        [-7, 7].forEach((cents) => {
          const o = ctx.createOscillator();
          o.type = "sawtooth"; o.frequency.value = mtof(n); o.detune.value = cents;
          o.connect(lp);
          o.start(t); o.stop(t + len + 0.2);
        });
      });
    }

    const stepDur = 60 / BPM / 4;
    let step = 0, bar = 0;
    let next = ctx.currentTime + 0.08;

    function schedule(t, s, b) {
      const chord = PROGRESSION[b % PROGRESSION.length];
      const swingT = s % 2 ? t + stepDur * 0.14 : t;

      if (s % 4 === 0) kick(t);
      if (s % 4 === 2) hat(swingT, true, 1);
      else hat(swingT, false, s % 2 ? 0.7 : 0.45);
      if (b >= 2 && (s === 4 || s === 12)) clap(t);
      if (b >= 2 && [2, 6, 7, 10, 14, 15].includes(s)) bass(swingT, chord.bass + (s === 7 || s === 15 ? 12 : 0));
      if (b >= 4 && (s === 3 || s === 10 || (b % 2 && s === 14))) stab(swingT, chord.chord, s === 10 ? 0.45 : 0.22);
    }

    const timer = setInterval(() => {
      while (next < ctx.currentTime + 0.12) {
        schedule(next, step, bar);
        next += stepDur;
        if (++step === 16) { step = 0; bar++; }
      }
    }, 25);

    return {
      ctx, master, timer,
      setOpenness(p) {
        const f = 380 * Math.pow(18000 / 380, clamp(p, 0, 1));
        club.frequency.setTargetAtTime(f, ctx.currentTime, 0.15);
      },
    };
  }

  let soundOn = false;
  const setSound = (on) => {
    soundOn = on;
    if (!audio) audio = buildAudio();
    if (audio.ctx.state === "suspended") audio.ctx.resume();
    audio.master.gain.setTargetAtTime(soundOn ? 0.55 : 0, audio.ctx.currentTime, 0.4);
    soundBtn.setAttribute("aria-pressed", String(soundOn));
    soundLabel.textContent = soundOn ? `Sound on · ${BPM} BPM` : "Sound off";
  };
  soundBtn.addEventListener("click", () => setSound(!soundOn));

  // Browsers block audio until a user gesture, so on desktop sound starts on the first click or key press.
  // On phones it stays opt-in so a first tap never surprises anyone.
  if (!mobile) setSound(true);
  const unlock = (e) => {
    if (soundBtn.contains(e.target)) return;
    if (audio && soundOn && audio.ctx.state !== "running") audio.ctx.resume();
    ["pointerdown", "keydown", "touchend"].forEach((t) => removeEventListener(t, unlock, true));
  };
  ["pointerdown", "keydown", "touchend"].forEach((t) => addEventListener(t, unlock, true));
  document.addEventListener("visibilitychange", () => {
    if (!audio || !soundOn) return;
    document.hidden ? audio.ctx.suspend() : audio.ctx.resume();
  });

  /* ---------- Main loop ---------- */
  const root = document.documentElement;
  const portrait = $("#portrait");
  const heroTitle = $("#heroTitle");
  let bar = 0;
  function loop(now) {
    if (!reduced) drawGrain(now);
    drawHero(now);

    cpos.x = lerp(cpos.x, cpos.tx, 0.2);
    cpos.y = lerp(cpos.y, cpos.ty, 0.2);
    cursor.style.transform = `translate3d(${cpos.x}px, ${cpos.y}px, 0)`;

    const y = scrollY;
    if (heroVisible && !reduced) {
      const mx = (mouse.x / innerWidth - 0.5), my = (mouse.y / innerHeight - 0.5);
      portrait.style.transform = `translate3d(calc(-50% + ${mx * 18}px), ${y * 0.12 + my * 10}px, 0) scale(${1 + y * 0.00012})`;
      heroTitle.style.transform = `translate3d(${mx * -36}px, ${y * 0.45 + my * -14}px, 0)`;
      heroTitle.style.opacity = clamp(1 - y / (innerHeight * 0.7), 0, 1);
    }
    velocity = lerp(velocity, Math.abs(y - lastY), 0.15);
    lastY = y;
    const target = reduced ? 0 : clamp(velocity * 0.9, 0, innerHeight * 0.09);
    bar = lerp(bar, target, 0.12);
    root.style.setProperty("--bar", `${bar.toFixed(1)}px`);

    if (audio && soundOn) {
      audio.setOpenness(y / (innerHeight * 0.9));
      root.style.setProperty("--kick", Math.exp(-(now - lastKick) / 160).toFixed(3));
    }

    requestAnimationFrame(loop);
  }

  addEventListener("resize", () => { sizeGrain(); sizeHero(); onScroll(); });
  onScroll();
  requestAnimationFrame(loop);
})();
