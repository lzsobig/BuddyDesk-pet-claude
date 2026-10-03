"use strict";

document.documentElement.classList.replace("no-js", "js");
const opening = document.querySelector(".hero-wrapper");
const openingText = opening.querySelector(".text-layer");
const openingCards = [...opening.querySelectorAll(".card-wrap")];
const scrollHint = document.querySelector("#scrollHint");
const openingMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const cardPositions = [
  [-45, -30, -18, -360, -300, -25],
  [60, -45, -8, 360, -280, 22],
  [0, 0, 4, -560, 120, -12],
  [-35, 35, 12, 560, 140, 17],
  [45, 30, 19, 0, 460, 0],
];
let openingProgress = 0;
let openingFrame = 0;
function renderOpening() {
  openingFrame = 0;
  if (openingMotion.matches) {
    opening.classList.remove("hero-animated");
    openingText.style.opacity = "";
    openingText.style.transform = "";
    return;
  }
  opening.classList.add("hero-animated");
  const distance = Math.max(1, opening.offsetHeight - window.innerHeight);
  const target = Math.max(
    0,
    Math.min(1, -opening.getBoundingClientRect().top / distance),
  );
  openingProgress += (target - openingProgress) * 0.13;
  if (Math.abs(target - openingProgress) < 0.001) openingProgress = target;
  const mobileScale = window.innerWidth <= 600 ? 0.7 : 1;
  openingCards.forEach((card, index) => {
    const [x, y, rotation, spreadX, spreadY, spreadRotation] =
      cardPositions[index];
    card.style.transform = `translate3d(${x + spreadX * openingProgress * mobileScale}px, ${y + spreadY * openingProgress * mobileScale}px, 0) rotate(${rotation + spreadRotation * openingProgress}deg) scale(${1 - 0.2 * openingProgress})`;
  });
  openingText.style.opacity = String(openingProgress);
  openingText.style.transform = `scale(${0.5 + 0.5 * openingProgress})`;
  scrollHint.style.opacity = String(Math.max(0, 1 - openingProgress * 4));
  if (Math.abs(target - openingProgress) > 0.001)
    openingFrame = window.requestAnimationFrame(renderOpening);
}
function updateOpening() {
  if (!openingFrame) openingFrame = window.requestAnimationFrame(renderOpening);
}
window.addEventListener("scroll", updateOpening, { passive: true });
window.addEventListener("resize", updateOpening);
openingMotion.addEventListener("change", updateOpening);
renderOpening();

const menuButton = document.querySelector(".menu-toggle");
const navigation = document.querySelector("#nav-links");
function closeMenu() {
  navigation.classList.remove("open");
  menuButton.setAttribute("aria-expanded", "false");
}
menuButton.addEventListener("click", () => {
  const open = menuButton.getAttribute("aria-expanded") !== "true";
  menuButton.setAttribute("aria-expanded", String(open));
  navigation.classList.toggle("open", open);
});
navigation.addEventListener("click", (event) => {
  if (event.target.closest("a")) closeMenu();
});
document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    menuButton.getAttribute("aria-expanded") === "true"
  ) {
    closeMenu();
    menuButton.focus();
  }
});

const scene = document.querySelector("#desktop-scene");
const trigger = document.querySelector("#demo-trigger");
const statusLabel = document.querySelector("#island-status");
const triggerLabel = document.querySelector("#trigger-label");
const islandContent = document.querySelector("#island-content");
const transcript = document.querySelector("#demo-transcript");
const draft = document.querySelector("#demo-draft");
const today = document.querySelector("#demo-today");
const pet = document.querySelector("#demo-pet");
const confirmButton = document.querySelector("#confirm-demo");
const petSpot = document.querySelector(".pet-spot");
const petButton = document.querySelector(".pet-touch");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let demoGeneration = 0;
const demoTimers = new Set();

function schedule(callback, milliseconds, generation) {
  const timer = window.setTimeout(() => {
    demoTimers.delete(timer);
    if (generation === demoGeneration) callback();
  }, milliseconds);
  demoTimers.add(timer);
}

