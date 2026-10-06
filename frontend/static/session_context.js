(function(){
  const key="f1-analysis-session-context-v1";
  function read(){try{return JSON.parse(localStorage.getItem(key)||"{}")||{}}catch{return{}}}
  function write(sessionId,trackId){const value={session_id:sessionId||null,track_id:trackId==null?null:String(trackId),updated_at:Date.now()};localStorage.setItem(key,JSON.stringify(value));return value}
  function activityLabel(session){return session.sessionActivityName||session.sessionTypeName||"Unknown session"}
  function rewindLabel(lap){const count=Number(lap.rewindCount)||0;return count>0?` · STITCHED (${count} ${count===1?"rewind":"rewinds"})`:""}
  function sessionLabel(session){
    const tracks=[...new Set((session.tracks||[]).map(track=>track.trackName||`Track ${track.trackId}`))].join(", ")||"Course unknown";
    const count=session.lapCount??(session.tracks||[]).reduce((total,track)=>total+(track.laps||[]).length,0);
    const stamp=session.id.match(/^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})_?/);
    const date=stamp?`${stamp[1]} ${stamp[2]}:${stamp[3]}:${stamp[4]}`:"Date unknown";
    const suffix=stamp?session.id.slice(stamp[0].length):session.id;
    const identity=suffix.startsWith("session-")?suffix.replace(/^session-/,"").replace(/_track--?\d+/,""):session.id;
    return `${tracks} · ${activityLabel(session)} · ${count} ${count===1?"saved lap":"saved laps"} · ${date} · ID ${identity}`;
  }
  function chooseSession(values,requested){const saved=read();return values.find(value=>value.id===requested)||values.find(value=>value.id===saved.session_id)||values[0]||null}
  function chooseTrack(session,requested){const saved=read(),tracks=session?.tracks||[];return tracks.find(track=>String(track.trackId)===String(requested))||tracks.find(track=>String(track.trackId)===saved.track_id)||tracks[0]||null}
  function mount(sessionSelect,trackSelect){
    if(!document.querySelector('link[href*="session_context.css"]')){const link=document.createElement("link");link.rel="stylesheet";link.href="/static/session_context.css";document.head.append(link)}
    const nav=document.querySelector(".page-tabs"),sessionLabelElement=sessionSelect?.closest("label");if(!nav||!sessionLabelElement)return null;
    const previousParent=sessionLabelElement.parentElement,bar=document.createElement("section");bar.className=`global-session-context${trackSelect?"":" single"}`;
    sessionLabelElement.firstChild.textContent="Session / course";bar.append(sessionLabelElement);
    const trackLabel=trackSelect?.closest("label");if(trackLabel){trackLabel.firstChild.textContent="Course";bar.append(trackLabel)}
    nav.before(bar);if(previousParent&&!previousParent.children.length)previousParent.remove();return bar;
  }
  window.SessionContext={key,read,write,activityLabel,rewindLabel,sessionLabel,chooseSession,chooseTrack,mount};
})();
