// ITC Academy — Windows desktop ilovasi (v2).
// Arxitektura:
//  * Asosiy oyna — ilova ichiga joylangan lokal interfeys (`../dist`), sayt emas.
//    Oyna ramkasiz (frameless), title bar va boshqaruv tugmalari interfeysning o'zida.
//  * Ma'lumotlar https://itc-academy.uz/api/v1/ dan Rust orqali olinadi (token auth).
//    Token faqat Rust tomonida saqlanadi — JavaScript'ga hech qachon berilmaydi.
//  * Sayt media fayllari `Cross-Origin-Resource-Policy: same-origin` bilan keladi,
//    shuning uchun rasmlar `itcmedia://` protokoli orqali Rust'da proxy qilinadi.
//  * Dars ijrosi (video, vazifa, test) saytdagi mantiqqa bog'liq — u alohida
//    ichki oynada ochiladi. Bu oynaga hech qanday Tauri IPC ochilmagan.
// XAVFSIZLIK:
//  * IPC faqat `main` oynadagi lokal sahifaga ruxsat etilgan (capabilities/main.json).
//  * `api` buyrug'i faqat `/api/v1/` yo'llarini, `itcmedia` faqat `/media/` va
//    `/static/` yo'llarini qabul qiladi; host har doim qat'iy `itc-academy.uz`.
//  * TLS tekshiruvi tizim (SChannel) standartida — o'chirilmagan.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use serde::Serialize;
use serde_json::Value;
use tauri::http::{header, Response as HttpResponse, StatusCode};
use tauri::webview::{Color, NewWindowFeatures, NewWindowResponse};
use tauri::{
    AppHandle, Manager, Runtime, State, UriSchemeContext, UriSchemeResponder, WebviewUrl,
    WebviewWindow, WebviewWindowBuilder,
};
use url::Url;

const SITE: &str = "https://itc-academy.uz";
/// Sayt kiriş xabarida qurilma "Windows · Kompyuter" bölib körinişi uçun UA'da Windows belgisi bor.
const USER_AGENT: &str = concat!("ITC-Academy-Desktop/", env!("CARGO_PKG_VERSION"), " (Windows NT 10.0; Win64; x64)");

/// Ichki web-oynada ochilishiga ruxsat etilgan domenlar (o'zi va subdomenlari).
const IN_APP_HOSTS: &[&str] = &["itc-academy.uz", "itcreative.uz", "tezcheck.uz", "checkout.uz"];
/// Tizimga topshiriladigan (tashqi) sxemalar.
const EXTERNAL_SCHEMES: &[&str] = &["https", "http", "mailto", "tel", "tg"];

// ───────────────────────── Navigatsiya siyosati ─────────────────────────

fn host_allowed(host: &str) -> bool {
    IN_APP_HOSTS
        .iter()
        .any(|d| host == *d || host.ends_with(&format!(".{d}")))
}

fn in_app(url: &Url) -> bool {
    match url.scheme() {
        "https" => url.host_str().map(host_allowed).unwrap_or(false),
        // WebView2 ichki sahifalari (masalan, about:blank)
        "about" | "data" | "blob" => true,
        _ => false,
    }
}

/// Asosiy (lokal) oyna faqat ilova ichidagi sahifalarda qoladi.
fn is_local_app(url: &Url) -> bool {
    match url.scheme() {
        "tauri" => true,
        "http" | "https" => matches!(url.host_str(), Some("tauri.localhost") | Some("localhost")),
        "about" => true,
        _ => false,
    }
}

fn open_external_url(url: &Url) {
    if EXTERNAL_SCHEMES.contains(&url.scheme()) {
        let _ = tauri_plugin_opener::open_url(url.as_str(), None::<&str>);
    }
}

/// `/api/v1/...` yo'lini tekshiradi: boshqa host, `..`, sxema va hokazolar rad etiladi.
fn api_url(path: &str) -> Option<Url> {
    if !path.starts_with("/api/v1/") || path.contains("..") || path.contains('\\') {
        return None;
    }
    let url = Url::parse(SITE).ok()?.join(path).ok()?;
    (url.host_str() == Some("itc-academy.uz") && url.path().starts_with("/api/v1/")).then_some(url)
}