function resetDemo() {
  demoGeneration += 1;
  demoTimers.forEach(window.clearTimeout);
  demoTimers.clear();
  scene.dataset.state = "idle";
  statusLabel.textContent = "小橘在身边";
  triggerLabel.textContent = "按一下，试试";
  trigger.disabled = false;
  islandContent.hidden = true;
  transcript.hidden = true;
  draft.hidden = true;
  today.hidden = true;
  pet.src = "assets/companion-idle.png";
  petSpot.style.transform = "";
  document.querySelector("#draft-one").value = "结构力学课";
  document.querySelector("#draft-two").value = "给老师发送材料";
  document.querySelectorAll(".task-dot").forEach((button) => {
    button.setAttribute("aria-pressed", "false");
    button.closest(".demo-task").classList.remove("completed");
  });
}

function startDemo(keyboardInitiated = false) {
  resetDemo();
  const generation = demoGeneration;
  scene.dataset.state = "listening";
  statusLabel.textContent = "小橘在听";
  trigger.disabled = true;
  triggerLabel.textContent = "把想做的事，说给小橘听";
  islandContent.hidden = false;
  transcript.hidden = false;
  transcript.textContent = "“下午两点上课，晚上八点提醒我给老师发材料。”";
  schedule(
    () => {
      scene.dataset.state = "thinking";
      statusLabel.textContent = "正在琢磨";
      pet.src = "assets/companion-thinking.png";
      triggerLabel.textContent = "先理解，再整理";
    },
    reducedMotion.matches ? 350 : 1200,
    generation,
  );
  schedule(
    () => {
      scene.dataset.state = "draft";
      statusLabel.textContent = "整理好了，你来核对";
      transcript.hidden = true;
      draft.hidden = false;
      triggerLabel.textContent = "修改标题，再点“放到今天”";
      pet.src = "assets/companion-idle.png";
      trigger.disabled = false;
      if (
        keyboardInitiated &&
        [document.body, trigger].includes(document.activeElement)
      ) {
        document.querySelector("#draft-one").focus({ preventScroll: true });
      }
    },
    reducedMotion.matches ? 700 : 2600,
    generation,
  );
}

