// ショートカットタブのキーの割り当て(キーを押して決める)
// ボタンの data-action が役割("toggle" = 音声入力、"mode" = 入力モード切り替え、"undo" = 直前の入力を取り消す、
// "candidates" = 候補を出す(GPU版だけ。CPU版ではカードごと隠れていて、settings.js にも届かない))
//
// 1. ボタンを押す → Python に全部のキーの登録を一旦外してもらう(どのキーも画面に届くように)
// 2. キーを押す → "ctrl+alt+f9" の形にして Python に送る。Python が登録・保存し、ほかの役割も登録し直す
//    使えないキー・ほかのソフトが使用中のときは、Python が元のキーを登録し直してエラーを返す
// 3. Esc・ほかの場所をクリック・窓から離れる → 取り消し(元のキーを登録し直す)
// × ボタン(shortcut-clear)は「割り当てない」

const shortcutButtons = document.querySelectorAll(".shortcut-button");
let capturingButton = null;   // キーを待っているボタン(待っていなければ null)

// "ctrl+space" → "Ctrl + Space"
function formatShortcut(keyStr) {
  const names = { ctrl: "Ctrl", alt: "Alt", shift: "Shift", space: "Space", enter: "Enter" };
  return keyStr
    .split("+")
    .map((part) => names[part] ?? part.toUpperCase())
    .join(" + ");
}

// 起動時に登録できなかったときの知らせの文。kind は "taken" / "invalid" / "failed"
function startupShortcutMessage(label, kind, keyStr) {
  if (kind === "taken") {
    return `「${label}」の「${formatShortcut(keyStr)}」はほかのソフトが使用中のため、登録できませんでした。別のキーを割り当ててください`;
  }
  if (kind === "invalid") {
    return `「${label}」に設定されているキー「${keyStr}」を読み込めませんでした。キーを割り当て直してください`;
  }
  return `「${label}」の「${formatShortcut(keyStr)}」を登録できませんでした。キーを割り当て直してください`;
}

function buttonFor(action) {
  return document.querySelector(`.shortcut-button[data-action="${action}"]`);
}

// 役割のキーを表示する。"" なら「割り当てなし」で、× ボタンを隠す
function showShortcut(action, keyStr) {
  const button = buttonFor(action);
  button.dataset.value = keyStr;
  button.textContent = keyStr ? formatShortcut(keyStr) : "割り当てなし";
  const clear = document.querySelector(`.shortcut-clear[data-action="${action}"]`);
  if (clear) clear.hidden = !keyStr;
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

async function startCapture(button) {
  capturingButton = button;
  showError(null);
  button.classList.add("capturing");
  button.textContent = "キーを押してください(Esc で取り消し)";
  await window.pywebview.api.begin_shortcut_capture();
}

// keyStr: 押されたキー。null なら取り消し、"" なら割り当てない
async function finishCapture(keyStr) {
  const button = capturingButton;
  if (!button) return;
  capturingButton = null;
  button.classList.remove("capturing");
  await saveShortcut(button.dataset.action, keyStr);
}

async function saveShortcut(action, keyStr) {
  const result = await window.pywebview.api.end_shortcut_capture(action, keyStr);
  showShortcut(action, result.value);
  showError(result.error);
}

// キーを待っているあいだは、押されたキーをすべてここで受け取る(ほかの動きをさせない)
// capture: true で、ほかの要素より先に受け取る
document.addEventListener("keydown", (e) => {
  if (!capturingButton) return;
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
    capturingButton.textContent = "このキーは使えません。別のキーを押してください";
    return;
  }

  const parts = [];
  if (e.ctrlKey) parts.push("ctrl");
  if (e.altKey) parts.push("alt");
  if (e.shiftKey) parts.push("shift");
  parts.push(main);
  finishCapture(parts.join("+"));
}, true);

shortcutButtons.forEach((button) => {
  button.addEventListener("click", () => {
    if (!capturingButton) startCapture(button);
  });
});

document.querySelectorAll(".shortcut-clear").forEach((clear) => {
  clear.addEventListener("click", () => saveShortcut(clear.dataset.action, ""));
});

// ほかの場所をクリックしたり、窓から離れたりしたら取り消す
document.addEventListener("mousedown", (e) => {
  if (capturingButton && e.target !== capturingButton) finishCapture(null);
});
window.addEventListener("blur", () => finishCapture(null));