/// Rasm proxy'si uchun yo'l: faqat `/media/` va `/static/`.
fn media_url(path_and_query: &str) -> Option<Url> {
    let ok_prefix = path_and_query.starts_with("/media/") || path_and_query.starts_with("/static/");
    if !ok_prefix || path_and_query.contains("..") || path_and_query.contains('\\') {
        return None;
    }
    let url = Url::parse(SITE).ok()?.join(path_and_query).ok()?;
    (url.host_str() == Some("itc-academy.uz")).then_some(url)
}

/// Ichki web-oyna uchun yo'l: faqat sayt ichidagi nisbiy yo'l (`/lessons/12/`).
fn web_url(path: &str) -> Option<Url> {
    if !path.starts_with('/') || path.starts_with("//") || path.contains('\\') {
        return None;
    }
    let url = Url::parse(SITE).ok()?.join(path).ok()?;
    (url.host_str() == Some("itc-academy.uz")).then_some(url)
}

// ───────────────────────────── Sessiya ─────────────────────────────

struct Session {
    token: Mutex<Option<String>>,
    client: reqwest::Client,
    file: PathBuf,
    /// Brauzer orqali kiriş: (request_id, code_verifier). Verifier JavaScript'ga berilmaydi.
    pending: Mutex<Option<(String, String)>>,
}

impl Session {
    fn token(&self) -> Option<String> {
        self.token.lock().ok().and_then(|t| t.clone())
    }

    fn set_token(&self, token: Option<String>) {
        if let Ok(mut t) = self.token.lock() {
            *t = token.clone();
        }
        match token {
            Some(tok) => {
                if let Some(dir) = self.file.parent() {
                    let _ = std::fs::create_dir_all(dir);
                }
                let _ = std::fs::write(&self.file, serde_json::json!({ "token": tok }).to_string());
            }
            None => {
                let _ = std::fs::remove_file(&self.file);
            }
        }
    }

    fn load(file: PathBuf) -> Self {
        let token = std::fs::read_to_string(&file)
            .ok()
            .and_then(|s| serde_json::from_str::<Value>(&s).ok())
            .and_then(|v| v.get("token").and_then(Value::as_str).map(str::to_owned))
            .filter(|t| !t.is_empty() && t.chars().all(|c| c.is_ascii_alphanumeric()));
        let client = reqwest::Client::builder()
            .user_agent(USER_AGENT)
            .connect_timeout(Duration::from_secs(10))
            .timeout(Duration::from_secs(30))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .expect("HTTP client");
        Session { token: Mutex::new(token), client, file, pending: Mutex::new(None) }
    }
}

#[derive(Debug, Serialize)]
struct ApiError {
    /// HTTP status; 0 — tarmoq xatosi, 1 — ilova ichki xatosi.
    status: u16,
    data: Value,
}

impl ApiError {
    fn local(status: u16, msg: &str) -> Self {
        ApiError { status, data: serde_json::json!({ "detail": msg }) }
    }
}

async fn read_json(resp: reqwest::Response) -> Value {
    let text = resp.text().await.unwrap_or_default();
    serde_json::from_str(&text).unwrap_or(Value::Null)
}

// ───────────────────────────── Buyruqlar ─────────────────────────────

#[tauri::command]
fn has_session(session: State<'_, Session>) -> bool {
    session.token().is_some()
}

/// Server javobidagi tokenni tekşirib saqlaydi.
fn store_token(session: &Session, data: &Value) -> Result<(), ApiError> {
    let token = data
        .get("token")
        .and_then(Value::as_str)
        .filter(|t| !t.is_empty() && t.len() <= 128 && t.chars().all(|c| c.is_ascii_alphanumeric()))
        .ok_or_else(|| ApiError::local(1, "token"))?;
    session.set_token(Some(token.to_owned()));
    Ok(())
}

async fn post_json(session: &Session, path: &str, body: Value) -> Result<(StatusCode, Value), ApiError> {
    let url = api_url(path).ok_or_else(|| ApiError::local(1, "url"))?;
    let resp = session
        .client
        .post(url)
        .header(header::ACCEPT, "application/json")
        .json(&body)
        .send()
        .await
        .map_err(|_| ApiError::local(0, "network"))?;
    let status = resp.status();
    Ok((status, read_json(resp).await))
}

