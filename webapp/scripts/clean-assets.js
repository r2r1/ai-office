// Чистит static/webapp/assets/ перед сборкой — vite.config.ts's emptyOutDir:true
// на этой машине не срабатывает (outDir вне корня проекта, Vite либо тихо
// пропускает очистку, либо fs.rmSync(dir, {recursive:true}) не удаляет файлы
// на этой Windows-конфигурации — воспроизведено: rmSync молча ничего не
// делает, поштучный unlinkSync через readdir работает). Без этого шага
// каждая сборка добавляла новый хешированный бандл, а старые копились в
// репозитории вместо перезаписи (найдено при аудите 2026-07-06).
import { existsSync, readdirSync, unlinkSync } from "node:fs"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { dirname } from "node:path"

const __dirname = dirname(fileURLToPath(import.meta.url))
const assetsDir = join(__dirname, "..", "..", "static", "webapp", "assets")

if (existsSync(assetsDir)) {
  for (const f of readdirSync(assetsDir)) {
    unlinkSync(join(assetsDir, f))
  }
  console.log(`clean-assets: очищено ${assetsDir}`)
} else {
  console.log("clean-assets: директория ещё не существует, пропускаю")
}
