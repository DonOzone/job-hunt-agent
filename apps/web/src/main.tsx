import React, {useEffect, useMemo, useRef, useState} from "react";
import {createRoot} from "react-dom/client";
import {
  ApiClient, ApiError, validateBaseUrl, type AiSettings, type Application, type Card,
  type Dashboard, type Feedback, type Gap, type Kind, type Learning, type Match,
  type Opportunity, type Profile, type Run, type Task, type User
} from "@jobhunt/client";
import "./style.css";

const initialProfile: Profile = {
  name: "", location: "", home_country: "", roles: [], work_authorization: [],
  prefer_remote: true, cv_text: ""
};
const statuses = ["saved", "applying", "applied", "screening", "assessment", "interview", "final",
  "offer", "accepted", "rejected", "failed", "ghosted", "withdrawn", "declined", "skipped"];
const tabs = ["Dashboard", "Profile", "Opportunities", "Applications", "Learning", "Study cards", "Feedback", "LLM tasks", "Settings"];
type Preview = AiSettings & {prompt: string; notice: string; preview_digest: string};
type Draft = {cv: string; cover_letter: string; suggestions: string[]; warning: string};
function link(value: string): string | undefined {
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? value : undefined;
  } catch { return undefined; }
}
function download(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], {type: "text/plain;charset=utf-8"}));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function App() {
  const defaultUrl = window.location.port === "5173" || window.location.port === "5174"
    ? `${window.location.protocol}//${window.location.hostname}:8650` : "";
  const [baseUrl, setBaseUrl] = useState(localStorage.getItem("jobhunt-server") ?? defaultUrl);
  const api = useMemo(() => new ApiClient(baseUrl), [baseUrl]);
  const generation = useRef(0);
  const [server, setServer] = useState(baseUrl);
  const [user, setUser] = useState<User | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [register, setRegister] = useState(false);
  const [tab, setTab] = useState("Dashboard");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState<Profile>(initialProfile);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [jobs, setJobs] = useState<Opportunity[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [learning, setLearning] = useState<Learning[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [ai, setAi] = useState<AiSettings>({configured: false, provider: "", model: ""});
  const [kind, setKind] = useState<"all" | Kind>("all");
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [skill, setSkill] = useState("Python");
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [aiRequest, setAiRequest] = useState<Record<string, string>>({});
  const [consent, setConsent] = useState(false);
  const [preferAi, setPreferAi] = useState(true);
  const [boardType, setBoardType] = useState("ashby");
  const [board, setBoard] = useState("m-kopa");
  const [opportunity, setOpportunity] = useState({
    title: "", company: "", url: "", location: "", description: "", remote: true,
    opportunity_type: "job" as Kind, duration: ""
  });
  const [feedbackForm, setFeedbackForm] = useState({application_id: "", subject: "", body: ""});
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [cardResults, setCardResults] = useState<Record<string, string>>({});
  const [taskResults, setTaskResults] = useState<Record<string, string>>({});

  function clear() {
    generation.current++;
    setUser(null); setProfile(initialProfile); setDashboard(null); setJobs([]); setApplications([]);
    setLearning([]); setCards([]); setFeedback([]); setTasks([]); setRuns([]); setGaps([]);
    setMatch(null); setSelected(null); setDraft(null); setPreview(null); setCardResults({});
    setTaskResults({}); setFeedbackForm({application_id: "", subject: "", body: ""}); setKey("");
    setAi({configured: false, provider: "", model: ""}); setTab("Dashboard");
  }
  async function load() {
    const stamp = generation.current;
    const result = await Promise.all([
      api.request<Profile>("/api/profile"), api.request<Dashboard>("/api/dashboard"),
      api.request<Opportunity[]>("/api/opportunities"), api.request<Application[]>("/api/applications"),
      api.request<Learning[]>("/api/learning"), api.request<Card[]>("/api/cards"),
      api.request<Feedback[]>("/api/feedback"), api.request<Task[]>("/api/tasks"),
      api.request<Run[]>("/api/runs"), api.request<Gap[]>("/api/gaps"),
      api.request<string[]>("/api/skills"), api.request<AiSettings>("/api/ai")
    ]);
    if (stamp !== generation.current) return;
    setProfile(result[0]); setDashboard(result[1]); setJobs(result[2]); setApplications(result[3]);
    setLearning(result[4]); setCards(result[5]); setFeedback(result[6]); setTasks(result[7]);
    setRuns(result[8]); setGaps(result[9]); setSkills(result[10]); setAi(result[11]);
  }
  async function action(run: () => Promise<unknown>, message = "") {
    setError(""); setNotice(""); setBusy(true);
    try {
      await run();
      if (user) await load();
      setNotice(message);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The operation failed.");
      if (failure instanceof ApiError && failure.status === 401) clear();
    } finally { setBusy(false); }
  }
  useEffect(() => {
    let active = true;
    setRestoring(true);
    api.restore().then(found => {if (active) setUser(found);}).catch(failure => {
      if (active && !(failure instanceof ApiError && failure.status === 401)) setError(String(failure));
    }).finally(() => {if (active) setRestoring(false);});
    return () => {active = false;};
  }, [api]);
  useEffect(() => {
    if (user) load().catch(failure => setError(String(failure)));
  }, [user, api]);
  const pending = runs.some(r => ["queued", "running"].includes(r.status));
  useEffect(() => {
    if (!user || !pending) return;
    const timer = setInterval(() => load().catch(failure => setError(String(failure))), 3000);
    return () => clearInterval(timer);
  }, [user, pending, api]);

  function switchServer() {
    try {
      const value = validateBaseUrl(server);
      clear(); api.setToken(""); setBaseUrl(value);
      localStorage.setItem("jobhunt-server", value);
      setNotice("Server switched; sign in again. No token or data is forwarded to the new server.");
    } catch (failure) { setError(String(failure)); }
  }
  async function showAi(params: Record<string, string>) {
    const query = new URLSearchParams(params);
    const result = await api.request<Preview>(`/api/ai/preview?${query}`);
    setPreview(result); setAiRequest(params); setConsent(false);
  }
  async function upload(path: string, file: File, applicationId?: string) {
    const form = new FormData(); form.append("file", file);
    if (applicationId) form.append("application_id", applicationId);
    await api.upload(path, form);
  }
  if (!user) return <main className="auth">
    <div className="brand">Job Hunt <span>work + growth</span></div>
    <h1>{register ? "Create your account" : "Welcome back"}</h1>
    <p>Your jobs, projects, learning and responses in one private workspace. AI is optional.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <form onSubmit={event => {event.preventDefault(); action(async () => {
      generation.current++;
      const found = await api.login(email, password, register); setPassword(""); setUser(found);
    });}}>
      <label>Email<input required type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)}/></label>
      <label>Password<input required type="password" minLength={12} autoComplete={register ? "new-password" : "current-password"}
        value={password} onChange={e => setPassword(e.target.value)}/></label>
      <button disabled={busy || restoring}>{restoring ? "Checking session..." : register ? "Create account" : "Sign in"}</button>
    </form>
    <button className="secondary" onClick={() => setRegister(!register)}>{register ? "Already registered? Sign in" : "Create an account"}</button>
    <details><summary>Connect to a local or hosted server</summary>
      <label>API URL (blank = this server)<input value={server} onChange={e => setServer(e.target.value)}/></label>
      <button onClick={switchServer}>Switch server</button>
      <p>Use HTTPS when hosted. HTTP on a private network is for development only.</p>
    </details>
  </main>;

  return <div className="shell">
    <aside><div className="brand">Job Hunt <span>work + growth</span></div>
      <nav aria-label="Main navigation">{tabs.map(name => <button key={name} className={tab === name ? "active" : ""}
        aria-current={tab === name ? "page" : undefined} onClick={() => {setTab(name); setDraft(null);}}>{name}</button>)}</nav>
      <p className="account">{user.email}</p>
      <button className="secondary" onClick={() => action(async () => {await api.logout(); clear();})}>Sign out</button>
    </aside>
    <main><header><div><p className="eyebrow">Your next step</p><h1>{tab}</h1></div>
      <span className="badge">{ai.configured && preferAi ? `AI available: ${ai.provider}` : "Basic mode"}</span>
      <button className="secondary" disabled={busy} onClick={() => action(load)}>Refresh</button></header>
      {error && <p role="alert" className="error">{error}</p>}
      {notice && <p role="status" className="notice">{notice}</p>}
      {busy && <p role="status">Working...</p>}
      {preview && <section aria-label="Approve optional AI request" className="consent">
        <h2>Review before sending to {preview.provider}</h2><p>{preview.notice}</p>
        <details><summary>Exact data to be sent</summary><pre>{preview.prompt}</pre></details>
        <label className="check"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/>
          I approve sending this displayed data to this API provider.</label>
        <button disabled={!consent || busy} onClick={() => action(async () => {
          await api.request("/api/ai/generate", "POST", {...aiRequest, consent: true, preview_digest: preview.preview_digest});
          setPreview(null); setTab("LLM tasks");
        }, "AI draft queued. No application or email will be sent.")}>Generate draft</button>
        <button className="secondary" onClick={() => setPreview(null)}>Cancel</button>
      </section>}

      {tab === "Dashboard" && dashboard && <>
        <div className="stats">{[
          ["Opportunities", dashboard.opportunities], ["Short-term projects", dashboard.projects],
          ["Applications", dashboard.applications], ["Learning completed", `${dashboard.learning_completed}/${dashboard.learning_total}`],
          ["Quiz practice", `${dashboard.study_correct}/${dashboard.study_attempts}`],
          ["Responses to review", dashboard.feedback_unreviewed], ["LLM handoffs pending", dashboard.pending_tasks]
        ].map(([name, value]) => <section className="stat" key={name}><span>{name}</span><strong>{value}</strong></section>)}</div>
        <div className="columns"><section><h2>Application progress</h2>
          {Object.entries(dashboard.application_statuses).map(([status, count]) => <p key={status} className="row"><span>{status}</span><strong>{count}</strong></p>)}
          {!applications.length && <p>Save a job or short-term project to begin tracking.</p>}
          <button onClick={() => setTab("Applications")}>Review applications</button></section>
          <section><h2>Learning focus</h2>{learning.slice(0, 5).map(item => <p key={item.id} className="row"><span>{item.skill}</span><span>{item.status}</span></p>)}
            <button onClick={() => setTab("Learning")}>Plan next subject</button>
            <p className="muted">Quiz practice and self-ratings are not certifications or proof of production experience.</p></section></div>
        <section><h2>Recent feedback</h2>{feedback.slice(0, 3).map(item => <article key={item.id}><h3>{item.subject || "Received response"}</h3>
          <p>{item.body.slice(0, 180)}</p><span className="badge">{item.analysis ? "Review recorded" : "Needs review"}</span></article>)}
          {!feedback.length && <p>Paste or import a received response. No mailbox is connected.</p>}</section>
      </>}

      {tab === "Profile" && <section><h2>Confirm your facts</h2>
        <p>Import or paste your CV, then confirm preferences and work rights. Missing evidence is not a skill claim.</p>
        <form onSubmit={e => {e.preventDefault(); action(() => api.request("/api/profile", "PUT", profile), "Profile saved; CV version recorded.");}}>
          <div className="columns"><label>Name<input value={profile.name} onChange={e => setProfile({...profile, name: e.target.value})}/></label>
            <label>Location<input value={profile.location} onChange={e => setProfile({...profile, location: e.target.value})}/></label>
            <label>Home country<input value={profile.home_country} onChange={e => setProfile({...profile, home_country: e.target.value})}/></label>
            <label>Confirmed work authorization (comma separated)<input value={profile.work_authorization.join(", ")}
              onChange={e => setProfile({...profile, work_authorization: e.target.value.split(",").map(s => s.trim()).filter(Boolean)})}/></label></div>
          <label>Target roles (comma separated)<input value={profile.roles.join(", ")}
            onChange={e => setProfile({...profile, roles: e.target.value.split(",").map(s => s.trim()).filter(Boolean)})}/></label>
          <label className="check"><input type="checkbox" checked={profile.prefer_remote} onChange={e => setProfile({...profile, prefer_remote: e.target.checked})}/>Prefer remote opportunities</label>
          <label>Baseline CV<textarea rows={16} value={profile.cv_text} onChange={e => setProfile({...profile, cv_text: e.target.value})}/></label>
          <button disabled={busy}>Save confirmed profile</button>
        </form>
        <label>Import CV (TXT, MD, PDF, unprotected DOCX)<input type="file" accept=".txt,.md,.pdf,.docx" onChange={e => {
          const file = e.target.files?.[0]; if (file) action(() => upload("/api/cv", file), "CV imported. Review facts before saving applications.");
          e.target.value = "";
        }}/></label>
      </section>}

      {tab === "Opportunities" && <>
        <section><h2>Find jobs and short-term projects</h2><div className="row">
          <label>Opportunity type<select value={kind} onChange={e => setKind(e.target.value as "all" | Kind)}>
            <option value="all">Jobs and projects</option><option value="job">Jobs</option><option value="project">Short-term projects</option></select></label>
          <label>Official source<select value={boardType} onChange={e => setBoardType(e.target.value)}>
            {["ashby", "greenhouse", "lever", "remoteok", "remotive"].map(s => <option key={s}>{s}</option>)}</select></label>
          <label>Board identifier<input value={board} onChange={e => setBoard(e.target.value)} placeholder="m-kopa"/></label>
          <button disabled={busy} onClick={() => action(() => api.request("/api/search", "POST", {
            kind, sites: [{type: boardType, ...(boardType === "remoteok" || boardType === "remotive" ? {} : {company: board})}]
          }), "Search queued; results will appear after the worker finishes.")}>Search</button>
        </div><p className="muted">Official feeds are cached. Do not scrape LinkedIn, Indeed or Glassdoor; paste permitted descriptions instead.</p></section>
        <details className="panel"><summary>Add a job or short-term project you found</summary>
          <form onSubmit={e => {e.preventDefault(); action(async () => {
            await api.request("/api/opportunities", "POST", opportunity);
            setOpportunity({...opportunity, title: "", company: "", description: "", url: ""});
          }, "Opportunity saved.");}}>
            <div className="columns"><label>Title<input required value={opportunity.title} onChange={e => setOpportunity({...opportunity, title: e.target.value})}/></label>
              <label>Company/client<input required value={opportunity.company} onChange={e => setOpportunity({...opportunity, company: e.target.value})}/></label>
              <label>Posting link<input type="url" value={opportunity.url} onChange={e => setOpportunity({...opportunity, url: e.target.value})}/></label>
              <label>Location<input value={opportunity.location} onChange={e => setOpportunity({...opportunity, location: e.target.value})}/></label>
              <label>Type<select value={opportunity.opportunity_type} onChange={e => setOpportunity({...opportunity, opportunity_type: e.target.value as Kind})}>
                <option value="job">Job</option><option value="project">Short-term project</option></select></label>
              <label>Confirmed duration<input value={opportunity.duration} onChange={e => setOpportunity({...opportunity, duration: e.target.value})} placeholder="Unknown or e.g. 3 months"/></label></div>
            <label className="check"><input type="checkbox" checked={opportunity.remote} onChange={e => setOpportunity({...opportunity, remote: e.target.checked})}/>Posting states remote</label>
            <label>Posting description<textarea rows={6} value={opportunity.description} onChange={e => setOpportunity({...opportunity, description: e.target.value})}/></label>
            <button disabled={busy}>Save opportunity</button></form>
        </details>
        <section><p className="muted">Keyword scores are not hiring probabilities. Verify country eligibility and requirements yourself.</p>
          {jobs.filter(j => kind === "all" || j.opportunity_type === kind).map(job => <article key={job.id}>
            <div className="row"><div><h3>{job.title}</h3><p>{job.company} · {job.location} · {job.opportunity_type} {job.duration}</p></div>
              <span className="badge">{Math.round((job.match_score ?? 0) * 100)}% keyword overlap</span></div>
            <div className="row">{link(job.url) && <a href={link(job.url)} target="_blank" rel="noopener noreferrer">Official posting</a>}
              <button onClick={() => action(async () => {setSelected(job); setMatch(await api.request<Match>(`/api/opportunities/${job.id}/match`));})}>Review match</button>
              <button className="secondary" onClick={() => action(() => api.request("/api/applications", "POST", {opportunity_id: job.id}),
                "Saved for tracking; not submitted.")}>Track application/proposal</button>
              {ai.configured && preferAi && <button className="secondary" onClick={() => action(() => showAi({kind: "match", opportunity_id: job.id}))}>AI match review</button>}</div>
          </article>)}
          {!jobs.length && <p>Search a source or add a posting to see matches.</p>}
        </section>
        {selected && match && <section><h2>{selected.title}: evidence and gates</h2><pre>{match.report}</pre></section>}
      </>}

      {tab === "Applications" && <section><h2>Jobs and project proposals</h2><p>Statuses are recorded manually. This platform never submits applications or sends messages.</p>
        {applications.map(item => <article key={item.id}><h3>{item.title}</h3><p>{item.company} · {item.opportunity_type}</p>
          <label>Status<select value={item.status} onChange={e => action(() => api.request(`/api/applications/${item.id}`, "PATCH",
            {status: e.target.value, next_action: item.next_action}), "Status recorded.")}>{statuses.map(s => <option key={s}>{s}</option>)}</select></label>
          <label>Next action<input defaultValue={item.next_action} key={`${item.id}-${item.updated_at}`} onBlur={e => {
            if (e.target.value !== item.next_action) action(() => api.request(`/api/applications/${item.id}`, "PATCH",
              {status: item.status, next_action: e.target.value}));
          }}/></label>
          <button onClick={() => action(async () => setDraft(await api.request<Draft>(`/api/applications/${item.id}/draft`)))}>Basic draft and evidence tips</button>
          {ai.configured && preferAi && <button className="secondary" onClick={() => action(() => showAi({kind: "draft", opportunity_id: item.opportunity_id}))}>AI draft review</button>}
        </article>)}
        {!applications.length && <p>Track an opportunity to start an application or short-term project proposal.</p>}
        {draft && <section><h2>Reviewable draft</h2><p className="warning">{draft.warning}</p>
          <ul>{draft.suggestions.map(tip => <li key={tip}>{tip}</li>)}</ul>
          <label>Editable CV draft<textarea rows={10} value={draft.cv} onChange={e => setDraft({...draft, cv: e.target.value})}/></label>
          <button onClick={() => download("cv-draft.txt", draft.cv)}>Download TXT draft</button>
          <label>Editable cover letter/proposal<textarea rows={10} value={draft.cover_letter} onChange={e => setDraft({...draft, cover_letter: e.target.value})}/></label>
          <button onClick={() => download("cover-letter-draft.txt", draft.cover_letter)}>Download TXT draft</button>
        </section>}
      </section>}

      {tab === "Learning" && <>
        <section><h2>Ramp-up plan</h2><form className="row" onSubmit={e => {e.preventDefault(); action(() => api.request("/api/learning", "POST", {skill}), "Subject added.");}}>
          <label>Subject<input list="skills" value={skill} required onChange={e => setSkill(e.target.value)}/></label>
          <datalist id="skills">{skills.map(s => <option key={s}>{s}</option>)}</datalist><button disabled={busy}>Add learning goal</button></form>
          {learning.map(item => <article key={item.id}><h3>{item.skill}</h3>
            <label>Progress<select value={item.status} onChange={e => action(() => api.request(`/api/learning/${item.id}`, "PATCH",
              {status: e.target.value, hours: item.hours, evidence: item.evidence}))}>
              <option value="planned">Planned</option><option value="learning">Learning</option><option value="completed">Completed</option></select></label>
            <label>Hours studied<input type="number" min="0" defaultValue={item.hours} onBlur={e => action(() => api.request(`/api/learning/${item.id}`, "PATCH",
              {status: item.status, hours: Number(e.target.value), evidence: item.evidence}))}/></label>
            <label>Evidence / notes<textarea rows={2} defaultValue={item.evidence} onBlur={e => action(() => api.request(`/api/learning/${item.id}`, "PATCH",
              {status: item.status, hours: item.hours, evidence: e.target.value}))}/></label>
            <ul>{item.resources.map(resource => <li key={resource.url}>{link(resource.url) && <a href={link(resource.url)} target="_blank" rel="noopener noreferrer">{resource.name}</a>}
              {" "}{resource.provider} · {resource.type}</li>)}</ul>
            <button onClick={() => action(async () => {await api.request("/api/cards", "POST", {skill: item.skill}); setTab("Study cards");})}>Practice this subject</button>
          </article>)}
          <p className="muted">Completion is your own record. It does not automatically change your CV or certify proficiency.</p></section>
        <section><h2>Potential gaps from saved opportunities</h2>{gaps.map(g => <p className="row" key={g.skill}>
          <span>{g.skill} · mentioned in {g.jobs} opportunities</span><button className="secondary" onClick={() => action(() => api.request("/api/learning", "POST", {skill: g.skill}))}>Add to plan</button></p>)}
          <p className="muted">These are taxonomy/evidence gaps, not proof that you lack a skill.</p></section>
      </>}

      {tab === "Study cards" && <section><h2>Practice and check understanding</h2>
        <form className="row" onSubmit={e => {e.preventDefault(); action(() => api.request("/api/cards", "POST", {skill}));}}>
          <label>Subject<input value={skill} onChange={e => setSkill(e.target.value)} required/></label><button disabled={busy}>Create practice deck</button>
          {ai.configured && preferAi && <button type="button" className="secondary" onClick={() => action(() => showAi({kind: "study", skill}))}>Suggest cards with AI</button>}
        </form>
        {cards.map(card => <article key={card.id}><p className="eyebrow">{card.topic} · {card.kind}</p><h3>{card.front}</h3>
          {card.options.length ? <fieldset><legend>Choose an answer</legend>{card.options.map((option, i) => <label className="check" key={option}>
            <input type="radio" name={card.id} value={String.fromCharCode(97 + i)} checked={answers[card.id] === String.fromCharCode(97 + i)}
              onChange={e => setAnswers({...answers, [card.id]: e.target.value})}/>{option}</label>)}</fieldset> :
            <label>Self-rating<select value={answers[card.id] ?? ""} onChange={e => setAnswers({...answers, [card.id]: e.target.value})}>
              <option value="">Choose...</option><option value="know">I know</option><option value="dont-know">I don't know</option></select></label>}
          <button disabled={!answers[card.id] || busy} onClick={() => action(async () => {
            const answer = await api.request<{correct: boolean | null; back: string}>(`/api/cards/${card.id}/answer`, "POST", {answer: answers[card.id]});
            setCardResults({...cardResults, [card.id]: `${answer.correct === null ? "Self-rating recorded" : answer.correct ? "Correct" : "Review needed"}: ${answer.back}`);
          })}>Check and record</button>
          <button className="secondary" onClick={() => action(async () => {
            const result = await api.request<{back: string}>(`/api/cards/${card.id}/reveal`, "POST");
            setCardResults({...cardResults, [card.id]: result.back});
          })}>Reveal explanation</button>
          {cardResults[card.id] && <p role="status" className="notice">{cardResults[card.id]}</p>}
        </article>)}
      </section>}

      {tab === "Feedback" && <section><h2>Received email or response</h2><p>Paste or import only the response you want reviewed. No mailbox access, sending or automatic status changes.</p>
        <form onSubmit={e => {e.preventDefault(); action(async () => {
          await api.request("/api/feedback", "POST", feedbackForm);
          setFeedbackForm({...feedbackForm, subject: "", body: ""});
        }, "Response saved privately.");}}>
          <label>Application/project<select required value={feedbackForm.application_id} onChange={e => setFeedbackForm({...feedbackForm, application_id: e.target.value})}>
            <option value="">Choose...</option>{applications.map(a => <option value={a.id} key={a.id}>{a.company} - {a.title}</option>)}</select></label>
          <label>Subject<input value={feedbackForm.subject} onChange={e => setFeedbackForm({...feedbackForm, subject: e.target.value})}/></label>
          <label>Received response<textarea required rows={6} value={feedbackForm.body} onChange={e => setFeedbackForm({...feedbackForm, body: e.target.value})}/></label>
          <button disabled={busy}>Save response</button></form>
        <label>Import EML/TXT for the selected application<input type="file" accept=".eml,.txt" disabled={!feedbackForm.application_id} onChange={e => {
          const file = e.target.files?.[0]; if (file) action(() => upload("/api/feedback/import", file, feedbackForm.application_id), "Response imported.");
          e.target.value = "";
        }}/></label>
        {feedback.map(item => <article key={item.id}><h3>{item.subject || "Received response"}</h3><pre>{item.body}</pre>
          <button onClick={() => action(async () => {await api.request("/api/tasks", "POST", {feedback_id: item.id}); setTab("LLM tasks");},
            "Manual handoff created. Review the data before copying it to your authorized assistant.")}>Ask my logged-in LLM to review</button>
          {ai.configured && preferAi && <button className="secondary" onClick={() => action(() => showAi({kind: "feedback", feedback_id: item.id}))}>Review via connected API</button>}
          {item.analysis && <details><summary>Recorded review</summary><pre>{item.analysis}</pre></details>}
        </article>)}
      </section>}

      {tab === "LLM tasks" && <>
        <section><h2>Authorized assistant handoffs</h2><p>Use your official logged-in assistant yourself. This app does not take its subscription credentials.</p>
          {tasks.map(task => <article key={task.id}><h3>{task.title}</h3><span className="badge">{task.status}</span>
            <details><summary>Review exact handoff content</summary><pre>{task.prompt}</pre></details>
            <button onClick={() => action(() => navigator.clipboard.writeText(task.prompt), "Prompt copied. Share only with an assistant you authorize.")}>Copy reviewed prompt</button>
            <label>Paste the assistant's reviewed result<textarea rows={5} value={taskResults[task.id] ?? task.result}
              onChange={e => setTaskResults({...taskResults, [task.id]: e.target.value})}/></label>
            <button disabled={busy || !(taskResults[task.id] ?? task.result).trim()} onClick={() => action(() => api.request(`/api/tasks/${task.id}`, "PATCH",
              {result: taskResults[task.id] ?? task.result, status: "completed"}), "Review recorded; no status change or reply was sent.")}>Record completed review</button>
          </article>)}
        </section>
        <section><h2>Search and API AI runs</h2>{runs.map(run => <article key={run.id}><h3>{run.kind} · {run.status}</h3>
          <p>{run.created_at}</p>{run.error && <p role="alert" className="error">{run.error}</p>}
          {run.result && <pre>{run.result}</pre>}</article>)}</section>
      </>}

      {tab === "Settings" && <section><h2>Optional AI connection</h2>
        <p>API credentials are encrypted on your server. API billing is separate from ChatGPT/Claude/Gemini subscription login. No provider key is returned to this UI.</p>
        <p>{ai.configured ? `Connected: ${ai.provider}, ${ai.model}` : "No AI connection; the basic platform is available."}</p>
        <label className="check"><input type="checkbox" checked={preferAi} onChange={e => setPreferAi(e.target.checked)}/>Prefer AI-assisted actions when configured (each request still needs approval)</label>
        <form onSubmit={e => {e.preventDefault(); action(async () => {
          await api.request("/api/ai", "PUT", {provider, model, api_key: key}); setKey(""); setPreview(null);
        }, "Connection saved. No model request has been made.");}}>
          <label>Provider<select value={provider} onChange={e => setProvider(e.target.value)}>
            {["openai", "anthropic", "gemini"].map(p => <option key={p}>{p}</option>)}</select></label>
          <label>Model ID enabled in your account<input required value={model} onChange={e => setModel(e.target.value)}/></label>
          <label>API key<input required type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)}/></label>
          <button disabled={busy}>Save encrypted connection</button>
        </form>
        {ai.configured && <button className="secondary" onClick={() => action(async () => {await api.request("/api/ai", "DELETE"); setPreview(null);},
          "Disconnected; queued requests using this connection will fail rather than switch providers.")}>Disconnect AI</button>}
        <h2>App server</h2><label>API URL (blank = this server)<input value={server} onChange={e => setServer(e.target.value)}/></label>
        <button onClick={switchServer}>Switch server and sign in again</button>
        <p className="muted">Current hosted pilot uses single-host persistent storage. Keep backups and enable HTTPS before public use.</p>
      </section>}
    </main>
  </div>;
}

createRoot(document.getElementById("root")!).render(<App/>);
