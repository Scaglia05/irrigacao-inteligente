(function () {
  const slides = Array.from(document.querySelectorAll(".slide"));
  const total = slides.length;
  const counter = document.getElementById("slideCounter");
  const dotsWrap = document.getElementById("slideDots");
  const progressBar = document.getElementById("deckProgress");
  const btnPrev = document.getElementById("btnPrevSlide");
  const btnNext = document.getElementById("btnNextSlide");
  const deckEl = document.getElementById("deck");

  let current = 0;

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
  }

  function goTo(i) {
    current = Math.max(0, Math.min(total - 1, i));
    render();
  }

  btnPrev.addEventListener("click", () => goTo(current - 1));
  btnNext.addEventListener("click", () => goTo(current + 1));

  window.addEventListener("keydown", (e) => {
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

  // ================= CHUVA NOS SLIDES DE TEMPESTADE =================
  document.querySelectorAll(".slide-chuva .rain-drops").forEach((container) => {
    const frag = document.createDocumentFragment();
    for (let i = 0; i < 45; i++) {
      const drop = document.createElement("span");
      drop.className = "drop";
      drop.style.left = `${Math.random() * 100}%`;
      drop.style.height = `${30 + Math.random() * 50}px`;
      drop.style.animationDuration = `${0.5 + Math.random() * 0.7}s`;
      drop.style.animationDelay = `${Math.random() * 2}s`;
      frag.appendChild(drop);
    }
    container.appendChild(frag);
  });
})();
