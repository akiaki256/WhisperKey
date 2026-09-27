// 仮の画面の動き(骨組みの動作確認用)

// タブを切り替える。Python 側(main_window.show)からも呼ばれる
function showTab(name) {
  document.querySelectorAll("nav button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll("main section").forEach((sec) => {
    sec.classList.toggle("active", sec.id === `tab-${name}`);
  });
}

document.querySelectorAll("nav button").forEach((btn) => {
  btn.addEventListener("click", () => showTab(btn.dataset.tab));
});

document.getElementById("btn-minimize").addEventListener("click", () => {
  window.pywebview.api.minimize();
});

document.getElementById("btn-close").addEventListener("click", () => {
  window.pywebview.api.close();
});

document.getElementById("btn-legacy-config").addEventListener("click", () => {
  window.pywebview.api.open_legacy_config();
});

showTab("shortcuts");
