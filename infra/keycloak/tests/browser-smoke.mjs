import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import https from 'node:https';
import {createPublicKey, verify} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const require = createRequire(fileURLToPath(new URL('../../../frontend-new/package.json', import.meta.url)));
const {chromium} = require('@playwright/test');
let input=''; for await (const chunk of process.stdin) input+=chunk;
const config=JSON.parse(input);
if(config.mode==='console') {
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({ignoreHTTPSErrors:true});
  const page=await context.newPage();
  let stage='console login';
  try {
    await page.goto(config.url);
    await page.locator('#username').fill(config.username);
    await page.locator('#password').fill(config.password);
    await page.locator('#kc-login').click();
    stage='temporary password update';
    await page.locator('#password-new').fill(config.newPassword);
    await page.locator('#password-confirm').fill(config.newPassword);
    await page.locator('input[type="submit"],button[type="submit"]').click();
    stage='required user profile';
    await page.locator('#email').waitFor();
    await page.locator('#email').fill('console-user@integration.test');
    await page.locator('#firstName').fill('Console');
    await page.locator('#lastName').fill('Team');
    await page.locator('input[type="submit"],button[type="submit"]').click();
    stage='team realm administration';
    await page.getByRole('link',{name:'Users',exact:true}).waitFor({timeout:30000});
    const prefix=new URL(config.url).pathname.split('/admin/')[0];
    const master=await context.request.get(new URL(prefix+'/admin/master',config.url).href);
    if(master.status()!==403) throw Error('Master console accepted team');
    console.log(JSON.stringify({passed:true,teamConsole:true,master403:true}));
  } catch(error) {const text=(await page.locator('body').innerText()).replaceAll(config.username,'[user]').replaceAll(config.password,'[redacted]').replaceAll(config.newPassword,'[redacted]'); console.error('Console flow failed during '+stage+': '+error.name+'; visible text: '+text.slice(0,2000));process.exitCode=1;}
  finally {await browser.close();}
  process.exit(process.exitCode||0);
}
function testJSON(url) {
  return new Promise((resolve,reject)=>https.get(url,{rejectUnauthorized:false},res=>{
    let raw='';res.on('data',chunk=>raw+=chunk);res.on('end',()=>{try {resolve(JSON.parse(raw));} catch {reject(new Error('Invalid test JSON'));}});
  }).on('error',reject));
}
const discovery=await testJSON(config.issuer+'/.well-known/openid-configuration');
const jwks=await testJSON(discovery.jwks_uri);
function authorized(token) {
  try {
    const [header,body,signature]=token.split('.');
    const h=JSON.parse(Buffer.from(header,'base64url')), p=JSON.parse(Buffer.from(body,'base64url'));
    const key=jwks.keys.find(k=>k.kid===h.kid);
    const aud=Array.isArray(p.aud)?p.aud:[p.aud];
    return h.alg==='RS256' && p.iss===config.issuer && aud.includes(config.clientId) && p.exp>Date.now()/1000 &&
      verify('RSA-SHA256',Buffer.from(header+'.'+body),createPublicKey({key,format:'jwk'}),Buffer.from(signature,'base64url'));
  } catch {return false;}
}
const server=createServer((req,res)=>{
  if(req.url==='/protected') {res.writeHead(authorized((req.headers.authorization||'').replace(/^Bearer /,''))?200:401);res.end('protected');return;}
  res.setHeader('Content-Type','text/html');
  res.end(`<!doctype html><html><body><div id="status">anonymous</div><button id="login">login</button><button id="refresh">refresh</button><button id="logout">logout</button><script>
  const c=${JSON.stringify({issuer:config.issuer,clientId:config.clientId})};
  const d=${JSON.stringify(discovery)};
  const b64=b=>btoa(String.fromCharCode(...new Uint8Array(b))).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
  let tokens=JSON.parse(sessionStorage.getItem('tokens')||'null');
  const status=document.querySelector('#status');
  document.querySelector('#login').onclick=async()=>{
    const verifier=b64(crypto.getRandomValues(new Uint8Array(32)));
    const state=b64(crypto.getRandomValues(new Uint8Array(16)));
    sessionStorage.setItem('verifier',verifier); sessionStorage.setItem('state',state);
    const challenge=b64(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier)));
    location.href=d.authorization_endpoint+'?'+new URLSearchParams({client_id:c.clientId,redirect_uri:location.origin+'/',response_type:'code',scope:'openid',code_challenge_method:'S256',code_challenge:challenge,state});
  };
  document.querySelector('#refresh').onclick=async()=>{
    const r=await fetch(d.token_endpoint,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'refresh_token',client_id:c.clientId,refresh_token:tokens.refresh_token})});
    if(!r.ok) throw Error('refresh failed'); tokens=await r.json();sessionStorage.setItem('tokens',JSON.stringify(tokens));status.textContent='refreshed';
  };
  document.querySelector('#logout').onclick=()=>{
    const token=tokens.id_token;sessionStorage.removeItem('tokens');
    location.href=d.end_session_endpoint+'?'+new URLSearchParams({id_token_hint:token,post_logout_redirect_uri:location.origin+'/'});
  };
  (async()=>{
    const p=new URLSearchParams(location.search);
    if(p.has('code')){
      if(p.get('state')!==sessionStorage.getItem('state')) throw Error('state mismatch');
      const r=await fetch(d.token_endpoint,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'authorization_code',client_id:c.clientId,code:p.get('code'),redirect_uri:location.origin+'/',code_verifier:sessionStorage.getItem('verifier')})});
      if(!r.ok) throw Error('code exchange failed'); tokens=await r.json();sessionStorage.setItem('tokens',JSON.stringify(tokens));history.replaceState(null,'','/');
    }
    if(tokens){const r=await fetch('/protected',{headers:{Authorization:'Bearer '+tokens.access_token}});status.textContent=r.ok?'authenticated':'rejected';}
  })();
  </script></body></html>`);
});
await new Promise(resolve=>server.listen(5173,'127.0.0.1',resolve));
const origin=`http://localhost:${server.address().port}`;
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({ignoreHTTPSErrors:true});
const page=await context.newPage();
let stage='anonymous';
const gatewayRequests=[];page.on('request',r=>{if(r.url().startsWith(new URL(config.issuer).origin)) gatewayRequests.push(r.url());});
try {
  const anonymous=await context.request.get(origin+'/protected');
  if(anonymous.status()!==401) throw Error('Anonymous request accepted');
  stage='login'; await page.goto(origin);
  await page.locator('#login').click();
  await page.locator('#username').fill(config.username);
  await page.locator('#password').fill(config.password);
  await page.locator('#kc-login').click();
  await page.locator('#status').filter({hasText:'authenticated'}).waitFor({timeout:30000});
  stage='other issuer'; const wrongCode=await page.evaluate(async otherIssuer=>{
    const r=await fetch(otherIssuer+'/protocol/openid-connect/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'authorization_code',client_id:'integration-public',code:'foreign-code',redirect_uri:location.origin+'/'} )});return r.status;
  },config.otherIssuer);
  if(wrongCode<400) throw Error('Other issuer accepted code');
  const badToken=await context.request.get(origin+'/protected',{headers:{Authorization:'Bearer invalid'}});
  if(badToken.status()!==401) throw Error('Invalid token accepted');
  const otherToken=await context.request.get(origin+'/protected',{headers:{Authorization:'Bearer '+config.otherToken}});
  if(otherToken.status()!==401) throw Error('Other realm token accepted');
  stage='refresh'; await page.locator('#refresh').click();
  await page.locator('#status').filter({hasText:'refreshed'}).waitFor();
  const cookieBefore=(await context.cookies()).some(c=>c.path.startsWith('/clusters/public-01') && c.name.includes('KEYCLOAK'));
  if(!cookieBefore) throw Error('Missing scoped Keycloak cookie');
  stage='logout'; await page.locator('#logout').click();
  await page.locator('#status').filter({hasText:'anonymous'}).waitFor();
  if(gatewayRequests.some(url=>!new URL(url).pathname.startsWith('/clusters/'))) throw Error('Resource escaped instance prefix');
  console.log(JSON.stringify({passed:true,login:true,refresh:true,logout:true,anonymous401:true,wrongIssuerRejected:true}));
} catch(error) {
  // No URLs, token bodies, screenshots or credentials in error output.
  console.error('Browser flow failed during '+stage+': '+error.name);
  process.exitCode=1;
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