/// PKCE (RFC 7636): tasodifiy verifier va uning SHA-256 challenge'i (base64url, tenglik belgisisiz).
fn pkce_pair() -> Result<(String, String), ApiError> {
    use base64::engine::general_purpose::URL_SAFE_NO_PAD;
    use base64::Engine;
    use sha2::{Digest, Sha256};
    let mut bytes = [0u8; 48];
    getrandom::fill(&mut bytes).map_err(|_| ApiError::local(1, "random"))?;
    let verifier = URL_SAFE_NO_PAD.encode(bytes);
    let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
    Ok((verifier, challenge))
}

fn approve_url(request_id: &str) -> Option<Url> {
    if request_id.is_empty()
        || request_id.len() > 64
        || !request_id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return None;
    }
    web_url(&format!("/app/desktop-login/{request_id}/"))
}

/// Brauzer orqali kiriş: sörov oçadi va saytni tizim brauzerida oçadi (Google, GitHub, Telegram, email...).
#[tauri::command]
async fn auth_start(session: State<'_, Session>) -> Result<Value, ApiError> {
    let (verifier, challenge) = pkce_pair()?;
    let (status, data) =
        post_json(&session, "/api/v1/app/auth/start/", serde_json::json!({ "code_challenge": challenge })).await?;
    if !status.is_success() {
        return Err(ApiError { status: status.as_u16(), data });
    }
    let request_id = data.get("request_id").and_then(Value::as_str).unwrap_or_default().to_owned();
    let url = approve_url(&request_id).ok_or_else(|| ApiError::local(1, "request_id"))?;
    if let Ok(mut p) = session.pending.lock() {
        *p = Some((request_id, verifier));
    }
    open_external_url(&url);
    Ok(serde_json::json!({
        "user_code": data.get("user_code").cloned().unwrap_or(Value::Null),
        "expires_in": data.get("expires_in").cloned().unwrap_or(Value::from(600)),
        "interval": data.get("interval").cloned().unwrap_or(Value::from(2)),
        "url": url.as_str(),
    }))
}

/// Tasdiqni tekşiradi: "pending" yoki "approved" (token saqlandi). Xatolarda ApiError.
#[tauri::command]
async fn auth_poll(session: State<'_, Session>) -> Result<Value, ApiError> {
    let (request_id, verifier) = session
        .pending
        .lock()
        .ok()
        .and_then(|p| p.clone())
        .ok_or_else(|| ApiError::local(1, "no pending"))?;
    let (status, data) = post_json(
        &session,
        "/api/v1/app/auth/poll/",
        serde_json::json!({ "request_id": request_id, "code_verifier": verifier }),
    )
    .await?;
    if status == StatusCode::ACCEPTED {
        return Ok(Value::from("pending"));
    }
    if let Ok(mut p) = session.pending.lock() {
        *p = None;
    }
    if !status.is_success() {
        return Err(ApiError { status: status.as_u16(), data });
    }
    store_token(&session, &data)?;
    Ok(Value::from("approved"))
}

#[tauri::command]
fn auth_cancel(session: State<'_, Session>) {
    if let Ok(mut p) = session.pending.lock() {
        *p = None;
    }
}

#[tauri::command]
async fn login(
    session: State<'_, Session>,
    username: String,
    password: String,
) -> Result<Value, ApiError> {
    // Ilova kiriş endpoint'i: faqat öquvçilar, kiriş qayd etiladi va Telegram/email xabari yuboriladi
    let (status, data) = post_json(
        &session,
        "/api/v1/app/login/",
        serde_json::json!({ "login": username.trim(), "password": password }),
    )
    .await?;
    if !status.is_success() {
        return Err(ApiError { status: status.as_u16(), data });
    }
    store_token(&session, &data)?;
    Ok(Value::Bool(true))
}

