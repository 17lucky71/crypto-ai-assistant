// Vercel 빌드 스크립트: 정적 파일을 dist/ 로 복사하고,
// 환경 변수 API_BASE_URL 값으로 dist/config.js 를 만든다.
const fs = require("fs");
const path = require("path");

const apiBase = process.env.API_BASE_URL;
if (!apiBase) {
  console.error("API_BASE_URL 환경 변수가 없습니다. Vercel 설정에서 추가하세요.");
  process.exit(1);
}

const out = path.join(__dirname, "dist");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out);
for (const f of ["index.html", "style.css", "app.js"]) {
  fs.copyFileSync(path.join(__dirname, f), path.join(out, f));
}
fs.writeFileSync(path.join(out, "config.js"), `window.API_BASE_URL = ${JSON.stringify(apiBase.replace(/\/$/, ""))};\n`);
console.log("빌드 완료: API_BASE_URL =", apiBase);
