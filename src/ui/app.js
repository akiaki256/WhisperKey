// 窓全体の動き(ヘッダーとタブの切り替え)。各タブの中身は、タブごとの js に書く

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

// 最初に開くのは一番上のタブ(入力履歴。いちばん動きのある場所)
showTab("history");
