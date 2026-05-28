const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  AlignmentType,
  BorderStyle,
  WidthType,
  ShadingType,
  VerticalAlign,
  HeadingLevel,
  ImageRun,
} = require("docx");
const fs = require("fs");

const payload = JSON.parse(fs.readFileSync("__ARCH_INPUT_JSON__", "utf-8"));
const outputPath = "__ARCH_OUTPUT_DOCX__";

const PAGE_W = 11906;
const MARGIN = 720;
const TABLE_W = PAGE_W - MARGIN * 2;
const GRAY = "D9D9D9";
const BLUE = "D9EAF7";
const WHITE = "FFFFFF";

const border = { style: BorderStyle.SINGLE, size: 1, color: "999999" };
const borders = { top: border, bottom: border, left: border, right: border };

function text(value) {
  return String(value ?? "");
}

function run(value, opts = {}) {
  return new TextRun({
    text: text(value),
    bold: opts.bold || false,
    size: opts.size || 20,
    font: "Malgun Gothic",
    color: opts.color || "111111",
  });
}

function paragraph(value, opts = {}) {
  return new Paragraph({
    heading: opts.heading,
    spacing: { before: opts.before || 80, after: opts.after || 80 },
    bullet: opts.bullet ? { level: 0 } : undefined,
    children: [run(value, opts)],
  });
}

function cell(value, opts = {}) {
  return new TableCell({
    borders,
    width: opts.width ? { size: opts.width, type: WidthType.DXA } : undefined,
    shading: { fill: opts.shade ? (opts.blue ? BLUE : GRAY) : WHITE, type: ShadingType.CLEAR },
    verticalAlign: VerticalAlign.CENTER,
    columnSpan: opts.span || 1,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [
      new Paragraph({
        alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
        children: [run(value, { bold: opts.bold, size: opts.size || 18 })],
      }),
    ],
  });
}

function buildRevisionTable() {
  return new Table({
    width: { size: TABLE_W, type: WidthType.DXA },
    rows: [
      new TableRow({
        children: [
          cell("날짜", { shade: true, bold: true, center: true, width: 1500 }),
          cell("버전", { shade: true, bold: true, center: true, width: 1200 }),
          cell("작성자", { shade: true, bold: true, center: true, width: 1500 }),
          cell("승인자", { shade: true, bold: true, center: true, width: 1500 }),
          cell("내용", { shade: true, bold: true, center: true, width: TABLE_W - 5700 }),
        ],
      }),
      new TableRow({
        children: [
          cell("", { width: 1500 }),
          cell("v1.0", { width: 1200, center: true }),
          cell("", { width: 1500 }),
          cell("", { width: 1500 }),
          cell("초안 작성", { width: TABLE_W - 5700 }),
        ],
      }),
    ],
  });
}

function buildSummaryTable() {
  const infra = payload.user_infra_spec || {};
  const extracted = payload.extracted_infra || {};
  const rows = [
    ["Middleware Stack", infra.middleware_stack || extracted.selected_middleware?.join(", ") || ""],
    ["Firewall", infra.firewall_setting || ""],
    ["Security/Auth", infra.security_auth || ""],
    ["Expected CCU", infra.expected_ccu ?? ""],
    ["Cloud", infra.is_cloud === true ? "Cloud" : "On-Premise"],
    ["Server Spec", infra.server_hardware_spec || ""],
  ];

  return new Table({
    width: { size: TABLE_W, type: WidthType.DXA },
    rows: [
      new TableRow({
        children: [
          cell("구분", { shade: true, blue: true, bold: true, center: true, width: 2500 }),
          cell("내용", { shade: true, blue: true, bold: true, center: true, width: TABLE_W - 2500 }),
        ],
      }),
      ...rows.map(([label, value]) =>
        new TableRow({
          children: [
            cell(label, { shade: true, bold: true, width: 2500 }),
            cell(value, { width: TABLE_W - 2500 }),
          ],
        })
      ),
    ],
  });
}

function markdownishToParagraphs(content) {
  const children = [];
  for (const raw of text(content).split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) {
      children.push(new Paragraph({ text: "" }));
    } else if (line.startsWith("### ")) {
      children.push(paragraph(line.slice(4), { heading: HeadingLevel.HEADING_3, bold: true, size: 24 }));
    } else if (line.startsWith("## ")) {
      children.push(paragraph(line.slice(3), { heading: HeadingLevel.HEADING_2, bold: true, size: 26 }));
    } else if (line.startsWith("# ")) {
      children.push(paragraph(line.slice(2), { heading: HeadingLevel.HEADING_1, bold: true, size: 30 }));
    } else if (line.startsWith("- ")) {
      children.push(paragraph(line.slice(2), { bullet: true }));
    } else {
      children.push(paragraph(line));
    }
  }
  return children;
}

function buildImageParagraph(imagePath) {
  if (!imagePath || !fs.existsSync(imagePath)) {
    return paragraph("아키텍처 이미지가 생성되지 않았습니다.");
  }

  return new Paragraph({
    spacing: { before: 160, after: 160 },
    alignment: AlignmentType.CENTER,
    children: [
      new ImageRun({
        data: fs.readFileSync(imagePath),
        transformation: { width: 650, height: 360 },
      }),
    ],
  });
}

const children = [
  paragraph("아키텍처 설계서", { heading: HeadingLevel.TITLE, bold: true, size: 36 }),
  paragraph("제·개정 이력", { heading: HeadingLevel.HEADING_2, bold: true, size: 26 }),
  buildRevisionTable(),
  paragraph("인프라 구성 요약", { heading: HeadingLevel.HEADING_2, bold: true, size: 26, before: 240 }),
  buildSummaryTable(),
  paragraph("아키텍처 설계 내용", { heading: HeadingLevel.HEADING_2, bold: true, size: 26, before: 240 }),
  ...markdownishToParagraphs(payload.report_specs || ""),
  paragraph("시스템 아키텍처 다이어그램", { heading: HeadingLevel.HEADING_2, bold: true, size: 26, before: 240 }),
  buildImageParagraph(payload.image_path),
  paragraph("Mermaid 원본", { heading: HeadingLevel.HEADING_2, bold: true, size: 26, before: 240 }),
  paragraph(payload.mermaid_script || "", { size: 16 }),
];

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: "Malgun Gothic", size: 20 },
      },
    },
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: PAGE_W, height: 16838 },
          margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
        },
      },
      children,
    },
  ],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outputPath, buffer);
  console.log("완료");
});
