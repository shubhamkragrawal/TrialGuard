import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const {
  SKILL_DIR,
  TMP_DIR,
  FINAL_PPTX,
  RUNTIME_PYTHON,
} = process.env;

for (const [name, value] of Object.entries({
  SKILL_DIR,
  TMP_DIR,
  FINAL_PPTX,
  RUNTIME_PYTHON,
})) {
  if (!path.isAbsolute(value ?? "")) {
    throw new Error(`${name} must be an absolute path`);
  }
}

const workspaceDir = process.cwd();
const {
  finalizePresentation,
  resolvePresentationFont,
} = await import(
  pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href
);

const FONT = resolvePresentationFont({ fontFamily: "Avenir Next" });
const W = 1280;
const H = 720;
const REPORT_IMAGE_PATH = path.join(
  workspaceDir,
  "slides/assets/trialguard-report.png"
);
const reportImageBytes = await fs.readFile(REPORT_IMAGE_PATH);

const C = {
  navy: "#0A2538",
  ink: "#15354A",
  teal: "#0A8A88",
  tealDark: "#08706F",
  aqua: "#BEEBE4",
  mint: "#EAF7F4",
  ice: "#F5FAF9",
  white: "#FFFFFF",
  fog: "#D7E6E3",
  gray: "#627781",
  pale: "#EEF4F3",
  coral: "#E56B52",
  sand: "#FFF6E9",
};

const presentation = Presentation.create({
  slideSize: { width: W, height: H },
});

function addShape(slide, {
  x,
  y,
  w,
  h,
  geometry = "rect",
  fill = "none",
  lineFill = "none",
  lineWidth = 0,
}) {
  return slide.shapes.add({
    geometry,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { fill: lineFill, width: lineWidth },
  });
}

function addText(slide, text, {
  x,
  y,
  w,
  h,
  size = 24,
  color = C.ink,
  bold = false,
  align = "left",
  valign = "top",
}) {
  const shape = addShape(slide, { x, y, w, h });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: size,
    color,
    bold,
    alignment: align,
    verticalAlignment: valign,
    autoFit: "none",
  };
  return shape;
}

function addLine(slide, x, y, w, h, color = C.fog, width = 1) {
  return addShape(slide, {
    x,
    y,
    w,
    h,
    geometry: "line",
    lineFill: color,
    lineWidth: width,
  });
}

function addRightArrow(slide, x, y, w = 32, h = 18, color = C.aqua) {
  return addShape(slide, {
    x, y, w, h, geometry: "rightArrow", fill: color,
  });
}

function addDownArrow(slide, x, y, w = 18, h = 24, color = C.aqua) {
  return addShape(slide, {
    x, y, w, h, geometry: "downArrow", fill: color,
  });
}

function addSlideTitle(slide, number, title, subtitle = "") {
  addText(slide, String(number).padStart(2, "0"), {
    x: 64, y: 49, w: 54, h: 33, size: 17, color: C.teal, bold: true,
  });
  addText(slide, title, {
    x: 64, y: 79, w: 1080, h: 58, size: 46, color: C.navy, bold: true,
  });
  if (subtitle) {
    addText(slide, subtitle, {
      x: 66, y: 138, w: 1060, h: 42, size: 22, color: C.gray,
    });
  }
  addLine(slide, 64, 188, 1152, 0, C.fog, 1);
}

function addFooter(slide, number, invert = false) {
  const color = invert ? C.aqua : C.gray;
  addText(slide, "TRIALGUARD  ·  PRESENTATION DECK", {
    x: 64, y: 676, w: 340, h: 20, size: 12, color, bold: true,
  });
  addText(slide, String(number).padStart(2, "0"), {
    x: 1160, y: 676, w: 56, h: 20, size: 12, color, bold: true, align: "right",
  });
}

function setNotes(slide, text) {
  slide.speakerNotes.textFrame.setText(text);
}

