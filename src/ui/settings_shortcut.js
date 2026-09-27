// ショートカットタブのキーの割り当て(キーを押して決める)
//
// 1. ボタンを押す → Python に今のキーの登録を外してもらう(今のキーも画面に届くように)
// 2. キーを押す → "ctrl+alt+f9" の形にして Python に送る。Python が登録・保存する
//    使えないキー・ほかのソフトが使用中のときは、Python が元のキーを登録し直してエラーを返す
// 3. Esc・ほかの場所をクリック・窓から離れる → 取り消し(元のキーを登録し直す)

const shortcutButton = document.getElementById("btn-shortcut");
let capturing = false;

// "ctrl+space" → "Ctrl + Space"
function formatShortcut(keyStr) {
  const names = { ctrl: "Ctrl", alt: "Alt", shift: "Shift", space: "Space", enter: "Enter" };
  return keyStr
    .split("+")
    .map((part) => names[part] ?? part.toUpperCase())
    .join(" + ");
}

// 起動時に登録できなかったときの知らせの文。kind は "taken" / "invalid" / "failed"
function startupShortcutMessage(kind, keyStr) {
  if (kind === "taken") {
    return `「${formatShortcut(keyStr)}」はほかのソフトが使用中のため、登録できませんでした。別のキーを割り当ててください`;
  }
  if (kind === "invalid") {
    return `設定されているキー「${keyStr}」を読み込めませんでした。キーを割り当て直してください`;
  }
  return `「${formatShortcut(keyStr)}」を登録できませんでした。キーを割り当て直してください`;
}

function showShortcut(keyStr) {
  shortcutButton.dataset.value = keyStr;
  shortcutButton.textContent = formatShortcut(keyStr);
}

// 押されたキー(e.code)を、Python の parse_shortcut が読める名前にする。使えないキーなら null
// e.key ではなく e.code を使う(Shift を押していても "A" と "a" が同じになる、キーの場所で決まる)
function mainKeyName(code) {
  if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) return code.toLowerCase();   // F1〜F24
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();        // KeyA → a
  if (/^Digit[0-9]$/.test(code)) return code.slice(5);                    // Digit1 → 1
  if (code === "Space") return "space";
  if (code === "Enter") return "enter";
  return null;
}

async function startCapture() {
  capturing = true;
  showError(null);
  shortcutButton.classList.add("capturing");
  shortcutButton.textContent = "キーを押してください(Esc で取り消し)";
  await window.pywebview.api.begin_shortcut_capture();
}

async function finishCapture(keyStr) {
  if (!capturing) return;
  capturing = false;
  shortcutButton.classList.remove("capturing");

  const result = await window.pywebview.api.end_shortcut_capture(keyStr);
  showShortcut(result.value);
  showError(result.error);
}

// キーを待っているあいだは、押されたキーをすべてここで受け取る(ほかの動きをさせない)
// capture: true で、ほかの要素より先に受け取る
document.addEventListener("keydown", (e) => {
  if (!capturing) return;
  e.preventDefault();
  e.stopPropagation();

  if (e.code === "Escape") {
    finishCapture(null);
    return;
  }
  // Ctrl・Alt・Shift だけが押された時点では、まだ決めない(続けてメインのキーが押されるのを待つ)
  if (["Control", "Alt", "Shift", "Meta"].includes(e.key)) return;

  const main = mainKeyName(e.code);
  if (main === null) {
    shortcutButton.textContent = "このキーは使えません。別のキーを押してください";
    return;
  }

  const parts = [];
  if (e.ctrlKey) parts.push("ctrl");
  if (e.altKey) parts.push("alt");
  if (e.shiftKey) parts.push("shift");
  parts.push(main);
  finishCapture(parts.join("+"));
}, true);

shortcutButton.addEventListener("click", () => {
  if (!capturing) startCapture();
});

// ほかの場所をクリックしたり、窓から離れたりしたら取り消す
document.addEventListener("mousedown", (e) => {
  if (capturing && e.target !== shortcutButton) finishCapture(null);
});
window.addEventListener("blur", () => finishCapture(null));
