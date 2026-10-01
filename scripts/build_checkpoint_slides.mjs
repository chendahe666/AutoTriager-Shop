/** Build the eight-slide, evidence-backed October 1 coursework checkpoint.
 * Requires the supplied @oai/artifact-tool runtime and presentation skill.
 * This authoring utility never reads API credentials or evaluator labels.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SKILL = process.env.PRESENTATION_SKILL_DIR;
const NODE_MODULES = process.env.RUNTIME_NODE_MODULES;
const PYTHON = process.env.RUNTIME_PYTHON;
if (![SKILL, NODE_MODULES, PYTHON].every(v => v && path.isAbsolute(v))) {
  throw new Error('Set PRESENTATION_SKILL_DIR, RUNTIME_NODE_MODULES, RUNTIME_PYTHON to the supplied runtime paths.');
}
const require = createRequire(path.join(NODE_MODULES, 'presentation-builder.cjs'));
const {Presentation, PresentationFile} = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const {resolvePresentationFont, makeNativeBulletParagraphs, finalizePresentation} = await import(
  pathToFileURL(path.join(SKILL, 'container_tools/artifact_tool_utils.mjs')).href);
const family = resolvePresentationFont({fontFamily:'Arial'});
const BUILD = path.join(ROOT,'evaluation','private','checkpoint-slides-final-20261001');
const OUTPUT = path.join(ROOT,'output','slides','AutoTriager_OfficialShop_Checkpoint_Dahe_Chen_Final.pptx');
await fs.mkdir(BUILD,{recursive:true});
await fs.mkdir(path.dirname(OUTPUT),{recursive:true});
const p = Presentation.create({slideSize:{width:1280,height:720}});

function text(s, value, x, y, w, h, size=30, bold=false) {
  const shape=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  shape.text=value;
  shape.text.style={typeface:family,fontSize:size,color:'#111111',bold,autoFit:'none'};
  return shape;
}
function bullets(s, items, x=68,y=160,w=1144,h=410,size=30) {
  const shape=text(s,'',x,y,w,h,size);
  shape.text=makeNativeBulletParagraphs(items,{marginLeftPoints:18,hangingPoints:9,spaceAfterPoints:16});
  shape.text.style={typeface:family,fontSize:size,color:'#111111',autoFit:'none'};
}
function slide(title, note) {
  const s=p.slides.add(); s.background.fill='#FFFFFF';
  text(s,title,64,44,1152,100,43,true);
  text(s,'Dahe Chen  /  CS 5588  /  October 1, 2026 checkpoint',64,672,1020,28,16);
  text(s,String(p.slides.items.length),1190,672,38,28,16);
  s.speakerNotes.textFrame.setText(note);
  return s;
}
function table(s, values, widths, x=64,y=160,w=1152,h=310,size=27) {
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
  t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({fill:'#FFFFFF',textStyle:{typeface:family,fontSize:size,color:'#111111'},margins:{left:12,right:12,top:10,bottom:10}});
  t.cells.block({row:0,column:0,rowCount:1,columnCount:values[0].length}).assign({fill:'#EEEEEE',textStyle:{typeface:family,fontSize:size,bold:true,color:'#111111'}});
  t.borders.assign({style:'solid',fill:'#888888',width:0.7});
  return t;
}
async function screenshot(s,name,x,y,w,h) {
  // Monochrome document rendering only. Preserve the original captured file.
  const original=path.join(ROOT,'results','screenshots',name);
  const gray=path.join(BUILD,`${name}.grayscale.png`);
  const render=spawnSync(PYTHON,['-c',
    'from PIL import Image, ImageOps; import sys; ImageOps.grayscale(Image.open(sys.argv[1])).save(sys.argv[2])',original,gray],{encoding:'utf8'});
  if (render.status!==0) throw new Error(`Monochrome document rendering failed: ${render.stderr}`);
  const bytes=await fs.readFile(gray);
  s.images.add({blob:new Uint8Array(bytes),contentType:'image/png',alt:`Monochrome rendering of unchanged actual screenshot: ${name}`,fit:'contain',position:{left:x,top:y,width:w,height:h}});
}

let s=slide('AutoTriager Shop',
  'Current checkpoint, not a backdated September submission. Sources: docs/OFFICIAL_SHOP_WORKSHOP_DRAFT.md sections1,2; original Enhancement handout. Present the bounded feature and preserved failures without a novelty or user-benefit claim.');
text(s,'Evidence-grounded incident investigation',68,162,1100,70,40);
text(s,'Dahe Chen',68,248,900,64,36,true);
bullets(s,[
  'User: an on-call developer new to the shopping system',
  'P1: load a captured checkout incident and inspect a checkable service suggestion',
  'Question: can bounded evidence support an inspection priority while allowing deferral?'
],68,340,1120,265,29);

s=slide('Instructor feedback and design changes',
  'Feedback paraphrases the user-provided teacher discussion, not a verbatim instructor quotation. Evidence: pinned official source, runtime receipts, nine examples, frozen comparison results, claim audit. The user requested the scenario reset despite the Enhancement default to improve existing work.');
table(s,[['Feedback','Change','Evidence'],
 ['Who needs this?','Focus on a developer new to this system','Concrete checkout investigation'],
 ['Use a real scenario','Run official Astronomy Shop locally','25 containers and captured telemetry'],
 ['Evaluate the AI','Keep controls, direct reference and failures','30 calls, 28 responses, 2 errors'],
 ['Make findings checkable','Retain IDs, values and trace relationships','Saved inputs and source inspection']
],[280,435,437],64,154,1152,388,25);
text(s,'The current study measures label agreement and evidence limits. User benefit remains unmeasured.',68,580,1120,64,25);

s=slide('Working investigation feature',
  'Actual recorded official fault view: results/screenshots/official_case_app_20261001.jpg. The model returned payment on development002-b. This is saved response replay and does not make a new API call. App.py and ui.py implement scope/source/review. No real human rating is supplied. Local URL is not remotely accessible.');
await screenshot(s,'official_case_app_20261001.jpg',64,148,715,402);
bullets(s,['Select a captured interval','Inspect the suggested service and cited observations','Accept, reject or defer with a reason'],822,172,390,370,27);
text(s,'Local demo: http://127.0.0.1:8510',68,584,1100,38,26);
text(s,'Offline replay requires no API key. Live Gemini analysis requires explicit data-sharing consent.',68,625,1100,36,20);

s=slide('Research context and reused ideas',
  'Primary sources checked in research/closest_work.md: OpenRCA ICLR2025 Section2.3, https://github.com/microsoft/OpenRCA and https://proceedings.iclr.cc/paper_files/paper/2025/file/d29b8d53678015079e1d245c023e49d2-Paper-Conference.pdf; EviRCA preprint https://arxiv.org/html/2609.19825v1 III-B/C,V-B, code https://github.com/yuhao541/EviRCA; MicroRCA-Agent competition report https://arxiv.org/html/2509.15635v1 3.5,4.1, code https://github.com/tangpan360/MicroRCA-Agent. No local closest-method reproduction or cross-paper score comparison. Dataset/source: https://github.com/open-telemetry/opentelemetry-demo/tree/dedc0178918e260823323b8d95005a8cb924b007 Apache2.0.');
bullets(s,[
  'OpenRCA: public telemetry benchmark and RCA-Agent. Learn structured fault queries and evaluation boundaries.',
  'EviRCA: deterministic extraction before read-only reasoning. Evidence cards are an existing method.',
  'MicroRCA-Agent: structured diagnosis with documented invented call-chain evidence. Audit claim support separately.',
  'Own study data: official Shop 3.1.0 captures. Benchmark scores do not validate this live scenario.'
],68,156,1144,405,29);
text(s,'github.com/microsoft/OpenRCA    github.com/yuhao541/EviRCA',68,583,1140,34,20);
text(s,'github.com/tangpan360/MicroRCA-Agent    github.com/open-telemetry/opentelemetry-demo',68,622,1140,35,20);

s=slide('Methods and evaluation',
  'Sources: research/program.md, experiment_plan.json,A1/A2/A3 amendments,selected_method.json, results/official_research_round_20261001.json. Both conditions see same records/order within condition but direct asks initiating service whereas amended grounded asks inspection priority. Thus descriptive comparison only. Frozen run has48 cap, metric/span balancing, structural citations validator, no independent logs.');
bullets(s,[
  'Data: 9 phase windows, 8,379 observations, one injected payment-failure mechanism',
  'Processing: preserve numerical values, IDs, UTC times and observed parent links',
  'Model: Gemini 3.5 Flash-Lite, 48-record cap, temperature 0, no retries',
  'References: direct prompt and transparent rule ranking',
  'Measures: injected-service agreement, control deferral, claim support, tokens and latency'
],68,150,1144,397,28);
text(s,'Direct asks for an initiating service. The amended method asks for an inspection priority.',68,579,1120,64,25,true);
text(s,'These questions prevent a same-task superiority claim.',68,632,1120,32,23);

s=slide('Frozen confirmation results',
  'Sources: public aggregate results and scored confirmation003/005.2faultwindows and4controls in2dependentgroups. Raw/application same candidate outcomes. Directpayment2/2,groundedpayment1/2 checkout1/2. Rule reference uses fullpool and abstainsallconfirmation6 windows, input budget unmatched.30calls28completed2dev503.205778known total tokens for28 responses, two failures usageunknown. No significance/speed/SOTA claims.');
table(s,[['Measure','Direct reference','Evidence-grounded'],
  ['Fault label agreement','2 / 2','1 / 2'],
  ['Control deferral','4 / 4','4 / 4'],
  ['Other fault suggestion','None','Checkout in group 003']
],[445,347,360],64,156,1152,258,28);
bullets(s,[
  '30 total calls: 28 completed and 2 development HTTP 503 failures',
  'Capture yield: 10 accepted of 13 attempted phases',
  'No evidence of superiority, optimal first action or cross-fault generalization'
],68,460,1120,179,27);

s=slide('Testing and a retained failure',
  'Real confirmation003-b screenshot results/screenshots/official_confirmation_counterexample_20261001.jpg. Candidatecheckout is a label nonmatch, not proof of a bad first inspection action. paymentERRORselectedspan7/8 were available but uncited. Grounded003-a reason sayszeroerroracrossservices despite selectedloadgenmetric19 positiveandERRORspan; actualclaim audit preserves this counterexample. Ninebundles are phasewindows onone mechanism, not9independentfaultcategories.');
await screenshot(s,'official_confirmation_counterexample_20261001.jpg',64,148,710,399);
bullets(s,[
  '9 recorded windows cover normal, injected fault and recovery',
  'Group 003 suggests checkout although the intervention targets payment',
  'A normal-window explanation overlooks selected load-generator errors'
],820,158,392,398,27);
text(s,'Valid evidence IDs do not guarantee a faithful explanation. Preserve the negative case.',68,591,1120,64,26,true);

s=slide('Delivery and next experiment',
  'Sources: README, docs/PROJECT_PLAN, actual report and ninepublic examples. Course/currentimplemented bounded cycle complete except originalpre-AIworkflow unavailable, meaningfulactualhumanreview notyetrecorded. Newcomponent comparison is post-studyengineering, no additional modelclaims. C3 competing hypotheses and action-quality criteria; C4 missing/delayed signals; C5 integration. Do not advance merely by techadditions.');
bullets(s,[
  'Available: local app, official captures, replay examples, evaluation code and English report',
  'Remaining: observed human review and a matched investigation-task comparison',
  'Challenge 3: compare competing service explanations with checkable evidence',
  'Challenge 4: evaluate predefined missing or delayed telemetry',
  'Challenge 5: integrate verified features and prepare the live demonstration'
],68,150,1144,379,28);
text(s,'Application: http://127.0.0.1:8510  (local demonstration)',68,573,1144,38,25);
text(s,'Repository: https://github.com/chendahe666/AutoTriager-Shop',68,622,1144,38,24);

const candidatePath=path.join(BUILD,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidatePath);
const result=await finalizePresentation({workspaceDir:ROOT,candidatePath,finalPath:OUTPUT,
  explicitTotalSlideCount:8,requiredNativeTableOwnerSlides:[2,6],
  pythonExecutable:PYTHON,
  integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',
    '--require-native-table-slide','2','--require-native-table-slide','6'],
  fontPolicy:{basis:'design',families:[family]},verifyArtifactToolImport:true,
  receiptPath:path.join(BUILD,'validation.json')});
for (let i=0;i<p.slides.items.length;i++) {
  const image=await p.export({slide:p.slides.items[i],format:'png',scale:1});
  await fs.writeFile(path.join(BUILD,`slide-${i+1}.png`),new Uint8Array(await image.arrayBuffer()));
}
console.log(JSON.stringify({output:OUTPUT,slides:p.slides.items.length,validation:result}));