// Slide 1: title
{
  const slide = presentation.slides.add();
  slide.background.fill = C.navy;
  addShape(slide, { x: 955, y: 0, w: 325, h: 720, fill: C.teal });
  addShape(slide, { x: 955, y: 0, w: 18, h: 720, fill: C.aqua });
  addText(slide, "HACKATHON DECISION-SUPPORT DEMONSTRATION", {
    x: 74, y: 70, w: 720, h: 30, size: 15, color: C.aqua, bold: true,
  });
  addText(slide, "TrialGuard", {
    x: 70, y: 165, w: 790, h: 96, size: 82, color: C.white, bold: true,
  });
  addText(slide, "Evidence-linked operational review questions from public trial records", {
    x: 74, y: 285, w: 770, h: 106, size: 31, color: C.white,
  });
  addLine(slide, 74, 430, 120, 0, C.aqua, 5);
  addText(slide, "For clinical operations and trial-review teams", {
    x: 74, y: 455, w: 700, h: 38, size: 20, color: C.aqua,
  });
  addText(slide, "PUBLIC RECORD", {
    x: 1012, y: 152, w: 210, h: 30, size: 16, color: C.white, bold: true,
  });
  addText(slide, "BOUNDED COHORT", {
    x: 1012, y: 252, w: 210, h: 30, size: 16, color: C.white, bold: true,
  });
  addText(slide, "RELEASE GATE", {
    x: 1012, y: 352, w: 210, h: 30, size: 16, color: C.white, bold: true,
  });
  addLine(slide, 1012, 204, 146, 0, C.aqua, 2);
  addLine(slide, 1012, 304, 146, 0, C.aqua, 2);
  addLine(slide, 1012, 404, 146, 0, C.aqua, 2);
  addText(slide, "IMPLEMENTED DEMONSTRATION", {
    x: 74, y: 650, w: 260, h: 22, size: 12, color: C.aqua, bold: true,
  });
  setNotes(
    slide,
    "Source: TrialGuard Development Plan, sections 1 and 15. TrialGuard is a bounded decision-support demonstration, not a clinical decision system."
  );
}

// Slide 2: problem
{
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addSlideTitle(
    slide,
    2,
    "The trial review problem",
    "Operational review starts with fragments spread across public records"
  );

  const columns = [
    {
      n: "01",
      label: "CONTEXT",
      text: "A trial status has little meaning without a bounded peer cohort.",
    },
    {
      n: "02",
      label: "COMPARABILITY",
      text: "Phase, condition, intervention, and design vary across candidate records.",
    },
    {
      n: "03",
      label: "VERIFICATION",
      text: "Stop reasons must trace back to the exact source field and registry record.",
    },
  ];
  columns.forEach((item, i) => {
    const x = 66 + i * 385;
    addText(slide, item.n, {
      x, y: 235, w: 72, h: 55, size: 38, color: C.aqua, bold: true,
    });
    addText(slide, item.label, {
      x, y: 302, w: 300, h: 28, size: 15, color: C.teal, bold: true,
    });
    addText(slide, item.text, {
      x, y: 347, w: 325, h: 118, size: 25, color: C.ink,
    });
    if (i < columns.length - 1) {
      addLine(slide, x + 350, 230, 0, 250, C.fog, 1);
    }
  });

  addShape(slide, { x: 64, y: 525, w: 1152, h: 102, fill: C.mint });
  addText(
    slide,
    "A useful review keeps source links visible and leaves the decision with a qualified reviewer. Uncertainty stays explicit.",
    {
      x: 96, y: 548, w: 1088, h: 58, size: 25, color: C.navy, bold: true,
      align: "center", valign: "middle",
    }
  );
  addFooter(slide, 2);
  setNotes(
    slide,
    "Source: TrialGuard Development Plan, sections 1, 4, and 7. No external statistics appear on this template slide."
  );
}

