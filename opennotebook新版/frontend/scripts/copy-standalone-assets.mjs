// next build 的 standalone 产物不带静态文件，按 Next 文档把 public 和 .next/static 拷进去，
// 这样 `npm start`（node start-server.js）就能直接跑。原版是在 Dockerfile 里做这一步。
import { cpSync, existsSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const standalone = path.join(root, '.next', 'standalone')

if (!existsSync(standalone)) {
  console.error('[copy-standalone-assets] 没找到 .next/standalone，先跑 next build')
  process.exit(1)
}

for (const [from, to] of [
  [path.join(root, 'public'), path.join(standalone, 'public')],
  [path.join(root, '.next', 'static'), path.join(standalone, '.next', 'static')],
]) {
  rmSync(to, { recursive: true, force: true })
  cpSync(from, to, { recursive: true })
}
console.log('[copy-standalone-assets] 已把 public 和 .next/static 拷进 .next/standalone')
