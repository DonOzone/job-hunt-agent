import React, { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Linking, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import * as SecureStore from "expo-secure-store";
import * as Clipboard from "expo-clipboard";
import {
  ApiClient, AiSettings, Application, Card, Dashboard, Feedback, Learning,
  Match, Opportunity, Profile, Run, Task, User, validateBaseUrl
} from "@jobhunt/client";

const statuses = ["saved", "applying", "applied", "screening", "assessment", "interview", "final",
  "offer", "accepted", "rejected", "failed", "ghosted", "withdrawn", "declined", "skipped"];
const tabs = ["Dashboard", "Opportunities", "Applications", "Learning", "Tasks", "Settings"] as const;
type Tab = typeof tabs[number];
const emptyProfile: Profile = {
  name: "", location: "", home_country: "", work_authorization: [], roles: [],
  prefer_remote: true, cv_text: ""
};
const message = (error: unknown) => error instanceof Error ? error.message : String(error);

function Field({ label, value, set, secret = false, multiline = false }: {
  label: string; value: string; set: (value: string) => void; secret?: boolean; multiline?: boolean
}) {
  return <View style={styles.field}><Text>{label}</Text><TextInput
    accessibilityLabel={label} value={value} onChangeText={set} secureTextEntry={secret}
    multiline={multiline} autoCapitalize="none" autoCorrect={false}
    style={[styles.input, multiline && styles.multiline]} /></View>;
}
function Panel({ children }: { children: React.ReactNode }) {
  return <View style={styles.panel}>{children}</View>;
}
function Choices({ values, selected, choose }: {
  values: readonly string[]; selected: string; choose: (value: string) => void
}) {
  return <View style={styles.row}>{values.map(value => <Button key={value}
    title={selected === value ? `✓ ${value}` : value} onPress={() => choose(value)} />)}</View>;
}

export default function App() {
  const [server, setServer] = useState("http://127.0.0.1:8650");
  const [activeServer, setActiveServer] = useState("http://127.0.0.1:8650");
  const api = useMemo(() => new ApiClient(activeServer), [activeServer]);
  const [user, setUser] = useState<User | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tab, setTab] = useState<Tab>("Dashboard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [learning, setLearning] = useState<Learning[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [kind, setKind] = useState("all");
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [duration, setDuration] = useState("");
  const [addKind, setAddKind] = useState("job");
  const [source, setSource] = useState("remotive");
  const [sourceCompany, setSourceCompany] = useState("");
  const [selectedApp, setSelectedApp] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [nextActions, setNextActions] = useState<Record<string, string>>({});
  const [skill, setSkill] = useState("");
  const [cardAnswers, setCardAnswers] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, string>>({});
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [report, setReport] = useState("");
  const [studyHours, setStudyHours] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [aiPreview, setAiPreview] = useState<{
    prompt: string; notice: string; preview_digest: string; provider: string; model: string;
    configured: boolean; kind: "feedback" | "study"; selector: { feedback_id: string } | { skill: string };
  } | null>(null);
  const sessionGeneration = useRef(0);

  async function refresh(client = api) {
    const generation = sessionGeneration.current;
    const values = await Promise.all([
      client.request<Dashboard>("/api/dashboard"),
      client.request<Opportunity[]>(`/api/opportunities?kind=${kind}`),
      client.request<Application[]>("/api/applications"),
      client.request<Feedback[]>("/api/feedback"),
      client.request<Learning[]>("/api/learning"),
      client.request<Card[]>("/api/cards"),
      client.request<Task[]>("/api/tasks"),
      client.request<Run[]>("/api/runs"),
      client.request<AiSettings>("/api/ai"),
      client.request<Profile>("/api/profile")
    ] as const);
    if (generation !== sessionGeneration.current) return;
    setDashboard(values[0]); setOpportunities(values[1]); setApplications(values[2]);
    setFeedback(values[3]); setLearning(values[4]); setCards(values[5]);
    setTasks(values[6]); setRuns(values[7]); setAi(values[8]); setProfile(values[9]);
  }
  function clearPrivateState() {
    sessionGeneration.current += 1;
    api.setToken(""); setUser(null); setPassword("");
    setDashboard(null); setOpportunities([]); setApplications([]); setFeedback([]);
    setLearning([]); setCards([]); setTasks([]); setRuns([]); setAi(null);
    setProfile(emptyProfile); setReport(""); setResults({}); setRevealed({});
    setBody(""); setSubject(""); setApiKey(""); setSelectedApp(""); setDescription("");
    setNextActions({}); setCardAnswers({}); setStudyHours({}); setEvidence({});
    setTitle(""); setCompany(""); setUrl(""); setDuration(""); setSkill(""); setAiPreview(null);
  }
  async function perform(action: () => Promise<unknown>, reload = true) {
    if (busy) return;
    setBusy(true); setError("");
    try { await action(); if (reload && user) await refresh(); }
    catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    let cancelled = false;
    const generation = sessionGeneration.current;
    void (async () => {
      try {
        const stored = await SecureStore.getItemAsync("jobhunt-session");
        if (!stored || cancelled || generation !== sessionGeneration.current) return;
        const session = JSON.parse(stored) as { server: string; token: string };
        const client = new ApiClient(session.server);
        client.setToken(session.token);
        const restored = await client.restore();
        if (cancelled || generation !== sessionGeneration.current) return;
        setServer(client.baseUrl); setActiveServer(client.baseUrl); setUser(restored);
        api.setToken(session.token);
      } catch (e) {
        if (cancelled || generation !== sessionGeneration.current) return;
        await SecureStore.deleteItemAsync("jobhunt-session");
        if (!cancelled) setError(message(e));
      }
    })();
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    void (async () => {
      try {
        const saved = await SecureStore.getItemAsync("jobhunt-session");
        if (saved) {
          const session = JSON.parse(saved) as { server: string; token: string };
          if (session.server === activeServer) api.setToken(session.token);
        }
        if (!cancelled) await refresh();
      } catch (e) { if (!cancelled) setError(message(e)); }
    })();
    return () => { cancelled = true; };
  }, [user, api, kind]);
  useEffect(() => {
    if (!user || !runs.some(run => run.status === "queued" || run.status === "running")) return;
    const timer = setInterval(() => {
      void refresh().catch(e => setError(message(e)));
    }, 4000);
    return () => clearInterval(timer);
  }, [user, runs, api, kind]);

  async function switchServer() {
    const base = validateBaseUrl(server);
    if (!base) throw new Error("Enter a server URL.");
    await SecureStore.deleteItemAsync("jobhunt-session");
    try { if (user) await api.logout(); } finally {
      clearPrivateState(); setActiveServer(base); setServer(base);
    }
  }
  async function login(register: boolean) {
    if (server.replace(/\/$/, "") !== activeServer) {
      throw new Error("Apply the server address before signing in.");
    }
    sessionGeneration.current += 1;
    const session = await api.request<{ user: User; token: string }>(
      `/api/auth/${register ? "register" : "login"}`, "POST", { email, password });
    await SecureStore.setItemAsync("jobhunt-session", JSON.stringify({
      server: activeServer, token: session.token
    }));
    api.setToken(session.token); setUser(session.user); setPassword("");
  }
  function generate(kind: "feedback" | "study", id: string) {
    void perform(async () => {
      const selector = kind === "feedback" ? { feedback_id: id } : { skill: id };
      const query = `kind=${kind}&${kind === "feedback" ? "feedback_id" : "skill"}=${encodeURIComponent(id)}`;
      const preview = await api.request<{
        prompt: string; notice: string; preview_digest: string; provider: string;
        model: string; configured: boolean
      }>(`/api/ai/preview?${query}`);
      if (!preview.configured) throw new Error("Connect an optional API provider in Settings first.");
      setAiPreview({ ...preview, kind, selector });
    }, false);
  }
  return <SafeAreaProvider><SafeAreaView style={styles.safe}><ScrollView
    contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
    <Text style={styles.heading}>Job Hunt</Text>
    <Text>Private planning, learning and application tracking. No automatic submissions or mailbox access.</Text>
    {error !== "" && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    {busy && <Text>Working…</Text>}
    {user && aiPreview && <Panel>
      <Text style={styles.title}>Exact outbound API data</Text>
      <Text>{aiPreview.provider} / {aiPreview.model}</Text><Text>{aiPreview.notice}</Text>
      <Text selectable>{aiPreview.prompt}</Text>
      <Button title="Cancel external request" onPress={() => setAiPreview(null)} />
      <Button title="I approve sending this exact prompt" disabled={busy} onPress={() => void perform(async () => {
        await api.request("/api/ai/generate", "POST", {
          kind: aiPreview.kind, ...aiPreview.selector,
          consent: true, preview_digest: aiPreview.preview_digest
        });
        setAiPreview(null); setTab("Tasks");
      })} />
    </Panel>}
    {!user ? <Panel>
      <Text style={styles.title}>Connect to your backend</Text>
      <Text>On a phone, use your computer's trusted LAN IP or an HTTPS server, not the phone's loopback address.</Text>
      <Field label="Server URL" value={server} set={setServer} />
      <Button title="Apply server (clears session)" disabled={busy} onPress={() => void perform(switchServer, false)} />
      <Field label="Email" value={email} set={setEmail} />
      <Field label="Password (at least 12 characters)" value={password} set={setPassword} secret />
      <Button title="Sign in" disabled={busy} onPress={() => void perform(() => login(false), false)} />
      <Button title="Create account" disabled={busy} onPress={() => void perform(() => login(true), false)} />
    </Panel> : <>
      <Text>{user.email} · {activeServer}</Text>
      <Choices values={tabs} selected={tab} choose={value => setTab(value as Tab)} />
      <Button title="Refresh" disabled={busy} onPress={() => void perform(async () => {}, true)} />
      {tab === "Dashboard" && <Panel>
        <Text style={styles.title}>Your progress</Text>
        {dashboard && Object.entries(dashboard).map(([key, value]) =>
          <Text key={key}>{key.replace(/_/g, " ")}: {typeof value === "object" ? JSON.stringify(value) : value}</Text>)}
      </Panel>}
      {tab === "Opportunities" && <>
        <Choices values={["all", "job", "project"]} selected={kind} choose={setKind} />
        <Panel><Text style={styles.title}>Find public opportunities</Text>
          <Choices values={["remotive", "remoteok", "ashby", "greenhouse", "lever"]} selected={source} choose={setSource} />
          <Field label="Company board ID (required for company sources)" value={sourceCompany} set={setSourceCompany} />
          <Button title="Start search" disabled={busy} onPress={() => void perform(async () => {
            if (["ashby", "greenhouse", "lever"].includes(source) && !sourceCompany.trim())
              throw new Error("Enter the official company board ID.");
            await api.request("/api/search", "POST", {
              sites: [{ type: source, ...(sourceCompany ? { company: sourceCompany } : {}) }], kind
            });
          })} />
        </Panel>
        <Panel><Text style={styles.title}>Paste a job or short-term project</Text>
          <Field label="Title" value={title} set={setTitle} />
          <Field label="Company" value={company} set={setCompany} />
          <Field label="Official posting URL" value={url} set={setUrl} />
          <Field label="Description (paste posting)" value={description} set={setDescription} multiline />
          <Choices values={["job", "project"]} selected={addKind} choose={setAddKind} />
          <Field label="Duration (projects)" value={duration} set={setDuration} />
          <Button title="Save opportunity" disabled={busy} onPress={() => void perform(async () => {
            await api.request("/api/opportunities", "POST", {
              title, company, url, description, duration, opportunity_type: addKind,
              location: "", remote: true
            });
            setTitle(""); setDescription("");
          })} />
        </Panel>
        {opportunities.map(o => <Panel key={o.id}>
          <Text style={styles.title}>{o.title} · {o.company}</Text>
          <Text>{o.opportunity_type} · {o.location} · {o.duration}</Text>
          <Text>{o.description}</Text>
          <Button title="Track application" disabled={busy} onPress={() => void perform(async () => {
            const a = await api.request<Application>("/api/applications", "POST", { opportunity_id: o.id });
            setSelectedApp(a.id); setTab("Applications");
          })} />
          <Button title="Check CV fit" disabled={busy} onPress={() => void perform(async () => {
            const match = await api.request<Match>(`/api/opportunities/${o.id}/match`);
            setReport(match.report);
          })} />
        </Panel>)}
        {report && <Panel><Text selectable>{report}</Text></Panel>}
      </>}
      {tab === "Applications" && <>
        {applications.map(a => <Panel key={a.id}>
          <Text style={styles.title}>{a.title} · {a.company} ({a.opportunity_type})</Text>
          <Choices values={statuses} selected={a.status} choose={status => {
            void perform(() => api.request(`/api/applications/${a.id}`, "PATCH", { status }));
          }} />
          <Field label="Next action" value={nextActions[a.id] ?? a.next_action}
            set={value => setNextActions({ ...nextActions, [a.id]: value })} />
          <Button title="Save next action" disabled={busy} onPress={() => void perform(() =>
            api.request(`/api/applications/${a.id}`, "PATCH", { next_action: nextActions[a.id] ?? a.next_action }))} />
          <Button title="Record received feedback for this application" onPress={() => setSelectedApp(a.id)} />
          <Button title="View application drafts (review before use)" disabled={busy} onPress={() => void perform(async () => {
            const draft = await api.request<{ cv: string; cover_letter: string; warning: string }>(
              `/api/applications/${a.id}/draft`);
            setReport(`${draft.warning}\n\n${draft.cv}\n\n${draft.cover_letter}`);
          })} />
        </Panel>)}
        {report && <Panel><Text selectable>{report}</Text></Panel>}
        <Panel><Text style={styles.title}>Received feedback (paste only)</Text>
          <Text>Selected: {applications.find(a => a.id === selectedApp)?.title ?? "Choose an application above"}</Text>
          <Field label="Subject" value={subject} set={setSubject} />
          <Field label="Received email body" value={body} set={setBody} multiline />
          <Button title="Save feedback" disabled={busy || !selectedApp} onPress={() => void perform(async () => {
            await api.request("/api/feedback", "POST", { application_id: selectedApp, subject, body });
            setSubject(""); setBody("");
          })} />
        </Panel>
        {feedback.map(f => <Panel key={f.id}>
          <Text style={styles.title}>{f.subject}</Text><Text>{f.body}</Text><Text>{f.analysis}</Text>
          <Button title="Create manual assistant handoff" disabled={busy} onPress={() => void perform(async () => {
            await api.request("/api/tasks", "POST", { feedback_id: f.id }); setTab("Tasks");
          })} />
          {ai?.configured && <Button title="Review data for optional API analysis"
            onPress={() => generate("feedback", f.id)} />}
        </Panel>)}
      </>}
      {tab === "Learning" && <>
        <Panel><Field label="Skill to learn" value={skill} set={setSkill} />
          <Button title="Add learning goal" disabled={busy} onPress={() => void perform(() =>
            api.request("/api/learning", "POST", { skill }))} />
          <Button title="Generate local study cards" disabled={busy} onPress={() => void perform(() =>
            api.request("/api/cards", "POST", { skill }))} />
        </Panel>
        {learning.map(l => <Panel key={l.id}><Text style={styles.title}>{l.skill}</Text>
          <Field label="Hours" value={studyHours[l.id] ?? String(l.hours)}
            set={value => setStudyHours({ ...studyHours, [l.id]: value })} />
          <Field label="Evidence / notes" value={evidence[l.id] ?? l.evidence}
            set={value => setEvidence({ ...evidence, [l.id]: value })} multiline />
          <Choices values={["planned", "learning", "completed"]} selected={l.status} choose={status => {
            void perform(async () => {
              const hours = Number(studyHours[l.id] ?? l.hours);
              if (!Number.isFinite(hours) || hours < 0) throw new Error("Hours must be a non-negative number.");
              await api.request(`/api/learning/${l.id}`, "PATCH", {
                status, hours, evidence: evidence[l.id] ?? l.evidence
              });
            });
          }} />
          {l.resources.map((r, i) => <Button key={i} title={r.name} onPress={() => {
            void perform(async () => {
              const link = new URL(r.url);
              if (!["http:", "https:"].includes(link.protocol) || link.username || link.password)
                throw new Error("Only public HTTP(S) resource links are allowed.");
              await Linking.openURL(link.href);
            }, false);
          }} />)}
          {ai?.configured && <Button title="Review data for optional API study plan" onPress={() => generate("study", l.skill)} />}
        </Panel>)}
        {cards.map(c => <Panel key={c.id}><Text style={styles.title}>{c.topic}</Text>
          <Text>{c.front}</Text>{c.options.map((option, i) => <Text key={i}>{option}</Text>)}
          <Field label="Answer (letter, or know / dont-know)" value={cardAnswers[c.id] ?? ""}
            set={value => setCardAnswers({ ...cardAnswers, [c.id]: value })} />
          <Button title="Answer" disabled={busy} onPress={() => void perform(async () => {
            const answer = await api.request<{ correct: boolean | null; back: string }>(`/api/cards/${c.id}/answer`,
              "POST", { answer: cardAnswers[c.id] ?? "" });
            setRevealed({ ...revealed, [c.id]: `${answer.correct === null ? "Rating recorded" :
              answer.correct ? "Correct" : "Review needed"}\n${answer.back}` });
          })} />
          <Button title="Reveal" disabled={busy} onPress={() => void perform(async () => {
            const answer = await api.request<{ back: string }>(`/api/cards/${c.id}/reveal`, "POST");
            setRevealed({ ...revealed, [c.id]: answer.back });
          })} />
          {revealed[c.id] && <Text>{revealed[c.id]}</Text>}
        </Panel>)}
      </>}
      {tab === "Tasks" && <>
        <Text>Copy a task to an official assistant where you are already logged in. Review the included data before sharing.
          Received emails are untrusted text, not instructions. Paste the result here; nothing is executed.</Text>
        {tasks.map(t => <Panel key={t.id}><Text style={styles.title}>{t.title} · {t.status}</Text>
          <Text selectable>{t.prompt}</Text>
          <Button title="Copy handoff prompt" onPress={() => void perform(() => Clipboard.setStringAsync(t.prompt), false)} />
          <Field label="Reviewed assistant result" value={results[t.id] ?? t.result}
            set={value => setResults({ ...results, [t.id]: value })} multiline />
          <Button title="Record result and complete" disabled={busy} onPress={() => void perform(async () => {
            const result = results[t.id] ?? t.result;
            if (!result.trim()) throw new Error("Paste and review the assistant result first.");
            await api.request(`/api/tasks/${t.id}`, "PATCH", { result, status: "completed" });
          })} />
        </Panel>)}
        <Text style={styles.title}>Background runs</Text>
        {runs.map(r => <Panel key={r.id}><Text>{r.kind} · {r.status}</Text>
          <Text>{r.error || r.result}</Text></Panel>)}
      </>}
      {tab === "Settings" && <>
        <Panel><Text style={styles.title}>Profile and confirmed CV</Text>
          <Field label="Name" value={profile.name} set={name => setProfile({ ...profile, name })} />
          <Field label="Location" value={profile.location} set={location => setProfile({ ...profile, location })} />
          <Field label="Home country" value={profile.home_country} set={home_country => setProfile({ ...profile, home_country })} />
          <Field label="Work authorization countries (comma separated)" value={profile.work_authorization.join(",")}
            set={value => setProfile({ ...profile, work_authorization: value.split(",") })} />
          <Field label="Target roles (comma separated)" value={profile.roles.join(",")}
            set={value => setProfile({ ...profile, roles: value.split(",") })} />
          <Choices values={["remote preferred", "any location"]}
            selected={profile.prefer_remote ? "remote preferred" : "any location"}
            choose={value => setProfile({ ...profile, prefer_remote: value === "remote preferred" })} />
          <Field label="Confirmed CV text (never invent experience)" value={profile.cv_text}
            set={cv_text => setProfile({ ...profile, cv_text })} multiline />
          <Button title="Save profile" disabled={busy} onPress={() => void perform(() =>
            api.request("/api/profile", "PUT", { ...profile,
              roles: profile.roles.map(v => v.trim()).filter(Boolean),
              work_authorization: profile.work_authorization.map(v => v.trim()).filter(Boolean) }))} />
        </Panel>
        <Panel><Text style={styles.title}>Optional AI API</Text>
          <Text>{ai?.configured ? `Connected: ${ai.provider} / ${ai.model}` : "Disconnected. Manual assistant handoff needs no API key."}</Text>
          <Text>Your API key is sent to your backend for encrypted storage. Generation always requires a separate data confirmation.</Text>
          <Choices values={["openai", "anthropic", "gemini"]} selected={provider} choose={setProvider} />
          <Field label="Model ID" value={model} set={setModel} />
          <Field label="API key" value={apiKey} set={setApiKey} secret />
          <Button title="Send key to my backend and connect" disabled={busy} onPress={() => {
            Alert.alert("Store API key?", `Send this ${provider} key to ${activeServer}? No generation runs automatically.`,
              [{ text: "Cancel", style: "cancel" }, { text: "Connect", onPress: () => void perform(async () => {
                await api.request("/api/ai", "PUT", { provider, model, api_key: apiKey }); setApiKey("");
              }) }]);
          }} />
          <Button title="Disconnect API" disabled={busy} onPress={() => void perform(() => api.request("/api/ai", "DELETE"))} />
        </Panel>
        <Panel><Field label="Server URL" value={server} set={setServer} />
          <Button title="Switch server and clear session" disabled={busy} onPress={() => void perform(switchServer, false)} />
          <Button title="Sign out and clear local session" disabled={busy} onPress={() => void perform(async () => {
            await SecureStore.deleteItemAsync("jobhunt-session");
            try { await api.logout(); } finally { clearPrivateState(); setAiPreview(null); }
          }, false)} />
        </Panel>
      </>}
    </>}
  </ScrollView></SafeAreaView></SafeAreaProvider>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f3f6fb" },
  page: { padding: 18, gap: 12, paddingBottom: 40 },
  heading: { fontSize: 30, fontWeight: "700", color: "#16355c" },
  title: { fontSize: 19, fontWeight: "600", marginBottom: 8 },
  panel: { backgroundColor: "white", padding: 16, borderRadius: 12, gap: 10 },
  field: { gap: 5 },
  input: { borderColor: "#8395ae", borderWidth: 1, borderRadius: 6, padding: 10, color: "#10223c" },
  multiline: { minHeight: 100, textAlignVertical: "top" },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  error: { color: "#a11919", fontWeight: "600" }
});