#[tauri::command]
async fn logout(app: AppHandle, session: State<'_, Session>) -> Result<(), ()> {
    session.set_token(None);
    // Keyingi foydalanuvchi oldingisining ochiq dars oynasini ko'rmasin
    for (label, window) in app.webview_windows() {
        if label != "main" {
            let _ = window.close();
        }
    }
    Ok(())
}

/// Umumiy API so'rovi. `method`: GET | POST | PATCH. `body` — JSON.
#[tauri::command]
async fn api(
    session: State<'_, Session>,
    method: String,
    path: String,
    body: Option<Value>,
) -> Result<Value, ApiError> {
    let url = api_url(&path).ok_or_else(|| ApiError::local(1, "path"))?;
    let token = session.token().ok_or_else(|| ApiError::local(401, "no session"))?;
    let req = match method.as_str() {
        "GET" => session.client.get(url),
        "POST" => session.client.post(url),
        "PATCH" => session.client.patch(url),
        _ => return Err(ApiError::local(1, "method")),
    };
    let req = req
        .header(header::AUTHORIZATION, format!("Token {token}"))
        .header(header::ACCEPT, "application/json");
    let req = match body {
        Some(b) => req.json(&b),
        None => req,
    };
    let resp = req.send().await.map_err(|_| ApiError::local(0, "network"))?;
    let status = resp.status();
    let data = read_json(resp).await;
    if status == StatusCode::UNAUTHORIZED {
        session.set_token(None);
    }
    if status.is_success() {
        Ok(data)
    } else {
        Err(ApiError { status: status.as_u16(), data })
    }
}

/// Token bilan bir martalik kiriş havolasini oladi: sayt oynasida qayta login so'ralmaydi.
/// Olib bo'lmasa (tarmoq, eski server) oddiy sahifa ochiladi va sayt o'zi kirishni so'raydi.
async fn signed_web_url(session: &Session, path: &str, fallback: Url) -> Url {
    let Some(token) = session.token() else { return fallback };
    let Some(endpoint) = api_url("/api/v1/app/web-login/") else { return fallback };
    let resp = session
        .client
        .post(endpoint)
        .header(header::AUTHORIZATION, format!("Token {token}"))
        .header(header::ACCEPT, "application/json")
        .json(&serde_json::json!({ "path": path }))
        .send()
        .await;
    let Ok(resp) = resp else { return fallback };
    if !resp.status().is_success() {
        return fallback;
    }
    read_json(resp)
        .await
        .get("url")
        .and_then(Value::as_str)
        .filter(|u| u.starts_with("/app/web-login/"))
        .and_then(web_url)
        .unwrap_or(fallback)
}

/// Saytdagi sahifani (masalan, dars) ilova ichidagi alohida oynada ochadi.
/// Buyruq asinxron: sinxron buyruqda oyna yaratish Windows'da osilib qoladi.
#[tauri::command]
async fn open_web(app: AppHandle, session: State<'_, Session>, path: String) -> Result<(), String> {
    let url = web_url(&path).ok_or("path")?;
    let url = signed_web_url(&session, &path, url).await;
    if let Some(w) = app.get_webview_window("web") {
        let _ = w.navigate(url);
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
        return Ok(());
    }
    web_window(&app, "web", url, None).map(|_| ()).map_err(|e| e.to_string())
}

/// Havolani tizim brauzerida ochadi (faqat https/mailto/tel/tg).
#[tauri::command]
fn open_external(url: String) {
    if let Ok(u) = Url::parse(&url) {
        if u.scheme() != "http" {
            open_external_url(&u);
        }
    }
}

// ─────────────────────────── Rasm proxy'si ───────────────────────────

