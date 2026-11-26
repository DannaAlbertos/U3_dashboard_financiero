// node --test U3_Act3/tests/test_asignacion_roles_frontend.cjs
// Pruebas del JavaScript real con DOM y transporte controlados; no son navegador.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const vm = require('node:vm');

const html = readFileSync(resolve(__dirname, '../../dashboard.html'), 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const role = {id:'23',code:'CONSULTA',name:'Consulta'};
const next = {id:'47',code:'CAPTURISTA',name:'Capturista'};
const member = {id:'91',userId:'7',userName:'Persona de prueba',userEmail:'persona@prueba.invalid',
                isActive:true,isAdmin:false,roleName:role.name,role};

class Element {
  constructor(){ this.dataset={on:'false'}; this.value=''; this.hidden=false; this.disabled=false;
    this.classList={toggle(){},add(){},remove(){}}; this.children=[]; this.content=''; }
  set innerHTML(value){
    this.content=value; this.children=[];
    for(const m of value.matchAll(/<(select|button)\b([^>]*data-role-(select|save)="([^"]+)"[^>]*)>([\s\S]*?)<\/\1>/g)){
      const el=new Element(); el.dataset[m[3]==='select'?'roleSelect':'roleSave']=m[4];
      el.disabled=/\bdisabled\b/.test(m[2]);
      if(m[1]==='select'){
        const options=[...m[5].matchAll(/<option value="([^"]*)"([^>]*)>/g)];
        el.value=(options.find(o=>/\bselected\b/.test(o[2]))||options[0])?.[1]||'';
      }
      this.children.push(el);
    }
  }
  get innerHTML(){return this.content;}
  querySelectorAll(s){
    if(s==='[data-role-select]')return this.children.filter(c=>'roleSelect' in c.dataset);
    if(s==='[data-role-save]')return this.children.filter(c=>'roleSave' in c.dataset);
    return [];
  }
  addEventListener(){}
}

function setup(perms=['company.users.read','roles.write']){
  const elements=new Map(), storage=new Map(), calls=[], listeners={};
  const element=s=>{if(!elements.has(s))elements.set(s,new Element());return elements.get(s);};
  const context=vm.createContext({console,Set,Map,Date,Promise,JSON,
    document:{querySelector:element,querySelectorAll:()=>[]},
    window:{addEventListener:(event,fn)=>listeners[event]=fn},
    sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,String(v)),clear:()=>storage.clear()},
    fetch:async(url,options)=>{
      const body=JSON.parse(options.body);calls.push({url,headers:options.headers,...body});
      return {ok:true,json:async()=>({data:await handler(body.query,body.variables)})};
    },
  });
  let handler=async query=>{
    if(query.includes('myPermissions'))return {myPermissions:perms.map(code=>({code}))};
    if(query.includes('companyUsers'))return {companyUsers:[member]};
    if(query.includes('roles('))return {roles:[next,role]};
    throw Error('Operación inesperada');
  };
  vm.runInContext(source,context);
  storage.set('tk','sesion-ficticia-del-test');
  vm.runInContext(`savePerms(${JSON.stringify(perms)});_usuarios=${JSON.stringify([member])};_rolesAsignables=${JSON.stringify([role,next])};`,context);
  return {run:s=>vm.runInContext(s,context),element,calls,listeners,context,
          respond:fn=>handler=fn};
}

test('selector usa IDs reales, puesto actual, Guardar y ninguna escritura isAdmin',()=>{
  const s=setup();s.run('renderUsuarios()');
  const [select]=s.element('#us-list').querySelectorAll('[data-role-select]');
  const [button]=s.element('#us-list').querySelectorAll('[data-role-save]');
  assert.equal(select.value,'23');assert.equal(select.dataset.roleSelect,'91');assert.equal(button.disabled,true);
  select.value='47';select.onchange();assert.equal(button.disabled,false);
  assert.match(s.element('#us-list').innerHTML,/Consulta/);
  assert.equal(s.run('_usuarios[0].isAdmin'),false);
});

test('sin roles.write no se muestran controles aunque isAdmin sea verdadero',()=>{
  const s=setup(['company.users.read']);s.run('_usuarios[0].isAdmin=true;renderUsuarios()');
  assert.equal(s.element('#us-list').querySelectorAll('[data-role-select]').length,0);
  assert.match(s.element('#us-list').innerHTML,/Consulta/);
});

test('sin rol se ofrece selector y las membresías inactivas no tienen controles',()=>{
  const s=setup();s.run('_usuarios[0].role=null;_usuarios[0].roleName=null;renderUsuarios()');
  assert.match(s.element('#us-list').innerHTML,/Sin rol/);
  assert.equal(s.element('#us-list').querySelectorAll('[data-role-select]')[0].value,'');
  s.run('_usuarios[0].isActive=false;renderUsuarios()');
  assert.equal(s.element('#us-list').querySelectorAll('[data-role-select]').length,0);
});

