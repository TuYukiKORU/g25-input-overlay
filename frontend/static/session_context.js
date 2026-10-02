(function(){
  const key="f1-analysis-session-context-v1";
  function read(){try{return JSON.parse(localStorage.getItem(key)||"{}")||{}}catch{return{}}}
  function write(sessionId,trackId){const value={session_id:sessionId||null,track_id:trackId==null?null:String(trackId),updated_at:Date.now()};localStorage.setItem(key,JSON.stringify(value));return value}
  function sessionLabel(session){const tracks=[...new Set((session.tracks||[]).map(track=>track.trackName||`Track ${track.trackId}`))].join(", ")||"Course unknown";const mode=session.gameModeName&&session.gameModeName!=="Unknown"?session.gameModeName:session.sessionTypeName;return `${tracks} · ${session.id.replaceAll("_"," ")}${mode?` · ${mode}`:""}`}
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
  window.SessionContext={key,read,write,sessionLabel,chooseSession,chooseTrack,mount};
})();
