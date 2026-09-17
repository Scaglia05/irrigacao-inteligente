// Alternância de tema claro/escuro — compartilhada entre as páginas.
// A escolha (ou o default do sistema) já é aplicada por um script inline
// no <head>, antes do CSS pintar, para não piscar o tema errado.
(function () {
  const KEY = "irrigacao-tema";
  const root = document.documentElement;
  const btn = document.getElementById("themeToggle");
  if (!btn) return;

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    btn.textContent = theme === "dark" ? "☀️" : "🌙";
    btn.title = theme === "dark" ? "Mudar para tema claro" : "Mudar para tema escuro";
  }

  apply(root.getAttribute("data-theme") || "light");

  btn.addEventListener("click", () => {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    localStorage.setItem(KEY, next);
    apply(next);
    document.dispatchEvent(new CustomEvent("themechange", { detail: { theme: next } }));
  });
})();
