import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import { createRenderer, h, ref, nextTick } from 'vue'
const dataModule = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const transpile = source => ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const helper = dataModule(transpile(readFileSync(new URL('../src/v2/features/generate/workflowParameters.ts',import.meta.url),'utf8')))
const {descriptor}=parse(readFileSync(new URL('../src/v2/features/generate/WorkflowParameterFields.vue',import.meta.url),'utf8'))
let source=transpile(compileScript(descriptor,{id:'workflow-regression',inlineTemplate:true}).content)
source=source.replaceAll('from "vue"',`from ${JSON.stringify(import.meta.resolve('vue'))}`).replaceAll("from 'vue'",`from ${JSON.stringify(import.meta.resolve('vue'))}`)
source=source.replace(/import .* from ['"](?:.*MediaParameterField.vue|.*V2Field.vue|.*V2Button.vue)['"];?/g,'')
source=source.replace(/from ['"].\/workflowParameters['"]/g,`from ${JSON.stringify(helper)}`)
source=`const media=[];
const MediaParameterField={props:['modelValue','maskResourceId','multiple','mediaType'],emits:['update:modelValue','update:maskResourceId'],setup(props,{emit}){media.push({props,emit});return()=>null}};
const V2Field={inheritAttrs:false,setup(p,{slots}){return()=>slots.default?.()}};
const V2Button={setup(){return()=>null}};
export {media};
`+source
const {default:Fields,media}=await import(dataModule(source))
const node=()=>({children:[]})
const renderer=createRenderer({createElement:node,createText:node,createComment:node,setText(){},setElementText(){},patchProp(){},parentNode:n=>n.parent,nextSibling:n=>n.parent?.children[n.parent.children.indexOf(n)+1]||null,insert(n,p){n.parent=p;p.children.push(n)},remove(n){if(n?.parent)n.parent.children=n.parent.children.filter(v=>v!==n)}})
for(const multiple of [false,true])test(`selected ${multiple?'multiple':'single'} images survive same-tick mask reset and clear`,async()=>{
  media.length=0
  const model=ref({reference:multiple?[1]:1,reference__mask:55,prompt:'keep'})
  const app=renderer.createApp({setup(){return()=>h(Fields,{parameters:[{key:'reference',type:'image',label:'reference',multiple}],settings:{},modelValue:model.value,'onUpdate:modelValue':v=>model.value=v})}})
  app.mount(node())
  try{
    media[0].emit('update:modelValue',multiple?[7,8]:7)
    media[0].emit('update:maskResourceId',null)
    await nextTick()
    assert.deepEqual(model.value,{reference:multiple?[7,8]:7,reference__mask:null,prompt:'keep'})
    assert.deepEqual(media[0].props.modelValue,multiple?[7,8]:7)
    model.value={reference:multiple?[9]:9,reference__mask:66,prompt:'switched workflow'}
    await nextTick()
    media[0].emit('update:maskResourceId',77)
    await nextTick()
    assert.equal(model.value.prompt,'switched workflow')
    assert.deepEqual(model.value.reference,multiple?[9]:9)
    media[0].emit('update:modelValue',multiple?[]:null)
    media[0].emit('update:maskResourceId',null)
    await nextTick()
    assert.deepEqual(model.value,{reference:multiple?[]:null,reference__mask:null,prompt:'switched workflow'})
  }finally{app.unmount()}
})
