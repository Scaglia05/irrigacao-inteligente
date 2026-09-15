(function () {
  const slides = Array.from(document.querySelectorAll(".slide"));
  const total = slides.length;
  const counter = document.getElementById("slideCounter");
  const dotsWrap = document.getElementById("slideDots");
  const progressBar = document.getElementById("deckProgress");
  const btnPrev = document.getElementById("btnPrevSlide");
  const btnNext = document.getElementById("btnNextSlide");
  const btnNotes = document.getElementById("btnToggleNotes");
  const deckEl = document.getElementById("deck");

  let current = 0;
  let notesVisible = false;

  slides.forEach((_, i) => {
    const dot = document.createElement("button");
    dot.className = "deck-dot";
    dot.type = "button";
    dot.setAttribute("aria-label", `Ir para slide ${i + 1}`);
    dot.addEventListener("click", () => goTo(i));
    dotsWrap.appendChild(dot);
  });
  const dots = Array.from(dotsWrap.children);

  function render() {
    slides.forEach((s, i) => s.classList.toggle("active", i === current));
    dots.forEach((d, i) => d.classList.toggle("active", i === current));
    counter.textContent = `${current + 1} / ${total}`;
    progressBar.style.width = `${((current + 1) / total) * 100}%`;
    btnPrev.disabled = current === 0;
    btnNext.disabled = current === total - 1;
    document.querySelectorAll(".notes-panel").forEach((n) => { n.hidden = !notesVisible; });
  }

  function goTo(i) {
    current = Math.max(0, Math.min(total - 1, i));
    render();
  }

  btnPrev.addEventListener("click", () => goTo(current - 1));
  btnNext.addEventListener("click", () => goTo(current + 1));
  btnNotes.addEventListener("click", () => {
    notesVisible = !notesVisible;
    btnNotes.classList.toggle("active", notesVisible);
    render();
  });

  window.addEventListener("keydown", (e) => {
    if (document.body.classList.contains("storm-active")) return;
    if (["ArrowRight", "PageDown"].includes(e.key)) goTo(current + 1);
    if (["ArrowLeft", "PageUp"].includes(e.key)) goTo(current - 1);
    if (e.key === "Home") goTo(0);
    if (e.key === "End") goTo(total - 1);
  });

  let touchX = null;
  deckEl.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; });
  deckEl.addEventListener("touchend", (e) => {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 50) goTo(current + (dx < 0 ? 1 : -1));
    touchX = null;
  });

  render();

  // ================= MODO TEMPESTADE =================
  const overlay = document.getElementById("stormOverlay");
  const rainLayer = document.getElementById("rainLayer");
  const deckWrap = document.getElementById("deckWrap");
  const btnStorm = document.getElementById("btnStorm");
  const btnStormClose = document.getElementById("btnStormClose");
  let stormInterval = null;

  function spawnRaindrops(n) {
    rainLayer.innerHTML = "";
    const frag = document.createDocumentFragment();
    for (let i = 0; i < n; i++) {
      const drop = document.createElement("span");
      drop.className = "raindrop";
      drop.style.left = `${Math.random() * 100}%`;
      drop.style.height = `${40 + Math.random() * 70}px`;
      drop.style.animationDuration = `${0.5 + Math.random() * 0.7}s`;
      drop.style.animationDelay = `${Math.random() * 2}s`;
      frag.appendChild(drop);
    }
    rainLayer.appendChild(frag);
  }

  function flashOnce() {
    overlay.classList.add("flash");
    deckWrap.classList.add("shake");
    setTimeout(() => {
      overlay.classList.remove("flash");
      deckWrap.classList.remove("shake");
    }, 220);
  }

  function startStorm() {
    overlay.hidden = false;
    document.body.classList.add("storm-active");
    spawnRaindrops(90);
    clearInterval(stormInterval);
    stormInterval = setInterval(flashOnce, 3000 + Math.random() * 3000);
  }

  function stopStorm() {
    overlay.hidden = true;
    document.body.classList.remove("storm-active");
    clearInterval(stormInterval);
    rainLayer.innerHTML = "";
  }

  btnStorm.addEventListener("click", () => {
    if (overlay.hidden) startStorm(); else stopStorm();
  });
  btnStormClose.addEventListener("click", stopStorm);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) stopStorm();
  });
  document.querySelectorAll(".rain-trigger").forEach((el) => {
    el.addEventListener("click", startStorm);
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !overlay.hidden) stopStorm();
  });
})();
