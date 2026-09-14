(() => {
  const $ = id => document.getElementById(id);
  const api = async (path, options={}) => {
    const response = await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    const body = await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(body.detail||body.error||`${response.status} ${response.statusText}`);
    return body;
  };
  const esc = value => String(value??'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let timer=null;
  function render(body){
    const s=body.state||{};
    $('curiosityStatus').textContent=`${s.enabled?'ATIVA':'PAUSADA'} · ${s.status||'desconhecido'}`;
    $('curiosityTopic').textContent=s.current_topic?`Tópico: ${s.current_topic} · origem: ${s.reason||'—'}`:'Sem tópico atual';
    $('curiosityCycles').textContent=s.cycle||0; $('curiositySearches').textContent=s.searches||0; $('curiosityPages').textContent=s.pages_read||0;
    $('curiosityDiscoveries').textContent=s.discoveries||0; $('curiosityJumps').textContent=s.jumps||0; $('curiosityErrors').textContent=s.errors||0;
    $('curiosityTrajectory').textContent=(s.trajectory||[]).join(' → ')||'—';
    $('curiosityPause').disabled=!s.enabled; $('curiosityResume').disabled=!!s.enabled;
    const events=(body.events||[]).slice(-40).reverse(); const box=$('curiosityEvents'); box.innerHTML='';
    if(!events.length){box.innerHTML='<p>Nenhuma atividade registrada ainda.</p>';return;}
    for(const e of events){
      const article=document.createElement('article'); article.className='curiosity-event';
      const title=e.kind==='evidence'?(e.title||e.message):e.message;
      let html=`<strong>${esc(e.kind||'evento')}</strong> · ${esc(title||'')}<br><small>${esc(e.time||'')}`;
      if(e.topic) html+=` · tópico: ${esc(e.topic)}`;
      if(e.novelty!==undefined) html+=` · novidade: ${esc(e.novelty)}`;
      if(e.confidence!==undefined) html+=` · confiança inicial: ${esc(e.confidence)}`;
      html+='</small>';
      if(e.url) html+=`<br><a href="${esc(e.url)}" target="_blank" rel="noreferrer">${esc(e.domain||e.url)}</a>`;
      if(e.excerpt) html+=`<p>${esc(String(e.excerpt).slice(0,500))}</p>`;
      article.innerHTML=html; box.appendChild(article);
    }
  }
  async function refresh(){
    try{render(await api('/api/server/v1/curiosity'));}
    catch(error){$('curiosityStatus').textContent=`Erro: ${error.message}`;}
  }
  async function action(name){
    try{render(await api(`/api/server/v1/curiosity/${name}`,{method:'POST',body:'{}'}));}
    catch(error){$('curiosityStatus').textContent=`Erro: ${error.message}`;}
  }
  $('curiosityPause')?.addEventListener('click',()=>action('pause'));
  $('curiosityResume')?.addEventListener('click',()=>action('resume'));
  $('curiosityJump')?.addEventListener('click',()=>action('jump'));
  $('curiosityCycle')?.addEventListener('click',()=>action('cycle'));
  $('curiosityRefresh')?.addEventListener('click',refresh);
  document.querySelector('[data-page="curiosity"]')?.addEventListener('click',refresh);
  refresh(); timer=setInterval(refresh,5000);
  window.addEventListener('beforeunload',()=>clearInterval(timer));
})();
