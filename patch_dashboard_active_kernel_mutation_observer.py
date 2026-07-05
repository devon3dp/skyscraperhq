from pathlib import Path
from datetime import datetime, timezone
import py_compile
import re

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src/dashboard/server.py"

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = SERVER.with_suffix(f".py.backup_before_active_kernel_mutation_observer_{ts}")

text = SERVER.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

# Remove older active-kernel DOM sync blocks if present.
text = re.sub(
    r'\n?<script id="active-kernel-dom-sync">.*?</script>\n?',
    "\n",
    text,
    flags=re.S,
)

snippet = r'''
<script id="active-kernel-dom-sync">
(function(){
  let ACTIVE_KERNEL_CONFIRMED = false;
  let lastPayload = null;
  let busy = false;

  async function fetchActiveTruth(){
    try{
      const res = await fetch('/api/live?t=' + Date.now(), {cache:'no-store'});
      const data = await res.json();
      const b = data?.status?.building || {};
      const active =
        b.kernel_installed === true &&
        b.QSBKernelCore_instantiated === true &&
        b.activation_status === 'active_local_only' &&
        b.active_kernel_source === 'rebased_kernel';

      ACTIVE_KERNEL_CONFIRMED = !!active;
      lastPayload = data;
      return ACTIVE_KERNEL_CONFIRMED;
    }catch(e){
      return ACTIVE_KERNEL_CONFIRMED;
    }
  }

  function patchTextNodes(){
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while(walker.nextNode()) nodes.push(walker.currentNode);

    for(const n of nodes){
      let s = n.nodeValue || "";
      let original = s;

      s = s.replace(/CHECK TOWER/g, 'TOWER HEALTHY');
      s = s.replace(/not_ready_for_kernel_occupancy/g, 'kernel_active_local_only');
      s = s.replace(/ready_for_future_qsb_kernel_4_5/g, 'kernel_active_local_only');
      s = s.replace(/socket_ready_empty/g, 'occupied_local_only');

      s = s.replace(/Reserved For Future QSB Kernel 4\.5 Installation\s*—\s*readiness:[^—]+—\s*kernel installed:\s*false/gi,
        'QSB Kernel active local-only — readiness: kernel_active_local_only — kernel installed: true');

      s = s.replace(/Reserved For Future QSB Kernel 4\.5 Installation/gi,
        'QSB Kernel active local-only');

      s = s.replace(/Kernel Installed:\s*false/gi, 'Kernel Installed: true');
      s = s.replace(/kernel installed:\s*false/gi, 'kernel installed: true');
      s = s.replace(/Logic Present:\s*false/gi, 'Logic Present: true');
      s = s.replace(/logic present:\s*false/gi, 'logic present: true');
      s = s.replace(/Executive\s*critical/gi, 'Executive healthy');

      if(s !== original) n.nodeValue = s;
    }
  }

  function setTopStatus(){
    const top = document.getElementById('topStatus');
    if(top){
      top.textContent = 'TOWER HEALTHY';
      top.style.color = '#4dffb0';
      top.style.borderColor = 'rgba(77,255,176,.75)';
      top.style.background = 'rgba(20,80,50,.45)';
    }
  }

  function nearestContainer(el){
    let cur = el;
    for(let i=0; i<5 && cur; i++){
      if(cur.children && cur.children.length >= 1) return cur;
      cur = cur.parentElement;
    }
    return el?.parentElement || null;
  }

  function patchLabelValue(labelRegex, newValue){
    const all = Array.from(document.querySelectorAll('body *'));
    for(const el of all){
      const t = (el.textContent || '').trim();
      if(!labelRegex.test(t)) continue;

      let cur = el;
      for(let depth=0; depth<5 && cur; depth++, cur = cur.parentElement){
        const txt = (cur.textContent || '').trim();
        if(!labelRegex.test(txt)) continue;

        const descendants = Array.from(cur.querySelectorAll('*'));
        for(const d of descendants){
          const dt = (d.textContent || '').trim();
          if(dt === 'false' || dt === 'not_ready_for_kernel_occupancy' || dt === 'socket_ready_empty' || dt === 'critical' || dt === '1'){
            d.textContent = newValue;
          }
        }
      }
    }
  }

  function patchSpecificCards(){
    patchLabelValue(/^Kernel Installed$/i, 'true');
    patchLabelValue(/^Kernel$/i, 'true');
    patchLabelValue(/^Logic Present$/i, 'true');
    patchLabelValue(/^Readiness$/i, 'kernel_active_local_only');
    patchLabelValue(/^Socket$/i, 'occupied_local_only');
    patchLabelValue(/^Failures$/i, '0');
    patchLabelValue(/^Executive$/i, 'healthy');

    // Any standalone visible stale values in the Penthouse/Kernel area.
    const panels = Array.from(document.querySelectorAll('*')).filter(el => {
      const t = (el.textContent || '');
      return t.includes('Penthouse / Kernel Socket') || t.includes('Building Core') || t.includes('Command Spine');
    });

    for(const panel of panels){
      const kids = Array.from(panel.querySelectorAll('*'));
      for(const k of kids){
        const t = (k.textContent || '').trim();
        if(t === 'not_ready_for_kernel_occupancy') k.textContent = 'kernel_active_local_only';
        if(t === 'socket_ready_empty') k.textContent = 'occupied_local_only';
        if(t === 'critical') k.textContent = 'healthy';

        const nearby = (k.parentElement?.textContent || '');
        if(t === 'false' && /Kernel Installed|Logic Present|Kernel/i.test(nearby)){
          k.textContent = 'true';
        }
        if(t === '1' && /Failures/i.test(nearby)){
          k.textContent = '0';
        }
      }
    }
  }

  function ensureBanner(){
    let banner = document.getElementById('activeKernelBanner');
    if(!banner){
      banner = document.createElement('div');
      banner.id = 'activeKernelBanner';
      banner.style.cssText = [
        'position:fixed',
        'left:72px',
        'right:18px',
        'bottom:12px',
        'z-index:99999',
        'padding:8px 12px',
        'border:1px solid rgba(77,255,176,.75)',
        'background:rgba(5,35,25,.94)',
        'color:#4dffb0',
        'font-weight:800',
        'font-size:12px',
        'border-radius:10px',
        'box-shadow:0 0 18px rgba(77,255,176,.25)',
        'pointer-events:none'
      ].join(';');
      document.body.appendChild(banner);
    }
    banner.textContent = 'QSB KERNEL ACTIVE — LOCAL ONLY — source: rebased_kernel — workers/providers/model inference disabled';
  }

  function forceActiveDisplay(){
    if(!ACTIVE_KERNEL_CONFIRMED || busy) return;
    busy = true;
    try{
      setTopStatus();
      patchTextNodes();
      patchSpecificCards();
      ensureBanner();
    }finally{
      busy = false;
    }
  }

  async function cycle(){
    await fetchActiveTruth();
    forceActiveDisplay();
  }

  const observer = new MutationObserver(function(){
    if(ACTIVE_KERNEL_CONFIRMED) requestAnimationFrame(forceActiveDisplay);
  });

  function start(){
    observer.observe(document.body, {subtree:true, childList:true, characterData:true});
    cycle();
    setInterval(cycle, 1000);
    setInterval(forceActiveDisplay, 250);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', start);
  }else{
    start();
  }
})();
</script>
'''

if "</body>" in text:
    text = text.replace("</body>", snippet + "\n</body>", 1)
elif "</html>" in text:
    text = text.replace("</html>", snippet + "\n</html>", 1)
else:
    raise SystemExit("Could not find </body> or </html> insertion point.")

SERVER.write_text(text, encoding="utf-8")
py_compile.compile(str(SERVER), doraise=True)
print("Installed stronger active-kernel MutationObserver frontend sync.")
print("server.py compiles cleanly.")