trigger.addEventListener("click", (event) => {
  if (scene.dataset.state === "draft") {
    document.querySelector("#draft-one").focus();
    return;
  }
  startDemo(event.detail === 0);
});
document.querySelector("#demo-reset").addEventListener("click", () => {
  resetDemo();
  trigger.focus({ preventScroll: true });
});
confirmButton.addEventListener("click", () => {
  const titles = ["one", "two"].map((id) =>
    document.querySelector(`#draft-${id}`).value.trim(),
  );
  const missing = titles.findIndex((title) => !title);
  if (missing !== -1) {
    statusLabel.textContent = "先给事项一个名字";
    document.querySelector(`#draft-${["one", "two"][missing]}`).focus();
    return;
  }
  ["one", "two"].forEach((id, index) => {
    document.querySelector(`#task-${id}`).textContent = titles[index];
    const button = document
      .querySelector(`#task-${id}`)
      .closest(".demo-task")
      .querySelector("button");
    button.setAttribute("aria-label", `完成${titles[index]}`);
  });
  scene.dataset.state = "tasks";
  statusLabel.textContent = "已放到今天";
  draft.hidden = true;
  today.hidden = false;
  triggerLabel.textContent = "点圆圈，试试完成和撤销";
  document.querySelector("#demo-completion").textContent =
    "做好一件，就轻一点。";
  document.querySelector(".task-dot").focus({ preventScroll: true });
});
document.querySelectorAll(".task-dot").forEach((button) => {
  button.addEventListener("click", () => {
    const complete = button.getAttribute("aria-pressed") !== "true";
    button.setAttribute("aria-pressed", String(complete));
    button.closest(".demo-task").classList.toggle("completed", complete);
    const title = button
      .closest(".demo-task")
      .querySelector("div > span").textContent;
    button.setAttribute(
      "aria-label",
      `${complete ? "撤销完成" : "完成"}${title}`,
    );
    const done = document.querySelectorAll(
      '.task-dot[aria-pressed="true"]',
    ).length;
    document.querySelector("#demo-completion").textContent =
      done === 2
        ? "两件事都做好了，歇一会儿。"
        : `${done} / 2 已完成 · 再点一次可撤销`;
    statusLabel.textContent = done === 2 ? "今天，又轻松一点。" : "小橘在身边";
  });
});
let drag = null;
let suppressPetClick = false;
petButton.addEventListener("click", () => {
  if (suppressPetClick) return;
  petSpot.classList.remove("petted");
  void petSpot.offsetWidth;
  petSpot.classList.add("petted");
});
petSpot.addEventListener("animationend", () =>
  petSpot.classList.remove("petted"),
);
petButton.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  const bounds = petSpot.getBoundingClientRect();
  const stage = scene.getBoundingClientRect();
  drag = {
    pointer: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    startX: bounds.left - stage.left,
    startY: bounds.top - stage.top,
    stage,
    moved: false,
  };
  suppressPetClick = false;
  petButton.setPointerCapture(event.pointerId);
});
petButton.addEventListener("pointermove", (event) => {
  if (!drag || drag.pointer !== event.pointerId) return;
  const dx = event.clientX - drag.x;
  const dy = event.clientY - drag.y;
  if (Math.abs(dx) + Math.abs(dy) > 5) drag.moved = true;
  if (!drag.moved) return;
  const baseX =
    scene.clientWidth -
    petSpot.offsetWidth -
    parseFloat(getComputedStyle(petSpot).right);
  const baseY =
    scene.clientHeight -
    petSpot.offsetHeight -
    parseFloat(getComputedStyle(petSpot).bottom);
  const x = Math.max(
    0,
    Math.min(scene.clientWidth - petSpot.offsetWidth, drag.startX + dx),
  );
  const y = Math.max(
    100,
    Math.min(scene.clientHeight - petSpot.offsetHeight - 44, drag.startY + dy),
  );
  petSpot.style.transform = `translate(${x - baseX}px, ${y - baseY}px)`;
});
function endPetDrag(event) {
  if (!drag || drag.pointer !== event.pointerId) return;
  suppressPetClick = drag.moved;
  drag = null;
  if (petButton.hasPointerCapture(event.pointerId))
    petButton.releasePointerCapture(event.pointerId);
}
petButton.addEventListener("pointerup", endPetDrag);
petButton.addEventListener("pointercancel", endPetDrag);
petButton.addEventListener("keydown", () => {
  suppressPetClick = false;
});

const installationTabs = [...document.querySelectorAll("[data-tab]")];
function selectInstallationTab(tab) {
  installationTabs.forEach((button) => {
    const selected = button === tab;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    document.querySelector(`#panel-${button.dataset.tab}`).hidden = !selected;
  });
}
installationTabs.forEach((button, index) => {
  button.addEventListener("click", () => selectInstallationTab(button));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? installationTabs.length - 1
          : (index +
              (event.key === "ArrowRight" ? 1 : -1) +
              installationTabs.length) %
            installationTabs.length;
    selectInstallationTab(installationTabs[next]);
    installationTabs[next].focus();
  });
});
document.querySelectorAll("[data-copy]").forEach((button) => {
  let feedbackTimer;
  button.addEventListener("click", async () => {
    const command = document.getElementById(button.dataset.copy).textContent;
    try {
      if (!navigator.clipboard || !window.isSecureContext)
        throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(command);
      button.textContent = "已复制";
    } catch {
      const range = document.createRange();
      range.selectNodeContents(document.getElementById(button.dataset.copy));
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = "已选中，请 Ctrl+C";
    }
    window.clearTimeout(feedbackTimer);
    feedbackTimer = window.setTimeout(() => {
      button.textContent = "复制";
    }, 2600);
  });
});