test('carga roles activos del servidor y ordena sin inventar IDs',async()=>{
  const s=setup();await s.run('loadUsuarios()');
  assert.ok(s.calls.some(c=>c.query.includes('roles(activeOnly:true)')));
  assert.deepEqual(JSON.parse(s.run('JSON.stringify(_rolesAsignables.map(r=>r.id))')),['47','23']);
});

test('sin roles.write ni siquiera se consulta el catálogo de puestos',async()=>{
  const s=setup(['company.users.read']);await s.run('loadUsuarios()');
  assert.ok(!s.calls.some(c=>c.query.includes('roles(')));
});

test('guarda membresía correcta con Bearer y recarga el puesto confirmado',async()=>{
  const s=setup();s.respond(async q=>{
    if(q.includes('assignRole'))return {assignRole:true};
    if(q.includes('companyUsers'))return {companyUsers:[{...member,roleName:'Nombre del servidor',role:next}]};
    return {myPermissions:[{code:'roles.write'},{code:'company.users.read'}]};
  });
  await s.run('guardarRol("91","47")');
  const call=s.calls.find(c=>c.query.includes('assignRole'));
  assert.deepEqual(call.variables,{companyUserId:'91',roleId:'47'});
  assert.equal(call.headers.Authorization,'Bearer sesion-ficticia-del-test');
  assert.equal(s.run('_usuarios[0].roleName'),'Nombre del servidor');
  assert.match(s.element('#us-err').innerHTML,/Puesto actualizado/);
});

test('HTTP 200 con errors se rechaza y conserva el puesto anterior',async()=>{
  const s=setup();
  s.context.fetch=async(url,options)=>{
    const q=JSON.parse(options.body).query;
    return {ok:true,json:async()=>q.includes('assignRole')
      ? {errors:[{message:'El rol está inactivo <servidor>'}]}
      : {data:{myPermissions:[{code:'roles.write'},{code:'company.users.read'}]}}};
  };
  await s.run('guardarRol("91","47")');
  assert.equal(s.run('_usuarios[0].role.id'),'23');
  assert.match(s.element('#us-err').innerHTML,/El rol está inactivo/);
  assert.ok(!s.element('#us-err').innerHTML.includes('<servidor>'));
});

test('bloquea controles y evita envíos simultáneos o repetidos',async()=>{
  const s=setup();let finish;
  s.respond(q=>q.includes('assignRole') ? new Promise(resolve=>finish=()=>resolve({assignRole:true})) :
    Promise.resolve(q.includes('myPermissions')?{myPermissions:[{code:'roles.write'},{code:'company.users.read'}]}:
      {companyUsers:[{...member,roleName:next.name,role:next}]}));
  const pending=s.run('guardarRol("91","47")');
  assert.equal(s.element('#us-list').querySelectorAll('[data-role-select]')[0].disabled,true);
  assert.match(s.element('#us-err').innerHTML,/Guardando/);
  await s.run('guardarRol("91","47")');
  assert.equal(s.calls.filter(c=>c.query.includes('assignRole')).length,1);
  finish();await pending;
  await s.run('guardarRol("91","47")');
  assert.equal(s.calls.filter(c=>c.query.includes('assignRole')).length,1);
});

test('actualiza permisos del JWT vigente y elimina controles sin inferir por rol',async()=>{
  const s=setup();s.respond(async()=>({myPermissions:[{code:'company.users.read'}]}));
  await s.run('fetchPerms()');s.run('renderUsuarios()');
  assert.equal(s.element('#us-list').querySelectorAll('[data-role-select]').length,0);
  assert.equal(s.run('getToken()'),'sesion-ficticia-del-test');
  assert.equal(typeof s.listeners.focus,'function');
});

test('fallo al consultar permisos vacía la caché y no concede roles.write',async()=>{
  const s=setup();s.respond(async()=>{throw Error('desconectado');});
  await assert.rejects(s.run('fetchPerms()'));
  assert.equal(s.run('hasPerms("roles.write")'),false);
});

test('al volver a la pestaña actualiza controles sin recargar borradores de la matriz',async()=>{
  const s=setup(['roles.read','roles.write']);
  s.run(`sessionStorage.setItem('route','roles');
    var reloads=0, refreshes=0;
    RolesMatrixModule.load=()=>{reloads++};
    RolesMatrixModule.refreshAccess=()=>{refreshes++};`);
  s.respond(async()=>({myPermissions:[{code:'roles.read'}]}));
  await s.listeners.focus();
  assert.equal(s.run('reloads'),0);
  assert.equal(s.run('refreshes'),1);
  assert.equal(s.run('hasPerms("roles.write")'),false);
});
