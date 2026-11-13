'use strict';

const $ = id => document.getElementById(id);
const state = {path: '', entries: [], selected: new Set(), total: 0, token: '', language: 'en', view: localStorage.getItem('udeck-files-view') || 'grid', tasks: [], generation: 0, collapsed: false};
const chinese = {
  'Files':'文件', 'Connected to your device':'已连接到设备', 'Connection lost':'设备连接已断开',
  'NETWORK ACCESS':'网络访问', 'Upload files':'上传文件', 'Upload folder':'上传文件夹',
  'New folder':'新建文件夹', 'Search this folder':'搜索当前文件夹', 'List view':'列表视图', 'Grid view':'网格视图', 'View options':'显示选项',
  'Sort':'排序', 'Name':'名称', 'Modified':'修改时间', 'Size':'大小', 'Reverse order':'倒序排列', 'Show hidden files':'显示隐藏文件',
  'Download':'下载', 'Copy':'复制', 'Move':'移动', 'Rename':'重命名', 'Move to trash':'移入回收站',
  'This folder is empty':'此文件夹为空', 'Loading…':'正在读取…', 'Drop files here, or choose Upload files.':'拖入文件，或点击“上传文件”。',
  'Drop into this folder':'松开，上传到此文件夹', 'Try again':'重试', 'Load more':'加载更多', 'Select all':'全选',
  'Transfers & tasks':'传输与任务', 'Clear selection':'取消选择', 'Close':'关闭', 'Cancel':'取消', 'Create':'创建', 'Save':'保存',
  'Folder name':'文件夹名称', 'Folder path':'文件夹路径', 'uDeck Files':'uDeck 文件', 'New name':'新名称', 'Selected':'已选择', 'items':'个项目', 'free':'可用', 'No matching files':'没有匹配的文件',
  'Try another name in this folder.':'试试其他文件名。', 'Cancel upload':'取消上传', 'Uploading':'上传中', 'Waiting':'等待中',
  'Completed':'已完成', 'Failed':'失败', 'Cancelled':'已取消', 'Preparing':'准备中', 'Running':'处理中', 'Skipped':'已跳过',
  'Choose destination':'选择目标文件夹', 'Use this folder':'使用此文件夹', 'Parent folder':'上级文件夹', 'Home':'共享文件夹',
  'An item with this name already exists':'已存在同名项目', 'A file with this name already exists':'已存在同名项目', 'Keep both':'保留两者', 'Skip':'跳过', 'Replace':'替换',
  'Replace the existing file?':'替换现有文件？', 'Only regular files can be replaced. Folders are never merged or overwritten.':'只替换普通文件，不合并或覆盖文件夹。',
  'Continue':'继续', 'Folder created':'文件夹已创建', 'Renamed':'已重命名', 'Download started':'已开始下载',
  'The selected items will be moved to the device’s Trash.':'所选项目将移入设备回收站。',
  'Links and special files are not shared':'符号链接及特殊文件不提供网络访问', 'Permission denied':'没有访问权限',
  'The file or folder is no longer available':'文件或文件夹已不可用', 'Choose another destination':'请选择其他目标文件夹',
  'Not enough free space':'可用空间不足', 'Upload is incomplete':'上传未完成', 'Upload cancelled':'上传已取消',
  'Upload size does not match':'上传大小不匹配', 'Choose a path inside the shared folder':'请选择共享范围内的路径',
  'Open this action from the Files page':'请从文件页面执行此操作', 'Refresh to reconnect to the device.':'刷新页面以重新连接设备。',
  'Network access has stopped':'网络访问已停止', 'Expected an object':'请求格式无效',
  'Wait for the current uploads':'请等待当前上传完成', 'Upload is already running':'上传正在进行中',
  'Unsupported operation':'不支持此操作', 'Wait for the current file tasks':'请等待当前文件任务完成',
  'Wait for the current downloads':'请等待当前下载完成', 'Download cancelled':'下载已取消',
  'Invalid server address':'服务器地址无效', 'Choose fewer files for one download':'请减少单次下载的文件数量',
  'Archive interrupted':'打包已中断', 'File changed during download':'下载期间文件已更改', 'Download interrupted':'下载已中断',
  'Atomic no-replace rename is not available':'当前环境不支持安全重命名',
  'The name cannot be empty or contain path separators':'名称不能为空，也不能包含路径分隔符',
  'Shared folder is no longer available':'共享文件夹已不可用', 'Choose a regular file':'请选择普通文件',
  'Folders are never merged or replaced':'不会合并或替换文件夹', 'Invalid upload':'上传请求无效',
  'Choose between 1 and 2000 items':'请选择 1 至 2000 个项目', 'Cannot copy a folder into itself':'不能将文件夹复制到自身',
  'Unsafe trash directory; no files were changed':'回收站文件夹不安全，未改动任何文件',
  'Destination changed during the operation':'操作期间目标位置已更改', 'Only regular files can be replaced':'只能替换普通文件',
  'Source changed':'源文件或文件夹已更改', 'Source changed during copy':'复制期间源文件或文件夹已更改',
  'The shared volume cannot use this trash; no file was deleted':'共享卷无法使用此回收站，未删除任何文件',
};
const t = text => state.language === 'zh_CN' ? chinese[text] || text : text;
const svg = {list:'<path d="M9 6h12M9 12h12M9 18h12M3 6h1M3 12h1M3 18h1"/>',grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',options:'<path d="M4 6h16M4 12h16M4 18h16M9 3v6M15 9v6M8 15v6"/>'};
function icon(kind) { return '<svg viewBox="0 0 24 24" aria-hidden="true">' + svg[kind] + '</svg>'; }
function size(bytes) { const units=['B','KiB','MiB','GiB','TiB']; let index=0; while(bytes>=1024 && index<4){bytes/=1024;index++;} return (index ? bytes.toFixed(1) : bytes) + ' ' + units[index]; }
function join(parent, name) { return parent ? parent + '/' + name : name; }
function element(tag, cls, text) { const item=document.createElement(tag); if(cls)item.className=cls; if(text!==undefined)item.textContent=text; return item; }
let toastTimer;
function toast(message) { $('toast').textContent=t(message); $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,5000); }
async function api(path, value, method='POST') {
  const response=await fetch('/api/'+path, value === undefined ? {} : {method,headers:{'Content-Type':'application/json','X-UDeck-Request':state.token},body:method==='DELETE'?undefined:JSON.stringify(value)});
  const result=await response.json();
  if(!response.ok){const error=new Error(t(result.error||'Failed')); error.code=result.code; error.status=response.status; throw error;}
  return result;
}
function translate() {
  document.documentElement.lang=state.language==='zh_CN'?'zh-CN':'en';
  document.querySelectorAll('[data-i18n]').forEach(item=>item.textContent=t(item.dataset.i18n));
  document.querySelectorAll('[data-placeholder]').forEach(item=>{item.placeholder=t(item.dataset.placeholder);item.setAttribute('aria-label',t(item.dataset.placeholder));});
  $('options-toggle').setAttribute('aria-label',t('View options'));
  $('options-toggle').title=t('View options');
  $('clear-selection').setAttribute('aria-label',t('Clear selection'));
  $('dialog-close').setAttribute('aria-label',t('Close'));
  $('files').setAttribute('aria-label',t('Files'));
  $('breadcrumbs').setAttribute('aria-label',t('Folder path'));
  document.querySelector('.brand').setAttribute('aria-label',t('uDeck Files'));
  document.title=t('Files')+' · uDeck';
  $('subtitle').textContent=(state.language==='zh_CN'?'共享自 ':'Shared from ') + state.rootName;
  updateView(); renderTasks();
}
async function config() {
  const data=await api('config');
  const changed=state.language!==data.language||state.rootName!==data.name;
  const restarted=!!state.token&&state.token!==data.requestToken;
  const reconnecting=$('connection').classList.contains('offline');
  state.language=data.language; state.rootName=data.name; state.token=data.requestToken;
  document.documentElement.dataset.theme=data.theme;
  if(changed || !$('subtitle').textContent)translate();
  $('connection').classList.remove('offline');
  $('connection').lastElementChild.textContent=t('Connected to your device');
  if(restarted||reconnecting)await load();
}
function offline(){ $('connection').classList.add('offline');$('connection').lastElementChild.textContent=t('Connection lost'); }
async function load({more=false}={}) {
  const generation=++state.generation;
  $('load-error').hidden=true;
  $('load-more').disabled=true;
  const params=new URLSearchParams({path:state.path,offset:more?state.entries.length:0,query:$('search').value,sort:$('sort').value,descending:$('descending').checked?'1':'0',hidden:$('hidden').checked?'1':'0'});
  try {
    const data=await api('files?'+params);
    if(generation!==state.generation)return;
    state.entries=more?state.entries.concat(data.entries):data.entries;
    state.total=data.total;state.freeBytes=data.freeBytes;
    const names=new Set(state.entries.map(row=>row.path));
    for(const path of state.selected)if(!names.has(path))state.selected.delete(path);
    render();
  } catch(error) {
    if(generation!==state.generation)return;
    $('load-error').hidden=false;$('load-error-message').textContent=error.message;
    state.entries=[];state.selected.clear();
    $('files').replaceChildren();$('files').hidden=true;$('list-heading').hidden=true;$('load-more').hidden=true;
    $('item-count').textContent='';$('space').textContent='';selection();
    $('empty').hidden=true;
    if(!error.status||error.status>=500)offline();
  } finally {
    if(generation===state.generation){$('loading').hidden=true;$('load-more').disabled=false;}
  }
}
function navigate(path, updateHash=true) {
  clearTimeout(searchTimer);
  state.path=path;state.selected.clear();$('search').value='';
  state.entries=[];$('files').replaceChildren();$('files').hidden=true;$('empty').hidden=true;$('list-heading').hidden=true;
  $('loading').hidden=false;renderBreadcrumbs();selection();
  if(updateHash)location.hash=encodeURIComponent(path);load();
}
function renderBreadcrumbs(container=$('breadcrumbs'), path=state.path, handler=navigate) {
  container.replaceChildren();
  const parts=path?path.split('/'):[];
  ['',...parts].forEach((name,index)=>{
    if(index)container.append(element('span','', '›'));
    const button=element('button','',index?name:state.rootName || t('Home'));
    button.type='button';button.onclick=()=>handler(parts.slice(0,index).join('/'));
    if(index===parts.length)button.setAttribute('aria-current','page');
    container.append(button);
  });
}
function selection() {
  const count=state.selected.size;
  $('selection').hidden=!count;
  $('selection-count').textContent=state.language==='zh_CN'?`已选择 ${count} 个项目`:`${count} selected`;
  $('rename').disabled=count!==1;
  $('files').classList.toggle('has-selection',!!count);
  document.querySelectorAll('.file').forEach(tile=>{
    const checked=state.selected.has(tile.dataset.path);
    tile.classList.toggle('selected',checked);tile.querySelector('.choose').checked=checked;
    tile.querySelector('.open').setAttribute('aria-pressed',String(checked));
  });
}
function render() {
  renderBreadcrumbs(); $('files').replaceChildren();
  for(const row of state.entries) {
    const tile=element('article','file'+(!row.usable?' unusable':''));tile.dataset.path=row.path;
    const checkbox=element('input','choose');checkbox.type='checkbox';checkbox.setAttribute('aria-label',(state.language==='zh_CN'?'选择 ':'Select ')+row.name);
    checkbox.disabled=!row.usable;
    checkbox.onchange=()=>{checkbox.checked?state.selected.add(row.path):state.selected.delete(row.path);selection();};
    const open=element('button','open');open.type='button';open.title=row.name;
    const image=element('img');image.src='/assets/icon/'+encodeURIComponent(row.icon);image.alt='';image.loading='lazy';
    open.append(image,element('span','file-name',row.name),element('span','file-size',row.directory?'—':size(row.size)),element('span','file-modified',new Date(row.modified*1000).toLocaleString(state.language==='zh_CN'?'zh-CN':'en',{dateStyle:'medium',timeStyle:'short'})));
    open.onclick=event=>{
      if(!row.usable){toast('Links and special files are not shared');return;}
      if(row.directory&&!event.ctrlKey&&!event.metaKey&&!state.selected.size)navigate(row.path);
      else {state.selected.has(row.path)?state.selected.delete(row.path):state.selected.add(row.path);selection();}
    };
    open.ondblclick=()=>{if(!row.usable)return;if(row.directory)navigate(row.path);else downloadPaths([row]).catch(error=>toast(error.message));};
    open.onkeydown=event=>{if(event.code==='Space'&&row.usable){event.preventDefault();checkbox.checked=!checkbox.checked;checkbox.onchange();}};
    tile.append(checkbox,open);$('files').append(tile);
  }
  $('files').hidden=!state.entries.length;
  $('empty').hidden=!!state.entries.length;
  $('empty').querySelector('h2').textContent=t($('search').value?'No matching files':'This folder is empty');
  $('empty').querySelector('p').textContent=t($('search').value?'Try another name in this folder.':'Drop files here, or choose Upload files.');
  $('load-more').hidden=state.entries.length>=state.total;
  $('item-count').textContent=state.total+' '+t('items');$('space').textContent=state.language==='zh_CN'?'可用 '+size(state.freeBytes):size(state.freeBytes)+' free';
  updateView();selection();
}
function updateView() {
  const list=state.view==='list';
  $('files').classList.toggle('files-list',list);$('list-heading').hidden=!list;
  $('view-toggle').innerHTML=icon(list?'grid':'list');
  $('view-toggle').title=t(list?'Grid view':'List view');$('view-toggle').setAttribute('aria-label',$('view-toggle').title);
}
let dialogSequence=Promise.resolve();
function dialog(title, description, content, buttons) {
  const next=()=>new Promise(resolve=>{
    const panel=$('dialog');$('dialog-title').textContent=t(title);$('dialog-body').textContent=description;
    $('dialog-content').replaceChildren();$('dialog-actions').replaceChildren();
    if(content)$('dialog-content').append(content);
    let settled=false;
    const done=value=>{if(settled)return;settled=true;panel.close();resolve(value);};
    for(const item of buttons){const button=element('button',item.primary?'primary':'',t(item.label));button.type='button';button.onclick=()=>done(item.value);$('dialog-actions').append(button);}
    panel.oncancel=event=>{event.preventDefault();done(null);};
    $('dialog-close').onclick=()=>done(null);
    $('dialog-form').onsubmit=event=>{event.preventDefault();const primary=$('dialog-actions').querySelector('.primary');if(primary&&!primary.disabled)primary.click();};
    panel.showModal();
    if(content?.tagName==='INPUT'){content.focus();content.select();}
  });
  const result=dialogSequence.then(next);dialogSequence=result.catch(()=>{});return result;
}
async function nameDialog(title, value, confirmLabel) {
  const input=element('input');input.type='text';input.value=value;input.setAttribute('aria-label',t(title));input.maxLength=255;
  const result=await dialog(title,'',input,[{label:'Cancel',value:null},{label:confirmLabel,value:true,primary:true}]);
  return result?input.value:null;
}
async function conflict(path, folder=false) {
  const buttons=[{label:'Cancel',value:null},{label:'Skip',value:'skip'}];
  if(!folder)buttons.push({label:'Replace',value:'replace'});
  buttons.push({label:'Keep both',value:'keep',primary:true});
  const policy=await dialog('An item with this name already exists',path,null,buttons);
  if(policy==='replace')return await dialog('Replace the existing file?',t('Only regular files can be replaced. Folders are never merged or overwritten.'),null,[{label:'Cancel',value:null},{label:'Replace',value:true,primary:true}])?'replace':null;
  return policy;
}
async function destination(action) {
  let current=state.path,generation=0,loaded=0;
  const container=element('div');const nav=element('div','picker-path');const folders=element('div','folder-picker');container.append(nav,folders);
  function ready(value){const confirm=container.closest('dialog')?.querySelector('.primary');if(confirm)confirm.disabled=!value;}
  async function show(path,{more=false}={}){
    const request=++generation;ready(false);
    let data;
    try{data=await api('files?'+new URLSearchParams({path,offset:more?loaded:0,limit:500,hidden:$('hidden').checked?'1':'0'}));}
    catch(error){if(request===generation)throw error;return;}
    if(request!==generation)return;
    current=path;nav.textContent=(state.rootName||t('Home'))+(path?' / '+path.replaceAll('/',' / '):'');
    if(!more){
      loaded=0;folders.replaceChildren();
      if(path){const up=element('button','', '↑  '+t('Parent folder'));up.type='button';up.onclick=()=>show(path.split('/').slice(0,-1).join('/')).catch(error=>toast(error.message));folders.append(up);}
    }else folders.querySelector('.picker-more')?.remove();
    for(const row of data.entries.filter(row=>row.directory)){const button=element('button');button.type='button';const img=element('img');img.src='/assets/icon/folder';img.alt='';button.append(img,element('span','',row.name));button.onclick=()=>show(row.path).catch(error=>toast(error.message));folders.append(button);}
    loaded+=data.entries.length;
    if(loaded<data.total&&data.entries.at(-1)?.directory){const button=element('button','picker-more',t('Load more'));button.type='button';button.onclick=()=>show(path,{more:true}).catch(error=>toast(error.message));folders.append(button);}
    ready(true);
  }
  await show(current);
  return await dialog('Choose destination',t(action),container,[{label:'Cancel',value:null},{label:'Use this folder',value:true,primary:true}])?{path:current}:null;
}
function chosen(){return state.entries.filter(row=>state.selected.has(row.path));}
function triggerDownload(url){const link=element('a');link.href=url;link.download='';document.body.append(link);link.click();link.remove();toast('Download started');}
async function downloadPaths(rows) {
  if(!rows.length)return;
  if(rows.length===1&&!rows[0].directory)triggerDownload('/api/download?'+new URLSearchParams({path:rows[0].path}));
  else {const ticket=await api('archives',{paths:rows.map(row=>row.path)});triggerDownload('/api/archives/'+ticket.id);}
}
function addTask(value) {
  const task={id:crypto.randomUUID?crypto.randomUUID():String(Date.now()+Math.random()),progress:0,state:'Waiting',...value};
  state.tasks.push(task);state.tasks=state.tasks.slice(-64);state.collapsed=false;renderTasks();return task;
}
function renderTasks() {
  $('transfers').hidden=!state.tasks.length;$('transfer-items').hidden=state.collapsed;
  $('transfer-count').textContent=state.tasks.filter(task=>['Waiting','Uploading','Running','Preparing'].includes(task.state)).length||state.tasks.length;
  $('transfer-arrow').textContent=state.collapsed?'⌃':'⌄';$('transfer-items').replaceChildren();
  for(const task of state.tasks.slice(-8).reverse()) {
    const row=element('div','transfer-row');const label=element('div','transfer-label');label.append(element('span','',task.name));
    if(task.cancel&&['Waiting','Uploading','Running','Preparing'].includes(task.state)){const cancel=element('button','',t('Cancel'));cancel.onclick=()=>task.cancel();label.append(cancel);}
    const progress=element('progress');progress.max=1;progress.value=task.progress||0;progress.setAttribute('aria-label',task.name);
    row.append(label,progress,element('div','transfer-detail',t(task.state)+(task.detail?' · '+task.detail:'')));$('transfer-items').append(row);
  }
}
async function fileTask(action) {
  const rows=chosen();if(!rows.length)return;
  let target={path:''},policy='error';
  if(action==='trash'){
    const result=await dialog('Move to trash',t('The selected items will be moved to the device’s Trash.'),null,[{label:'Cancel',value:null},{label:'Move to trash',value:true,primary:true}]);if(!result)return;
  }else{
    target=await destination(action==='copy'?'Copy':'Move');if(!target)return;
    const result=await api('conflicts',{paths:rows.map(row=>row.path),destination:target.path});
    if(result.conflicts.length){policy=await conflict(result.conflicts.join('\n'),rows.some(row=>row.directory));if(!policy)return;}
  }
  const server=await api('tasks',{action,paths:rows.map(row=>row.path),destination:target.path,policy});
  const task=addTask({name:t(action==='copy'?'Copy':action==='move'?'Move':'Move to Trash')+' · '+rows.length,state:'Waiting'});
  task.cancel=()=>api('tasks/'+server.id,{},'DELETE').catch(error=>toast(error.message));
  const poll=async()=>{
    try{const result=await api('tasks/'+server.id);task.progress=result.totalItems?(result.doneItems+result.skipped)/result.totalItems:0;
      task.state={queued:'Waiting',running:'Running',completed:'Completed',failed:'Failed',cancelled:'Cancelled'}[result.state];
      task.detail=result.errors.map(error=>error.path+': '+t(error.reason)).join('\n')||(result.doneItems+'/'+result.totalItems+(result.doneBytes?' · '+size(result.doneBytes):'')+(result.state==='running'&&result.speed?' · '+size(result.speed)+'/s':''));
      renderTasks();if(['queued','running'].includes(result.state))setTimeout(poll,500);else{await load();}
    }catch(error){task.state='Failed';task.detail=error.message;renderTasks();}
  };poll();state.selected.clear();selection();
}
function uploadBytes(file, id, task) {
  return new Promise((resolve,reject)=>{
    const started=performance.now();
    const xhr=new XMLHttpRequest();xhr.open('PUT','/api/uploads/'+id);xhr.setRequestHeader('X-UDeck-Request',state.token);
    task.cancel=()=>{task.cancelled=true;xhr.abort();api('uploads/'+id,{},'DELETE').catch(()=>{});};
    xhr.upload.onprogress=event=>{task.progress=event.lengthComputable?event.loaded/event.total:0;task.detail=size(event.loaded)+' / '+size(file.size)+' · '+size(event.loaded/Math.max(.1,(performance.now()-started)/1000))+'/s';renderTasks();};
    xhr.onload=()=>{let value;try{value=JSON.parse(xhr.responseText);}catch{reject(new Error(t('Failed')));return;}xhr.status===200?resolve(value):reject(new Error(t(value.error)));};
    xhr.onerror=()=>reject(new Error(t('Refresh to reconnect to the device.')));xhr.onabort=()=>reject(new Error(t('Cancelled')));xhr.send(file);
  });
}
async function uploadItems(files, directories=[]) {
  const base=state.path;
  const folders=new Set(directories), mapping=new Map(), skipped=[];
  for(const item of files){const parts=item.path.split('/');for(let i=1;i<parts.length;i++)folders.add(parts.slice(0,i).join('/'));}
  const isSkipped=path=>skipped.some(parent=>path===parent||path.startsWith(parent+'/'));
  const target=path=>{const parts=path.split('/'),name=parts.pop(),parent=parts.join('/');return join(mapping.get(parent)??base,name);};
  for(const directory of [...folders].sort((a,b)=>a.split('/').length-b.split('/').length||a.localeCompare(b))){
    if(isSkipped(directory))continue;
    let result;
    try{result=await api('folders',{path:target(directory)});}
    catch(error){
      if(error.code!=='conflict'){toast(error.message);skipped.push(directory);continue;}
      const policy=await conflict(directory,true);
      if(!policy||policy==='skip'){skipped.push(directory);continue;}
      try{result=await api('folders',{path:target(directory),policy});}
      catch(failure){toast(failure.message);skipped.push(directory);continue;}
    }
    mapping.set(directory,result.path);
  }
  const queue=files.filter(item=>!isSkipped(item.path)).map(item=>({file:item.file,path:target(item.path),task:addTask({name:item.path,state:'Waiting',cancelled:false})}));
  for(const item of queue)item.task.cancel=()=>{item.task.cancelled=true;item.task.state='Cancelled';renderTasks();};
  let cursor=0;
  async function worker(){
    while(cursor<queue.length){const item=queue[cursor++],task=item.task;if(task.cancelled)continue;
      let id;
      try{
        task.state='Preparing';renderTasks();let upload;
        try{upload=await api('uploads',{path:item.path,size:item.file.size});}
        catch(error){if(error.code!=='conflict')throw error;const policy=await conflict(item.path);if(!policy||policy==='skip'){task.state=policy?'Skipped':'Cancelled';renderTasks();continue;}upload=await api('uploads',{path:item.path,size:item.file.size,policy});}
        id=upload.id;if(task.cancelled){await api('uploads/'+id,{},'DELETE');continue;}
        task.state='Uploading';renderTasks();await uploadBytes(item.file,id,task);
        task.state='Completed';task.progress=1;
      }catch(error){task.state=task.cancelled?'Cancelled':'Failed';task.detail=error.message;if(id)await api('uploads/'+id,{},'DELETE').catch(()=>{});}
      renderTasks();
    }
  }
  await Promise.all([worker(),worker()]);if(folders.size&&!queue.length)toast('Folder created');await load();
}
async function dropped(data) {
  const files=[],directories=[];
  const directFiles=[...data.files];
  async function entry(value,prefix=''){
    if(value.isFile){const file=(!prefix&&directFiles.find(file=>file.name===value.name))||await new Promise((resolve,reject)=>value.file(resolve,reject));files.push({file,path:join(prefix,file.name)});}
    else if(value.isDirectory){const path=join(prefix,value.name);directories.push(path);const reader=value.createReader();while(true){const children=await new Promise((resolve,reject)=>reader.readEntries(resolve,reject));if(!children.length)break;for(const child of children)await entry(child,path);}}
  }
  const items=[...data.items];
  // Capture entries before the browser invalidates the drag data store.
  const entries=items.map(item=>item.webkitGetAsEntry?.()).filter(Boolean);
  if(entries.length){
    for(const value of entries)await entry(value);
  }else for(const file of directFiles)files.push({file,path:file.name});
  await uploadItems(files,directories);
}
function action(id, handler){$(id).onclick=()=>Promise.resolve().then(handler).catch(error=>toast(error.message));}
action('download',()=>downloadPaths(chosen()));
action('copy',()=>fileTask('copy'));action('move',()=>fileTask('move'));action('trash',()=>fileTask('trash'));
action('new-folder',async()=>{const name=await nameDialog('Folder name','','Create');if(name!==null){await api('folders',{path:join(state.path,name)});toast('Folder created');await load();}});
action('rename',async()=>{const row=chosen()[0];if(!row)return;const name=await nameDialog('New name',row.name,'Save');if(name!==null){await api('rename',{path:row.path,name});state.selected.clear();toast('Renamed');await load();}});
action('view-toggle',()=>{state.view=state.view==='list'?'grid':'list';localStorage.setItem('udeck-files-view',state.view);updateView();});
action('options-toggle',()=>$('view-options').hidden=!$('view-options').hidden);
action('clear-selection',()=>{state.selected.clear();selection();});
action('select-all',()=>{for(const row of state.entries)if(row.usable)state.selected.add(row.path);selection();});
action('load-more',()=>load({more:true}));action('retry',()=>load());
action('transfers-toggle',()=>{state.collapsed=!state.collapsed;renderTasks();});
action('upload-button',()=>$('file-input').click());action('upload-folder',()=>$('folder-input').click());
for(const id of ['file-input','folder-input'])$(id).onchange=event=>{const files=[...event.target.files].map(file=>({file,path:file.webkitRelativePath||file.name}));event.target.value='';uploadItems(files).catch(error=>toast(error.message));};
let searchTimer;
$('search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>load(),200);};
for(const id of ['sort','descending','hidden'])$(id).onchange=()=>load();
$('options-toggle').innerHTML=icon('options');
let dragDepth=0;
document.addEventListener('dragenter',event=>{if([...event.dataTransfer.types].includes('Files')){event.preventDefault();dragDepth++;$('drop-overlay').hidden=false;$('drop-destination').textContent=(state.rootName||'')+(state.path?' / '+state.path:'');}});
document.addEventListener('dragover',event=>{if([...event.dataTransfer.types].includes('Files'))event.preventDefault();});
document.addEventListener('dragleave',()=>{if(--dragDepth<=0){dragDepth=0;$('drop-overlay').hidden=true;}});
document.addEventListener('drop',event=>{event.preventDefault();dragDepth=0;$('drop-overlay').hidden=true;if(!$('dialog').open)dropped(event.dataTransfer).catch(error=>toast(error.message));});
document.addEventListener('keydown',event=>{
  if($('dialog').open||['INPUT','SELECT','TEXTAREA'].includes(event.target.tagName))return;
  if((event.ctrlKey||event.metaKey)&&event.key==='a'){event.preventDefault();$('select-all').click();}
  if(event.key==='Escape'){state.selected.clear();selection();}
});
window.addEventListener('hashchange',()=>{let path;try{path=decodeURIComponent(location.hash.slice(1));}catch{return;}if(path!==state.path)navigate(path,false);});
(async()=>{try{state.path=decodeURIComponent(location.hash.slice(1));await config();await load();}catch(error){offline();$('load-error').hidden=false;$('load-error-message').textContent=error.message;}setInterval(()=>config().catch(offline),5000);})();
