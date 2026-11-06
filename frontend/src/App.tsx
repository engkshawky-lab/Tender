import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { api, getToken, setToken } from "./api";
import { useI18n, useLabel } from "./i18n";
import Audit from "./pages/Audit";
import Dashboard from "./pages/Dashboard";
import Library from "./pages/Library";
import References from "./pages/References";
import Vendors from "./pages/Vendors";
import SettingsPage from "./pages/Settings";
import TenderPage from "./tender/TenderPage";
import { AuthCtx, Field, errText, type Me } from "./ui";

function Login() {
  const { L, lang, setLang } = useI18n();
  const nav = useNavigate();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.login(u, p);
      nav("/");
      window.location.reload();
    } catch (x) {
      setErr(errText(x));
    }
  };
  return (
    <div className="login">
      <form className="card" onSubmit={submit}>
        <header className="card-h">
          <h2>{L("منصة تسعير المناقصات", "Tender Pricing Platform")}</h2>
          <button type="button" className="ghost sm" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{lang === "ar" ? "English" : "عربي"}</button>
        </header>
        <div className="card-b stack">
          <Field label={L("اسم المستخدم", "Username")}><input value={u} onChange={(e) => setU(e.target.value)} autoFocus /></Field>
          <Field label={L("كلمة المرور", "Password")}><input type="password" value={p} onChange={(e) => setP(e.target.value)} /></Field>
          {err && <div className="alert err">{err}</div>}
          <button className="primary">{L("دخول", "Sign in")}</button>
        </div>
      </form>
    </div>
  );
}

export default function App() {
  const { L, lang, setLang } = useI18n();
  const lab = useLabel();
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [ai, setAi] = useState("");
  const load = () => {
    if (!getToken()) { setReady(true); return; }
    api.get("/auth/me").then(setMe).catch(() => setToken(null)).finally(() => setReady(true));
    api.get("/health").then((h) => setAi(h.ai)).catch(() => {});
  };
  useEffect(load, []);
  if (!ready) return null;
  if (!me) return <Routes><Route path="*" element={<Login />} /></Routes>;
  const can = (p: string) => me.permissions.includes(p);
  return (
    <AuthCtx.Provider value={{ me, reload: load }}>
      <div className="shell">
        <aside className="side">
          <div className="brand">{L("منصة تسعير المناقصات", "Tender Pricing Platform")}<small>{L("متكامل · بنية تحتية", "Integrated · Infrastructure")}</small></div>
          <NavLink to="/" end>{L("لوحة المتابعة", "Dashboard")}</NavLink>
          <NavLink to="/vendors">{L("سجل الموردين المعتمدين", "Approved vendors")}</NavLink>
          <NavLink to="/references">{L("المرجعية السعرية", "Pricing references")}</NavLink>
          <NavLink to="/library">{L("مكتبة الأسعار والقوالب", "Price library & templates")}</NavLink>
          {can("audit.view") && <NavLink to="/audit">{L("سجل التعديلات", "Audit log")}</NavLink>}
          <NavLink to="/settings">{L("الإعدادات والمستخدمون", "Settings & users")}</NavLink>
          <div className="foot stack" style={{ gap: 8 }}>
            <div>{me.full_name || me.username}<div className="small" style={{ color: "#9fb3cc" }}>{me.roles.map(lab).join(lang === "ar" ? "، " : ", ")}</div></div>
            <div className="small" style={{ color: "#9fb3cc" }}>AI: {ai === "offline-rules" ? L("وضع بدون مفتاح API", "offline rules (no API key)") : ai}</div>
            <div className="row gap">
              <button className="sm" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>{lang === "ar" ? "English" : "عربي"}</button>
              <button className="sm" onClick={() => { setToken(null); window.location.href = "/login"; }}>{L("خروج", "Sign out")}</button>
            </div>
          </div>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/tenders/:id/*" element={<TenderPage />} />
            <Route path="/library" element={<Library />} />
            <Route path="/vendors" element={<Vendors />} />
            <Route path="/references" element={<References />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/login" element={<Navigate to="/" />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </AuthCtx.Provider>
  );
}
