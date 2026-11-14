# OpenNotebook 配色

`space.css` 是 OpenNotebook 工作区使用的 TAgent 配色。可将它追加到 OpenNotebook 前端的全局 CSS 后重新构建。对于已经构建的独立 Next.js 前端，在启动前也可以对实际提供页面的构建运行：

```sh
python3 opennotebook/theme/apply-space-theme.py 'opennotebook新版/frontend/.next/standalone/.next'
```

脚本会更新样式文件名和构建引用，让浏览器重新获取主题。重新构建后需要再次应用。官方 Docker 镜像仍自带原主题，部署时需要使用包含此样式的前端构建。
