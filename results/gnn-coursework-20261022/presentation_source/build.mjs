import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
const HERE=path.dirname(fileURLToPath(import.meta.url));
for(const name of ['ARTIFACT_TOOL_MODULE','PRESENTATIONS_SKILL_DIR','RUNTIME_PYTHON','RUNTIME_NODE_MODULES']){if(!process.env[name])throw new Error('Set '+name+' from your installed presentation runtime.');}
const {Presentation, PresentationFile}=await import(pathToFileURL(process.env.ARTIFACT_TOOL_MODULE).href);
const REPO=path.resolve(HERE,'../../..');
const ROOT=path.dirname(REPO);
const BUILD=process.env.GNN_SLIDES_BUILD||path.join(ROOT,'tmp','gnn-slides-rebuild');
const RESULTS=REPO+'/results/gnn-coursework-20261022';
const SKILL=process.env.PRESENTATIONS_SKILL_DIR;
const PYTHON=process.env.RUNTIME_PYTHON;
const {makeNativeBulletParagraphs,finalizePresentation,resolvePresentationFont}=await import(pathToFileURL(SKILL+'/container_tools/artifact_tool_utils.mjs').href);
const FONT=resolvePresentationFont({fontFamily:'Arial'});
const p=Presentation.create({slideSize:{width:1280,height:720}});
p.theme.defaultFont=FONT;
p.theme.colorScheme={name:'Workshop Monochrome',themeColors:{accent1:'#111111',accent2:'#333333',accent3:'#555555',accent4:'#777777',accent5:'#999999',accent6:'#BBBBBB',bg1:'#FFFFFF',bg2:'#EEEEEE',tx1:'#111111',tx2:'#4B4B4B',dk1:'#000000',dk2:'#333333',lt1:'#FFFFFF',lt2:'#EEEEEE',hlink:'#4B4B4B',folHlink:'#4B4B4B'}};
const black='#111111',gray='#4B4B4B';
const WEB='https://github.com/chendahe666/AutoTriager-Shop/blob/main/';
const PAPER='https://papers.nips.cc/paper/6703-inductive-representation-learning-on-large-graphs';
const load=async path=>JSON.parse(await fs.readFile(path,'utf8'));

