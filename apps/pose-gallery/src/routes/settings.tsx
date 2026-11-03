import {createFileRoute} from '@tanstack/react-router'
export const Route=createFileRoute('/settings')({component:()=> <section><h1>生成工作流配置</h1><p>由 Console 管理员配置图库参考槽与工作流参数。</p><a href="/v2/settings/gallery">打开 Console 工作流配置</a></section>})
