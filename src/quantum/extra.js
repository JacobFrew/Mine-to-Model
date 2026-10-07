/* quantum page: listings table and ETF price */
function pageRefresh(){
  const tb=document.querySelector("#listtbl tbody"); if(tb){
    tb.innerHTML=LISTINGS.map(L=>{ const s=stockOf(L.id); const px=s?s.px:(S[L.id]&&S[L.id].px);
      const ch = px? (px/L.ref-1)*100 : null;
      return `<tr class="go" data-id="${L.id}" tabindex="0"><td><b>${esc(N[L.id].n)}</b> <span class="tkc">${esc(S[L.id].tk)}</span></td><td>${esc(L.when)}</td><td>${esc(L.how)} · ${esc(L.with)}</td><td>${esc(L.val)}</td>
        <td class="r num">${fmt$(L.ref)}</td><td class="r num">${px?fmt$(px):"—"}</td><td class="r num">${ch!=null?`<span class="chg ${ch>=0?"p":"n"}">${fmtPct(ch)}</span>`:"—"}</td></tr>`; }).join("");
    tb.querySelectorAll("tr").forEach(tr=>{ const go=()=>select(tr.dataset.id,true); tr.addEventListener("click",go); tr.addEventListener("keydown",e=>{ if(e.key==="Enter"){ e.preventDefault(); go(); } }); });
  }
  const q=S.qtum; if(q && q.px>0){ const el=document.getElementById("qtumpx"); if(el) el.textContent=fmt$(q.px);
    const sub=document.getElementById("qtumsub"); if(sub) sub.textContent=`QTUM, Defiance Quantum ETF · ${q.d||""} close${q.chg1d!=null?` · ${fmtChg(q.chg1d)} that day`:""}`; }
}