// Slide 3: product workflow
{
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addSlideTitle(
    slide,
    3,
    "Product workflow",
    "One NCT ID becomes a checked review brief with visible evidence"
  );

  const steps = [
    ["01", "Validate", "Confirm the NCT ID before any model call."],
    ["02", "Retrieve", "Load an allowlisted public trial record."],
    ["03", "Compare", "Build the cohort and rank stopped precedents."],
    ["04", "Draft", "Create evidence-linked review questions."],
    ["05", "Release", "Challenge the draft and apply deterministic checks."],
  ];
  steps.forEach((item, i) => {
    const y = 224 + i * 78;
    addShape(slide, {
      x: 70, y: y + 2, w: 42, h: 42, geometry: "ellipse",
      fill: i === 4 ? C.coral : C.teal, lineFill: "none",
    });
    addText(slide, item[0], {
      x: 70, y: y + 9, w: 42, h: 26, size: 13, color: C.white,
      bold: true, align: "center", valign: "middle",
    });
    addText(slide, item[1], {
      x: 132, y, w: 160, h: 28, size: 23, color: C.navy, bold: true,
    });
    addText(slide, item[2], {
      x: 132, y: y + 31, w: 360, h: 38, size: 17, color: C.gray,
    });
    if (i < steps.length - 1) {
      addLine(slide, 91, y + 45, 0, 33, C.aqua, 3);
    }
  });

  addShape(slide, {
    x: 550, y: 218, w: 665, h: 418,
    fill: C.ice, lineFill: C.teal, lineWidth: 2,
  });
  addText(slide, "CHECKED DEMO REPORT", {
    x: 550, y: 198, w: 240, h: 16, size: 10, color: C.teal, bold: true,
  });
  slide.images.add({
    blob: reportImageBytes,
    contentType: "image/png",
    alt: "TrialGuard checked evidence review for NCT06860815",
    fit: "contain",
    position: { left: 558, top: 226, width: 649, height: 406 },
  });
  addFooter(slide, 3);
  setNotes(
    slide,
    "Source: TrialGuard Development Plan, sections 4 and 15. Product image: slides/assets/trialguard-report.png, captured from the implemented checked-report view."
  );
}

