document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copy);
      if (!target) return;
      await navigator.clipboard.writeText(target.textContent.trim());
      const previous = button.textContent;
      button.textContent = "已复制";
      window.setTimeout(() => { button.textContent = previous; }, 1200);
    });
  });
});
