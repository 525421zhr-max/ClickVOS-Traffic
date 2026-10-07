"use strict";
const steps = [
  {label:"输入 / VIDEO",title:"先确认画面与目标。",description:"上传许可清楚的交通视频，抽帧后检查首帧。让目标足够清晰，是后续选择与传播的起点。",detail:"支持车辆、行人和非机动车类别。"},
  {label:"选择 / PROMPTS",title:"让每个目标有自己的提示。",description:"创建目标，在希望保留的区域添加正点，在误覆盖区域添加负点。切换目标后，可以继续标记同一画面里的其他对象。",detail:"多目标分别保存；正负点可以清空、追加与复核。"},
  {label:"传播 / MASKS",title:"把选择传播到后续帧。",description:"SAM2 根据提示生成逐帧掩码。浏览完整预览，同时查看异常提示，确认目标身份是否保持一致。",detail:"掩码数量完整，不等于目标边界已经准确。"},
  {label:"复核 / CORRECTION",title:"先试一帧，再决定整段。",description:"补点后可只更新首帧预览，检查副作用并撤销；也可以定位中间帧修正指定目标，再向后传播。",detail:"单帧预览保留正式输出；未应用的首帧提示会阻止导出旧结果。"},
  {label:"导出 / ANNOTATIONS",title:"带着结果和记录一起离开。",description:"下载 ZIP，获得逐对象二值掩码、合成预览、项目 JSON、COCO RLE，以及首帧补点与撤销记录。",detail:"源视频、抽帧图片与临时预览不会进入标注下载包。"}
];
const tabs = Array.from(document.querySelectorAll("[data-step]"));
let selected = 0;
function selectStep(index, focus) {
  selected = (index + steps.length) % steps.length;
  const step = steps[selected];
  tabs.forEach((tab, i) => {
    tab.classList.toggle("active", i === selected);
    tab.setAttribute("aria-selected", String(i === selected));
    tab.tabIndex = i === selected ? 0 : -1;
  });
  for (const [id, key] of [["panel-label","label"],["panel-title","title"],["panel-description","description"],["panel-detail","detail"]]) {
    document.getElementById(id).textContent = step[key];
  }
  document.getElementById("panel-symbol").src = `assets/icons/${["movie","focus-2","stack-2","adjustments-horizontal","file-export"][selected]}.svg`;
  document.getElementById("panel-counter").textContent = `${String(selected + 1).padStart(2,"0")} / 05`;
  document.getElementById("step-panel").setAttribute("aria-labelledby", `step-${selected}`);
  document.getElementById("next-step").firstChild.textContent = selected === 4 ? "回到第一步 " : "下一步 ";
  if (focus) tabs[selected].focus();
}
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectStep(index, false));
  tab.addEventListener("keydown", event => {
    const keys = {ArrowDown:index + 1, ArrowUp:index - 1, Home:0, End:steps.length - 1};
    if (Object.hasOwn(keys, event.key)) {event.preventDefault();selectStep(keys[event.key], true);}
  });
});
document.getElementById("next-step").addEventListener("click", () => selectStep(selected + 1, false));