// Slide 4: intended AWS architecture
{
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addSlideTitle(
    slide,
    4,
    "System architecture",
    "The intended AWS design keeps model output inside a deterministic release path"
  );

  const node = ({
    x, y, w, h, eyebrow, title, detail = "",
    fill = C.white, border = C.teal, titleColor = C.navy,
    eyebrowColor = C.teal, detailColor = C.gray,
  }) => {
    addShape(slide, {
      x, y, w, h, geometry: "roundRect",
      fill, lineFill: border, lineWidth: 2,
    });
    addText(slide, eyebrow, {
      x: x + 14, y: y + 13, w: w - 28, h: 18,
      size: 10, color: eyebrowColor, bold: true, align: "center",
    });
    addText(slide, title, {
      x: x + 12, y: y + 36, w: w - 24, h: detail ? 28 : 38,
      size: 18, color: titleColor, bold: true, align: "center",
      valign: "middle",
    });
    if (detail) {
      addText(slide, detail, {
        x: x + 12, y: y + 68, w: w - 24, h: 27,
        size: 12, color: detailColor, align: "center", valign: "middle",
      });
    }
  };

  // Main request and release path. Arrows are added before nodes.
  addRightArrow(slide, 210, 267, 32, 18);
  addRightArrow(slide, 442, 267, 32, 18);
  addRightArrow(slide, 734, 267, 32, 18);
  addRightArrow(slide, 1038, 267, 32, 18);
  node({
    x: 64, y: 224, w: 142, h: 104,
    eyebrow: "USER", title: "Browser", detail: "Public review UI",
    fill: C.ice,
  });
  node({
    x: 248, y: 224, w: 190, h: 104,
    eyebrow: "AWS APP RUNNER", title: "FastAPI", detail: "Container service",
    fill: C.mint,
  });
  node({
    x: 480, y: 224, w: 250, h: 104,
    eyebrow: "APPLICATION", title: "Bounded orchestrator",
    detail: "Call limits and one revision",
    fill: C.navy, border: C.navy, titleColor: C.white,
    eyebrowColor: C.aqua, detailColor: C.aqua,
  });
  node({
    x: 772, y: 224, w: 262, h: 104,
    eyebrow: "DETERMINISTIC", title: "Release gates",
    detail: "Citation · numeric · language",
    fill: C.white, border: C.coral, eyebrowColor: C.coral,
  });
  node({
    x: 1076, y: 224, w: 140, h: 104,
    eyebrow: "OUTPUT", title: "Report", detail: "Human review",
    fill: C.sand, border: C.coral, eyebrowColor: C.coral,
  });

  // Orchestrator dependencies.
  addLine(slide, 605, 328, 0, 43, C.aqua, 3);
  addLine(slide, 438, 370, 462, 0, C.aqua, 3);
  addLine(slide, 438, 370, 0, 26, C.aqua, 3);
  addLine(slide, 900, 370, 0, 26, C.aqua, 3);
  addDownArrow(slide, 429, 389, 18, 22);
  addDownArrow(slide, 891, 389, 18, 22);
  addText(slide, "READS", {
    x: 458, y: 345, w: 84, h: 18, size: 10, color: C.teal,
    bold: true, align: "center",
  });
  addText(slide, "INVOKES", {
    x: 798, y: 345, w: 100, h: 18, size: 10, color: C.teal,
    bold: true, align: "center",
  });

  node({
    x: 312, y: 407, w: 252, h: 112,
    eyebrow: "PUBLIC DATA", title: "ClinicalTrials.gov",
    detail: "Allowlisted fields · bounded cohort",
    fill: C.ice,
  });

  addShape(slide, {
    x: 604, y: 402, w: 612, h: 122, geometry: "roundRect",
    fill: C.ice, lineFill: C.teal, lineWidth: 2,
  });
  addText(slide, "AMAZON BEDROCK  ·  US-EAST-1", {
    x: 624, y: 416, w: 572, h: 19, size: 11, color: C.teal,
    bold: true, align: "center",
  });
  const roles = [
    [624, 456, 172, "EVIDENCE", "Grounded facts"],
    [812, 456, 184, "COORDINATOR", "Review questions"],
    [1012, 456, 184, "CHALLENGE", "Adversarial review"],
  ];
  roles.forEach(([x, y, w, title, detail]) => {
    addShape(slide, {
      x, y, w, h: 52, geometry: "roundRect",
      fill: C.white, lineFill: C.fog, lineWidth: 1,
    });
    addText(slide, title, {
      x: x + 8, y: y + 8, w: w - 16, h: 16,
      size: 10, color: C.navy, bold: true, align: "center",
    });
    addText(slide, detail, {
      x: x + 8, y: y + 28, w: w - 16, h: 16,
      size: 11, color: C.gray, align: "center",
    });
  });

  addShape(slide, {
    x: 64, y: 557, w: 548, h: 84, geometry: "roundRect",
    fill: C.mint, lineFill: "none",
  });
  addText(slide, "IAM WORKLOAD ROLE", {
    x: 86, y: 573, w: 190, h: 18, size: 11, color: C.teal, bold: true,
  });
  addText(slide, "No embedded credentials", {
    x: 86, y: 598, w: 490, h: 26, size: 20, color: C.navy, bold: true,
  });
  addShape(slide, {
    x: 628, y: 557, w: 588, h: 84, geometry: "roundRect",
    fill: C.pale, lineFill: "none",
  });
  addText(slide, "CLOUDWATCH METADATA-ONLY LOGS", {
    x: 650, y: 573, w: 300, h: 18, size: 11, color: C.teal, bold: true,
  });
  addText(slide, "Run ID, latency, token counts, and gate status only", {
    x: 650, y: 598, w: 540, h: 26, size: 18, color: C.navy, bold: true,
  });
  addFooter(slide, 4);
  setNotes(
    slide,
    "Source: implemented TrialGuard runtime and deployment package, 2026-09-26. This is the intended AWS production design. The current workshop role cannot provision App Runner. The diagram uses editable native PowerPoint shapes."
  );
}

