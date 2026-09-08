import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { reactive } from 'vue'
const source = readFileSync(new URL('../src/v2/features/generate/workflowParameters.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { workflowDefaults, workflowPayload, workflowValidation, migrateWorkflowParams, parameterVisible, promptParameter, parameterOptions } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const field = (key, type, rest = {}) => ({ key, type, label: key, ...rest })
test('reactive workflow defaults clone arrays and use maintained sizes/options', () => {
  const workflow = reactive({ parameters: [field('refs','image',{multiple:true,default:[1,2]}),field('width','int'),field('height','int'),field('mode','select',{options_from:'modes'}),field('flag','bool')] })
  const defaults = workflowDefaults(workflow, {image_size:{default_value:'1024x768'},modes:{default_value:2}})
  assert.deepEqual(defaults,{refs:[1,2],width:1024,height:768,__size:'1024x768',mode:2,flag:false})
  defaults.refs.push(3); assert.deepEqual(workflow.parameters[0].default,[1,2])
})
test('required visible inputs reject blanks/empty multi-images, retain zero and false', () => {
  assert.match(workflowValidation([field('refs','image',{required:true})],{refs:[]}),/refs/)
  assert.match(workflowValidation([field('prompt','textarea',{required:true})],{prompt:'  '}),/prompt/)
  assert.equal(workflowValidation([field('seed','seed',{required:true}),field('flag','bool',{required:true})],{seed:0,flag:false}),'')
  assert.equal(workflowValidation([field('hidden','image',{required:true,visible_when:{key:'flag',operator:'truthy'}})],{flag:false}),'')
})
test('submission contains only selected workflow visible fields and source masks', () => {
  const schema=[field('prompt','textarea'),field('input','image'),field('seed','seed'),field('enabled','bool'),field('hidden','text',{visible_when:{key:'enabled',operator:'truthy'}})]
  assert.deepEqual(workflowPayload(schema,{prompt:'portrait',input:9,input__mask:10,seed:0,enabled:false,hidden:'omit',old_image:7,__scheme:'a'}),{prompt:'portrait',input:9,input__mask:10,seed:0,enabled:false})
  assert.deepEqual(workflowPayload([field('input','image')],{input:null,input__mask:10}),{})
})
test('switch preserves matching media before aliases, does not duplicate or coerce plurality', () => {
  const previous=[field('a','image'),field('b','image'),field('refs','image',{multiple:true})]
  const next=[field('renamed','image'),field('a','image'),field('single','image')]
  assert.deepEqual(migrateWorkflowParams(previous,next,{a:1,b:2,b__mask:3,refs:[4]}),{renamed:2,renamed__mask:3,a:1})
})
test('conditional reference count and typed select options match generation UI', () => {
  const p=field('reference_image_2','image')
  assert.equal(parameterVisible(p,{multi_reference_enabled:true,multi_reference_count:1}),false)
  assert.equal(parameterVisible(p,{multi_reference_enabled:true,multi_reference_count:2}),true)
  assert.deepEqual(parameterOptions(field('count','select',{options_from:'counts'}),{counts:{options:[{label:'two',value:2}]}}),[{label:'two',value:2}])
})
test('positive prompt excludes negative prompt, and image limits are enforced', () => {
  assert.equal(promptParameter([field('negative_prompt','textarea'),field('positive_prompt','textarea')]).key,'positive_prompt')
  assert.match(workflowValidation([field('refs','image',{multiple:true,max_items:2})],{refs:[1,2,3]}),/2/)
})