fn media_protocol<R: Runtime>(
    ctx: UriSchemeContext<'_, R>,
    request: tauri::http::Request<Vec<u8>>,
    responder: UriSchemeResponder,
) {
    let app = ctx.app_handle().clone();
    let pq = request
        .uri()
        .path_and_query()
        .map(|p| p.as_str().to_owned())
        .unwrap_or_default();
    tauri::async_runtime::spawn(async move {
        let fail = |code: StatusCode| {
            HttpResponse::builder().status(code).body(Vec::new()).unwrap()
        };
        let Some(url) = media_url(&pq) else {
            responder.respond(fail(StatusCode::FORBIDDEN));
            return;
        };
        let session = app.state::<Session>();
        let mut req = session.client.get(url);
        if let Some(tok) = session.token() {
            req = req.header(header::AUTHORIZATION, format!("Token {tok}"));
        }
        let resp = match req.send().await {
            Ok(r) if r.status().is_success() => r,
            Ok(r) => {
                responder.respond(fail(StatusCode::from_u16(r.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY)));
                return;
            }
            Err(_) => {
                responder.respond(fail(StatusCode::BAD_GATEWAY));
                return;
            }
        };
        let ctype = resp
            .headers()
            .get(header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("application/octet-stream")
            .to_owned();
        // Faqat rasmlar — HTML/JS kabi kontent lokal sahifaga qaytarilmaydi.
        if !ctype.starts_with("image/") {
            responder.respond(fail(StatusCode::UNSUPPORTED_MEDIA_TYPE));
            return;
        }
        match resp.bytes().await {
            Ok(bytes) => responder.respond(
                HttpResponse::builder()
                    .status(StatusCode::OK)
                    .header(header::CONTENT_TYPE, ctype)
                    .header(header::CACHE_CONTROL, "max-age=3600")
                    .header("X-Content-Type-Options", "nosniff")
                    .body(bytes.to_vec())
                    .unwrap(),
            ),
            Err(_) => responder.respond(fail(StatusCode::BAD_GATEWAY)),
        }
    });
}

// ───────────────────────────── Oynalar ─────────────────────────────

static WINDOW_SEQ: AtomicUsize = AtomicUsize::new(1);

/// Asosiy oyna: lokal interfeys, ramkasiz, Windows 11 soyasi va yumaloq burchaklari bilan.
fn main_window<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<WebviewWindow<R>> {
    WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
        .title("ITC Academy")
        .inner_size(1320.0, 840.0)
        .min_inner_size(980.0, 640.0)
        .decorations(false)
        .shadow(true)
        .background_color(Color(11, 11, 20, 255))
        .center()
        .on_navigation(|url| {
            if is_local_app(url) {
                true
            } else {
                open_external_url(url);
                false
            }
        })
        .on_new_window(|url, _| {
            open_external_url(&url);
            NewWindowResponse::Deny
        })
        .build()
}

/// Sayt sahifalari uchun ichki oyna (dars, to'lov). IPC ochilmagan.
/// `target=_blank` / `window.open` bilan ochilgan ichki sahifalar ham
/// xuddi shu qoidalarga ega yangi oynada ochiladi (masalan, sertifikat yoki PDF).
fn web_window<R: Runtime>(
    app: &AppHandle<R>,
    label: &str,
    url: Url,
    features: Option<NewWindowFeatures>,
) -> tauri::Result<WebviewWindow<R>> {
    let handle = app.clone();
    let mut builder = WebviewWindowBuilder::new(app, label, WebviewUrl::External(url))
        .title("ITC Academy — Dars")
        // Saytning kiriş introsi dars ustida çiqmasin (static/js/brand_intro.js)
        .initialization_script("window.__ITC_APP_WEB__ = true;")
        .inner_size(1200.0, 800.0)
        .min_inner_size(400.0, 600.0)
        .zoom_hotkeys_enabled(true)
        .on_document_title_changed(|window, title| {
            let title = title.trim();
            let _ = window.set_title(if title.is_empty() { "ITC Academy" } else { title });
        })
        .on_navigation(|url| {
            if in_app(url) {
                true
            } else {
                open_external_url(url);
                false
            }
        })
        .on_new_window(move |url, features| {
            if !in_app(&url) {
                open_external_url(&url);
                return NewWindowResponse::Deny;
            }
            let label = format!("w{}", WINDOW_SEQ.fetch_add(1, Ordering::Relaxed));
            let blank = Url::parse("about:blank").expect("about:blank");
            match web_window(&handle, &label, blank, Some(features)) {
                Ok(window) => NewWindowResponse::Create { window },
                Err(_) => NewWindowResponse::Deny,
            }
        });
    builder = match features {
        Some(features) => builder.window_features(features),
        None => builder.center(),
    };
    builder.build()
}

fn main() {
    tauri::Builder::default()
        // Ikkinchi marta ishga tushirilsa — mavjud oyna oldinga chiqariladi
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        // Asosiy oyna ölçami, joyi va kattalaştirilgan holati keyingi işga tuşirişda tiklanadi
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_denylist(&["web"])
                .skip_initial_state("web")
                .build(),
        )
        .register_asynchronous_uri_scheme_protocol("itcmedia", media_protocol)
        .invoke_handler(tauri::generate_handler![
            has_session,
            login,
            auth_start,
            auth_poll,
            auth_cancel,
            logout,
            api,
            open_web,
            open_external
        ])
        .setup(|app| {
            let dir = app.path().app_local_data_dir()?;
            app.manage(Session::load(dir.join("session.json")));
            main_window(app.handle())?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("ITC Academy ishga tushmadi");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn u(s: &str) -> Url {
        Url::parse(s).unwrap()
    }

    #[test]
    fn lms_and_payment_stay_in_app() {
        assert!(in_app(&u("https://itc-academy.uz/dashboard/")));
        assert!(in_app(&u("https://www.itc-academy.uz/")));
        assert!(in_app(&u("https://pay.tezcheck.uz/checkout?id=1")));
        assert!(in_app(&u("https://checkout.uz/x")));
    }

    #[test]
    fn other_sites_and_plain_http_leave_app() {
        assert!(!in_app(&u("http://itc-academy.uz/")));
        assert!(!in_app(&u("https://itc-academy.uz.evil.com/")));
        assert!(!in_app(&u("https://evilitc-academy.uz/")));
        assert!(!in_app(&u("https://youtube.com/watch?v=1")));
        assert!(!in_app(&u("file:///C:/Windows/win.ini")));
    }

    #[test]
    fn main_window_stays_local() {
        assert!(is_local_app(&u("http://tauri.localhost/index.html")));
        assert!(is_local_app(&u("tauri://localhost/")));
        assert!(!is_local_app(&u("https://itc-academy.uz/")));
        assert!(!is_local_app(&u("http://tauri.localhost.evil.com/")));
    }

    #[test]
    fn api_paths_are_restricted() {
        assert_eq!(
            api_url("/api/v1/profile/").unwrap().as_str(),
            "https://itc-academy.uz/api/v1/profile/"
        );
        assert!(api_url("/api/v1/reyting/?tab=score&limit=50").is_some());
        assert!(api_url("/admin/").is_none());
        assert!(api_url("/api/v1/../admin/").is_none());
        assert!(api_url("//evil.com/api/v1/").is_none());
        assert!(api_url("https://evil.com/api/v1/").is_none());
    }

    #[test]
    fn media_paths_are_restricted() {
        assert!(media_url("/media/photos/a.jpg").is_some());
        assert!(media_url("/static/img/logo.png").is_some());
        assert!(media_url("/api/v1/profile/").is_none());
        assert!(media_url("/media/../api/v1/token/").is_none());
        assert!(media_url("//evil.com/media/x.png").is_none());
    }

    #[test]
    fn pkce_pair_matches_rfc7636() {
        use base64::engine::general_purpose::URL_SAFE_NO_PAD;
        use base64::Engine;
        use sha2::{Digest, Sha256};
        let (verifier, challenge) = pkce_pair().unwrap();
        assert_eq!(verifier.len(), 64);
        assert_eq!(challenge.len(), 43);
        assert_eq!(challenge, URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes())));
    }

    #[test]
    fn approve_url_is_restricted() {
        assert_eq!(
            approve_url("abc_DEF-123").unwrap().as_str(),
            "https://itc-academy.uz/app/desktop-login/abc_DEF-123/"
        );
        assert!(approve_url("../admin").is_none());
        assert!(approve_url("a/b").is_none());
        assert!(approve_url("").is_none());
    }

    #[test]
    fn web_paths_are_restricted() {
        assert_eq!(
            web_url("/lessons/12/").unwrap().as_str(),
            "https://itc-academy.uz/lessons/12/"
        );
        assert!(web_url("//evil.com/").is_none());
        assert!(web_url("https://evil.com/").is_none());
        assert!(web_url("lessons/1/").is_none());
    }
}