// Slide 5: verified evaluation metrics
{
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addSlideTitle(
    slide,
    5,
    "Evaluation results",
    "Repeatable checks and one live smoke test show the current implementation boundary"
  );

  addText(slide, "AUTOMATED VALIDATION", {
    x: 66, y: 222, w: 390, h: 24, size: 14, color: C.teal, bold: true,
  });
  addText(slide, "52/52", {
    x: 64, y: 258, w: 300, h: 72, size: 62, color: C.navy, bold: true,
  });
  addText(slide, "tests pass", {
    x: 66, y: 327, w: 360, h: 30, size: 22, color: C.gray,
  });
  addLine(slide, 64, 378, 420, 0, C.fog, 1);
  addText(slide, "7/7", {
    x: 64, y: 402, w: 220, h: 72, size: 62, color: C.navy, bold: true,
  });
  addText(slide, "synthetic offline evaluation behaviors matched", {
    x: 66, y: 472, w: 390, h: 56, size: 22, color: C.gray,
  });
  addText(
    slide,
    "Cases cover invalid IDs, sparse evidence, prompt injection, fabricated citations, and numeric mismatches.",
    {
      x: 66, y: 552, w: 405, h: 70, size: 16, color: C.gray,
    }
  );

  addLine(slide, 526, 216, 0, 420, C.fog, 1);
  addText(slide, "LIVE SMOKE TEST  ·  ONE SAMPLE", {
    x: 576, y: 222, w: 590, h: 24, size: 14, color: C.coral, bold: true,
  });
  addText(slide, "NCT06860815", {
    x: 576, y: 260, w: 580, h: 30, size: 19, color: C.teal, bold: true,
  });
  addText(slide, "Full release", {
    x: 576, y: 300, w: 330, h: 48, size: 38, color: C.navy, bold: true,
  });
  addText(slide, "14/14 checks passed", {
    x: 888, y: 311, w: 297, h: 30, size: 19, color: C.teal, bold: true,
    align: "right",
  });
  addLine(slide, 576, 365, 610, 0, C.fog, 1);

  const liveMetrics = [
    [576, "3", "BEDROCK CALLS"],
    [730, "10,821", "INPUT TOKENS"],
    [902, "1,758", "OUTPUT TOKENS"],
    [1064, "11.77 s", "ELAPSED"],
  ];
  liveMetrics.forEach(([x, value, label], i) => {
    addText(slide, value, {
      x, y: 393, w: i === 0 ? 120 : 150, h: 38,
      size: 27, color: C.navy, bold: true,
      align: i === 3 ? "right" : "left",
    });
    addText(slide, label, {
      x, y: 436, w: i === 0 ? 120 : 150, h: 20,
      size: 10, color: C.gray, bold: true,
      align: i === 3 ? "right" : "left",
    });
    if (i < liveMetrics.length - 1) {
      const separatorX = [702, 874, 1040][i];
      addLine(slide, separatorX, 391, 0, 62, C.fog, 1);
    }
  });
  addShape(slide, {
    x: 576, y: 480, w: 610, h: 84, geometry: "roundRect",
    fill: C.mint, lineFill: "none",
  });
  addText(slide, "$0.001071", {
    x: 598, y: 494, w: 255, h: 44, size: 37, color: C.navy, bold: true,
  });
  addText(slide, "estimated Bedrock model cost", {
    x: 860, y: 506, w: 300, h: 28, size: 18, color: C.teal, bold: true,
    align: "right",
  });
  addText(slide, "Nova Lite Standard: $0.06/M input and $0.24/M output", {
    x: 598, y: 539, w: 562, h: 18, size: 11, color: C.gray,
    align: "right",
  });
  addText(slide, "Rates verified 2026-09-26. One live sample, not a benchmark.", {
    x: 576, y: 584, w: 610, h: 30, size: 15, color: C.coral,
    bold: true, align: "center",
  });
  addFooter(slide, 5);
  setNotes(
    slide,
    "Verified values supplied from the stable TrialGuard build on 2026-09-26: 52/52 tests pass; 7/7 synthetic offline behaviors matched; one NCT06860815 live smoke test produced a full release, 14/14 checks, 3 calls, 10,821 input tokens, 1,758 output tokens, and 11.77 seconds elapsed. Estimated cost uses Amazon Nova Lite Standard rates of $0.06 per million input tokens and $0.24 per million output tokens, verified 2026-09-26. One live sample is not a benchmark."
  );
}