function text(s,name,value,x,y,w,h,size=28,bold=false,color=black){
 const q=s.shapes.add({name,geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 q.text=value;q.text.style={typeface:FONT,fontSize:size,bold,color,autoFit:'none',verticalAlignment:'top',insets:{left:0,right:0,top:0,bottom:0}};return q;
}
function code(s,value,x,y,w,h,size=24){const q=text(s,'code-excerpt',value,x,y,w,h,size);q.text.style={typeface:'Consolas',fontSize:size,color:black,autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};return q;}
function base(title,sub=''){
 const s=p.slides.add();s.background.fill='#FFFFFF';text(s,'title',title,64,36,1152,66,43,true);
 if(sub)text(s,'subtitle',sub,64,112,1152,60,25,false,gray);
 const page=text(s,'page',String(p.slides.items.length).padStart(2,'0'),1164,678,52,22,17,false,gray);page.text.style={alignment:'right'};return s;
}
function link(s,label,url,x=64,y=659,w=1082,size=17){const q=text(s,'source-link-'+s.shapes.items.length,label,x,y,w,29,size,false,gray);q.text.get(label).link={uri:url,isExternal:true};return q;}
function bullets(s,items,x,y,w,h,size=29,spacing=16){const q=text(s,'bullets-'+s.shapes.items.length,'',x,y,w,h,size);q.text=makeNativeBulletParagraphs(items.map(item=>' '+item),{marginLeftPoints:18,hangingPoints:9,spaceAfterPoints:spacing});q.text.style={typeface:FONT,fontSize:size,color:black,autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};return q;}
function table(s,values,widths,x,y,w,h,size=25){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
 t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({fill:'#FFFFFF',textStyle:{typeface:FONT,fontSize:size,color:black},margins:{left:12,right:12,top:8,bottom:8}});
 t.cells.block({row:0,column:0,rowCount:1,columnCount:values[0].length}).assign({fill:'#EEEEEE',textStyle:{typeface:FONT,fontSize:size,bold:true,color:black}});
 t.borders.assign({style:'solid',fill:'#999999',width:0.6});for(let i=0;i<values.length;i++)t.rows[i].height=i===0?55:(h-55)/(values.length-1);return t;
}
async function image(s,path,x,y,w,h,alt,crop){s.images.add({blob:new Uint8Array(await fs.readFile(path)),contentType:path.endsWith('.jpg')?'image/jpeg':'image/png',alt,fit:'contain',position:{left:x,top:y,width:w,height:h},...(crop?{crop}:{})});}
function box(s,name,value,x,y,w,h,size=26){const q=s.shapes.add({name,geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:'#FFFFFF',line:{fill:black,width:1.2}});q.text=value;q.text.style={typeface:FONT,fontSize:size,color:black,alignment:'center',verticalAlignment:'middle',autoFit:'none',insets:{left:10,right:10,top:8,bottom:8}};return q;}
function connect(s,a,b,fromSide='right',toSide='left'){s.shapes.connect(a,b,{kind:'elbow',fromSide,toSide,line:{fill:black,width:1.7},tail:{type:'triangle',width:'sm',length:'sm'}});}

// Measured experiment data populate slides 4, 5, 7 and 8 before export.
const data=await load(HERE+'/slide-evidence.json');

// 1. Existing project and GraphRAG.
{
 const s=base('AutoTriager: GNN-enhanced GraphRAG','Dahe Chen, CS 5588 Challenge 3, October 22, 2026');
 text(s,'purpose','Evidence for an engineer\ninvestigating service failures',64,192,588,107,37,true);
 bullets(s,['Existing GraphRAG connects incident observations with source-backed service knowledge.','Neo4j retrieves passages and paths. Gemini returns claims with evidence references.'],54,340,584,240,29,20);
 await image(s,HERE+'/assets/existing-aura.png',684,199,532,330,'Existing Neo4j Aura graph captured October 13, 2026',{top:0.125,right:0,left:0.1282051282051282,bottom:0.258});
 text(s,'kg-scope','Existing KG: 73 nodes, 124 relationships.\nVerified October 15. Screenshot: October 13.',684,557,532,69,24,false,gray);
 link(s,'Project: github.com/chendahe666/AutoTriager-Shop',WEB+'README.md');
}

// 2. Bounded motivation rather than an assumed gain.
{
 const s=base('Why add a GNN?','Question: can connected knowledge improve the evidence ranking?');
 text(s,'limitation','Current retrieval uses entity matching, graph traversal and lexical scores.',64,200,1152,79,34,true);
 bullets(s,['A relevant passage may use different words from the engineer\'s question.','A service, its operation and its documentation supply complementary context.','A learned node representation can incorporate information from these neighbors.'],54,325,1145,249,30,20);
 text(s,'scope-limit','This experiment measures retrieval. It does not measure root-cause accuracy.',64,596,1152,41,27,true);
 link(s,'GraphSAGE: Hamilton, Ying and Leskovec, NeurIPS 2017',PAPER);
}

// 3. Formula and matching implemented architecture.
{
 const s=base('GraphSAGE with mean aggregation','A node combines its own features with the average features of its neighbors.');
 text(s,'mean-formula','mᵥ = mean { hᵤ : u ∈ N(v) }',64,204,1152,57,38,true);
 text(s,'update-formula',data.architecture.formula,64,290,1152,64,36,true);
 bullets(s,data.architecture.bullets,54,404,1140,204,28,16);
 link(s,'Primary method: GraphSAGE, Algorithm 1',PAPER,64,661,620,17);
 link(s,'Implemented model and objective',WEB+data.codePath,720,661,495,17);
}

// 4. Concrete numbers from the actual run.
{
 const s=base('Message passing in the project graph',data.message.subtitle);
 const self=box(s,'self-node',data.message.selfLabel,64,204,285,103,26);
 const neighbors=box(s,'neighbor-nodes',data.message.neighborLabel,64,402,285,132,25);
 const update=box(s,'mean-update','Mean aggregation\n+ learned weights',474,288,310,136,28);
 const out=box(s,'updated-embedding','Updated\nnode embedding',927,288,289,136,29);
 connect(s,self,update);connect(s,neighbors,update);connect(s,update,out);
 code(s,data.message.values,414,464,802,137,24);
 text(s,'message-check',data.message.check,64,596,1152,44,25);
 link(s,'Recorded tensors and numerical reconstruction',WEB+data.messagePath);
}

// 5. Actual independent exercise and screenshot.
{
 const s=base('Hands-on project experiment','Independent project exercise, October 22. October 20 class materials were not available.');
 bullets(s,data.implementation.bullets,54,192,515,321,28,17);
 text(s,'implementation-result',data.implementation.result,64,554,505,80,28,true);
 await image(s,HERE+'/assets/v1-experiment.jpg',614,199,602,370,'Actual browser view of the recorded GNN experiment');
 text(s,'implementation-caption','Actual experiment report. All numbers\ncome from the saved local run.',614,584,602,63,24,false,gray);
 link(s,'Reproducible code, configuration and results',WEB+data.reportPath);
}

// 6. Explicitly requested native architecture diagram.
{
 const s=base('GNN ranking before evidence retrieval','The experiment ranks original evidence from a local snapshot of the existing graph.');
 const a=box(s,'knowledge','Existing KG model\nlocal snapshot',64,204,249,104,25);
 const b=box(s,'encoder','GraphSAGE\nnode embeddings',430,204,315,104);
 const c=box(s,'ranker','Question + 10 candidates\nGNN reranking',899,204,317,104,25);
 connect(s,a,b);connect(s,b,c);
 const d=box(s,'fetch','Top-5 passage IDs\nSource corpus lookup',899,409,317,108,26);
 const e=box(s,'packet','Original passages\n+ evidence IDs',430,409,315,108,27);
 const f=box(s,'answer','Existing LLM stage\nNot rerun today',64,409,249,108,25);
 connect(s,c,d,'bottom','top');connect(s,d,e,'left','right');connect(s,e,f,'left','right');
 text(s,'integration-status',data.integration,64,570,1152,69,27);
 link(s,'Neo4j GraphRAG for Python','https://neo4j.com/docs/neo4j-graphrag-python/current/',64,662,600,17);
 link(s,'Project integration example',WEB+data.integrationPath,727,662,489,17);
}

// 7. Same question, concrete evidence ranks.
{
 const s=base('An evidence-ranking example',data.ranking.question);
 table(s,data.ranking.table,[590,281,281],64,205,1152,290,25);
 text(s,'ranking-observation',data.ranking.observation,64,529,1152,67,30,true);
 text(s,'ranking-limit',data.ranking.limit,64,598,1152,56,23,false,gray);
 link(s,'Exact queries and ranked IDs',WEB+data.rankingPath,64,664,600,17);
 link(s,'RRF: Cormack et al., SIGIR 2009','https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf',720,664,496,17);
}

// 8. Measured outcomes with the controls that interpret them.
{
 const s=base('Retrieval results and limits',data.comparison.subtitle);
 table(s,data.comparison.table,[485,333,334],64,193,1152,267,25);
 text(s,'main-result',data.comparison.result,64,494,1152,43,30,true);
 text(s,'limits',data.comparison.limit,64,553,1152,91,24);
 link(s,'Complete metrics and experiment limitations',WEB+data.metricsPath);
}

// 9. Actual user-guided bounded development, with review status explicit.
{
 const s=base('Human-AI co-design','My direction: test GNN on this project, with at most three versions.');
 table(s,[['Step','Recorded guidance or implementation'],['My prompt (translated)','Try GNN on our system. Test the benefit. Explain failures and revise, up to three versions.'],['AI engineering',data.codesign.engineering],['Observed revision',data.codesign.change]], [289,863],64,199,1152,285,25);
 text(s,'learning','Recorded lesson',64,520,1152,38,30,true);
 text(s,'learning-body',data.codesign.lesson,64,570,1152,71,27);
 link(s,'Recorded human guidance and implementation changes',WEB+data.codesignPath);
}

// 10. Conclusions no broader than the execution evidence.
{
 const s=base('Lessons and next steps','The working example establishes a testable retrieval extension.');
 bullets(s,data.lessons,54,195,1138,291,31,20);
 text(s,'next-title','Before the October 26 report',64,527,1152,41,31,true);
 text(s,'next-body',data.nextSteps,64,585,1152,65,27);
 link(s,'Code and evidence: github.com/chendahe666/AutoTriager-Shop',WEB+'README.md');
}

await fs.mkdir(BUILD,{recursive:true});
await fs.writeFile(BUILD+'/presentation.json',JSON.stringify(p.toProto(),null,2));
await (await PresentationFile.exportPptx(p)).save(BUILD+'/candidate.pptx');
for(let i=0;i<p.slides.items.length;i++){const b=await p.export({slide:p.slides.items[i],format:'png',scale:1});await fs.writeFile(BUILD+`/slide-${i+1}.png`,new Uint8Array(await b.arrayBuffer()));}
console.log(JSON.stringify({slides:p.slides.items.length,draft:BUILD+'/candidate.pptx'}));
if(process.argv.includes('--finalize')){
 const finalPath=process.env.GNN_SLIDES_OUTPUT||REPO+'/output/slides/AutoTriager_Challenge3_GNN_Dahe_Chen_20261022_rebuilt.pptx';
 const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:BUILD+'/candidate.pptx',finalPath,explicitTotalSlideCount:10,requiredNativeTableOwnerSlides:[7,8,9],requiredNativeChartOwnerSlides:[],pythonExecutable:PYTHON,integrityValidatorPath:SKILL+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:SKILL+'/container_tools/inspect_presentation_layout_geometry.py',layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...[7,8,9].flatMap(n=>['--require-native-table-slide',String(n)])],fontPolicy:{basis:'design',families:[FONT,'Consolas']},verifyArtifactToolImport:true,receiptPath:BUILD+'/validation-final.json'});
 console.log(JSON.stringify({finalPath,result}));
}
