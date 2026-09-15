// Faixa "em desenvolvimento" — compartilhada entre as páginas
(function () {
  const info = document.getElementById("devBannerInfo");
  const popover = document.getElementById("devPopover");
  if (!info || !popover) return;

  info.addEventListener("click", (e) => {
    e.stopPropagation();
    popover.classList.toggle("open");
  });

  document.addEventListener("click", (e) => {
    if (popover.classList.contains("open") && !popover.contains(e.target) && e.target !== info) {
      popover.classList.remove("open");
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") popover.classList.remove("open");
  });
})();