// Slide 6: limits and next steps
{
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addShape(slide, { x: 768, y: 0, w: 512, h: 720, fill: C.navy });
  addText(slide, "06", {
    x: 64, y: 49, w: 54, h: 33, size: 17, color: C.teal, bold: true,
  });
  addText(slide, "Limits and next steps", {
    x: 64, y: 79, w: 650, h: 58, size: 46, color: C.navy, bold: true,
  });
  addText(slide, "CURRENT BOUNDARY", {
    x: 66, y: 198, w: 280, h: 28, size: 14, color: C.teal, bold: true,
  });

  const limits = [
    ["Public data", "Selected, allowlisted ClinicalTrials.gov fields only"],
    ["Sensitive data", "No PHI or confidential protocol uploads"],
    ["Decision support", "No prediction, design recommendation, or clinical advice"],
    ["Accountability", "A qualified reviewer makes the final decision"],
  ];
  limits.forEach((item, i) => {
    const y = 252 + i * 82;
    addText(slide, item[0], {
      x: 66, y, w: 180, h: 30, size: 19, color: C.navy, bold: true,
    });
    addText(slide, item[1], {
      x: 250, y, w: 430, h: 52, size: 20, color: C.gray,
    });
    if (i < limits.length - 1) {
      addLine(slide, 66, y + 60, 620, 0, C.fog, 1);
    }
  });

  addText(slide, "DEPLOYMENT STATUS", {
    x: 820, y: 87, w: 350, h: 28, size: 14, color: C.aqua, bold: true,
  });
  const deployment = [
    ["PUBLIC SHOWCASE", "Static GitHub Pages"],
    ["PRODUCTION TARGET", "FastAPI on AWS App Runner with Bedrock in us-east-1"],
    ["CURRENT CONSTRAINT", "The workshop IAM role blocks App Runner provisioning"],
    ["PACKAGE STATUS", "Ready for deployment from an authorized AWS account"],
  ];
  deployment.forEach((item, i) => {
    const y = 150 + i * 120;
    addText(slide, item[0], {
      x: 820, y, w: 340, h: 22, size: 12, color: C.aqua, bold: true,
    });
    addText(slide, item[1], {
      x: 820, y: y + 31, w: 365, h: 62, size: 21, color: C.white,
      bold: true,
    });
    if (i < deployment.length - 1) {
      addLine(slide, 820, y + 103, 360, 0, C.tealDark, 1);
    }
  });
  addText(
    slide,
    "Hackathon decision-support demonstration. Not clinical, regulatory, legal, or medical advice.",
    {
      x: 66, y: 616, w: 650, h: 46, size: 17, color: C.coral, bold: true,
    }
  );
  addFooter(slide, 6, true);
  setNotes(
    slide,
    "Source: TrialGuard Development Plan, sections 1, 3, 9, 17, and 18, plus deployment status verified 2026-09-26. The current public showcase uses static GitHub Pages because the workshop IAM role blocks App Runner provisioning. The App Runner package is ready for an authorized AWS account. Keep the intended-use boundary in the final deck."
  );
}

await fs.mkdir(TMP_DIR, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });

const previewDir = path.join(TMP_DIR, "authoring-preview");
await fs.mkdir(previewDir, { recursive: true });
for (let i = 0; i < presentation.slides.items.length; i += 1) {
  const slide = presentation.slides.items[i];
  const preview = await presentation.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(
    path.join(previewDir, `slide-${String(i + 1).padStart(2, "0")}.png`),
    new Uint8Array(await preview.arrayBuffer())
  );
}

const stagingDir = path.join(workspaceDir, "slides/.codex-finalizer");
await fs.mkdir(stagingDir, { recursive: true });
const candidatePath = path.join(stagingDir, "trialguard-template-candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);

const requirements = {
  explicitTotalSlideCount: 6,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  requiredEmbeddedWorkbookChartOwnerSlides: [],
};
const fontPolicy = {
  basis: "design",
  families: [FONT],
};
const expectedSlideSizeEmu = "12192000,6858000";

const result = await finalizePresentation({
  ...requirements,
  workspaceDir,
  candidatePath,
  finalPath: FINAL_PPTX,
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(
    SKILL_DIR,
    "container_tools/inspect_presentation_package_integrity.py"
  ),
  layoutValidatorPath: path.join(
    SKILL_DIR,
    "container_tools/inspect_presentation_layout_geometry.py"
  ),
  layoutArgs: [
    "--expected-slide-size-emu",
    expectedSlideSizeEmu,
    "--validate-bullet-geometry",
    "--validate-heading-fit",
  ],
  requiredNativeTableOwnerSlides: [],
  fontPolicy,
  verifyArtifactToolImport: true,
  receiptPath: path.join(
    stagingDir,
    `${path.basename(path.dirname(FINAL_PPTX))}-${path.basename(FINAL_PPTX)}.validation.json`
  ),
});

console.log(JSON.stringify(result, null, 2));
